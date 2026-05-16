"""
shared/squawk_generator.py
──────────────────────────
Convierte decisiones del pipeline en squawks personalizados por usuario.

Flujo:
    1. Pipeline genera una decisión para un ticker (BUY/HOLD)
    2. Este módulo busca qué usuarios siguen ese ticker
    3. Para cada usuario, aplica sus guardrails personalizados
    4. Genera un squawk con texto explicativo y lo guarda en gold_squawks

Uso:
    from shared.squawk_generator import generate_squawks
    generate_squawks(decision, row, detalle, run_id)
"""

from __future__ import annotations

import json
import logging

from shared.db import execute, query
from shared.guardrails import check_guardrails

log = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────

# Guardrails por defecto del sistema (usados si el usuario no tiene overrides)
DEFAULT_GUARDRAILS = {
    "score_threshold": 50,
    "horario_mercado": {"activo": True},
    "posicion_abierta": {"activo": True},
}


def generate_squawks(
    decision: dict,
    row,
    detalle: dict,
    run_id: str = "",
) -> int:
    """
    Genera squawks para todos los usuarios que siguen el ticker.

    Args:
        decision: dict del pipeline (ts, ticker, decision, score_final, motivo_rechazo)
        row:      última vela (pandas Series) con indicadores técnicos
        detalle:  dict con scores individuales de cada modelo
        run_id:   identificador de la ejecución del pipeline

    Returns:
        Número de squawks generados
    """
    ticker = decision["ticker"]
    score = decision["score_final"]
    pipeline_decision = decision["decision"]
    motivo_rechazo = decision.get("motivo_rechazo", "")

    # Buscar usuarios que siguen este ticker
    users = _get_users_for_ticker(ticker)
    if not users:
        return 0

    # Extraer datos de mercado del row
    market_data = _extract_market_data(row)
    model_scores = _extract_model_scores(detalle)

    squawks_created = 0

    for user in users:
        try:
            user_id = str(user["id"])
            user_guardrails = user.get("guardrail_overrides") or {}
            user_locale = user.get("locale", "es")

            # Guardrails del usuario para este ticker (o defaults)
            ticker_guardrails = user_guardrails.get(ticker, user_guardrails)
            merged_guardrails = {**DEFAULT_GUARDRAILS, **ticker_guardrails}

            # Evaluar guardrails del usuario
            estado_user = {
                "posicion_abierta": False,
                "n_posiciones": 0,
                "ordenes_hoy": 0,
            }
            user_passes, user_motivo = check_guardrails(
                row, score, merged_guardrails, estado_user
            )

            # Determinar tipo y prioridad del squawk
            squawk_type = _determine_squawk_type(
                pipeline_decision, score, user_passes
            )
            priority = _determine_priority(squawk_type, score)

            # Generar texto explicativo
            motivo_text = _generate_motivo(
                ticker, squawk_type, score, market_data,
                user_passes, user_motivo, motivo_rechazo, user_locale
            )

            # Guardrails que pasaron/fallaron
            guardrails_passed = _evaluate_guardrails_detail(
                row, score, merged_guardrails, estado_user
            )

            # Escribir squawk
            squawk_id = _save_squawk(
                user_id=user_id,
                ticker=ticker,
                squawk_type=squawk_type,
                priority=priority,
                score=score,
                decision=pipeline_decision,
                motivo=motivo_text,
                motivo_rechazo=user_motivo if not user_passes else "",
                guardrails_passed=guardrails_passed,
                guardrails_config=merged_guardrails,
                market_data=market_data,
                model_scores=model_scores,
                run_id=run_id,
                decision_ts=decision["ts"],
                audio_locale=user_locale,
            )

            # Generar audio TTS (no bloquea si falla)
            if squawk_id and motivo_text:
                try:
                    from shared.tts import generate_audio

                    audio_url = generate_audio(squawk_id, motivo_text, user_locale)
                    if audio_url:
                        execute(
                            "UPDATE gold_squawks SET audio_url = %s WHERE id = %s",
                            [audio_url, squawk_id],
                        )
                except Exception as e:
                    log.warning("  TTS falló para squawk %s: %s", squawk_id, e)

            squawks_created += 1

        except Exception as e:
            log.error("Error generando squawk para user %s: %s", user_id, e)

    if squawks_created:
        log.info(
            "  %s: %d squawks generados (%s, score %.1f)",
            ticker, squawks_created, pipeline_decision, score,
        )

    return squawks_created


# ── Helpers privados ──────────────────────────────────────────────────────────


def _get_users_for_ticker(ticker: str) -> list[dict]:
    """Busca usuarios activos que siguen este ticker."""
    rows = query(
        """SELECT u.id, u.locale, up.guardrail_overrides
           FROM users u
           JOIN user_preferences up ON up.user_id = u.id
           WHERE u.is_active = true
             AND up.tickers @> %s::jsonb""",
        [json.dumps([ticker])],
    )
    return rows


def _extract_market_data(row) -> dict:
    """Extrae indicadores técnicos relevantes del row para incluir en el squawk."""
    fields = [
        "rsi_14", "macd_line", "macd_signal", "bb_pct", "bb_width",
        "vwap", "atr_14", "ema_9", "ema_21", "returns_5", "volume_norm",
        "close", "open", "high", "low", "volume",
    ]
    data = {}
    for f in fields:
        val = row.get(f)
        if val is not None:
            try:
                data[f] = round(float(val), 4)
            except (TypeError, ValueError):
                pass
    return data


def _extract_model_scores(detalle: dict) -> dict:
    """Extrae scores individuales de cada modelo."""
    scores = {}
    if isinstance(detalle, dict):
        for model_name, info in detalle.items():
            if isinstance(info, dict):
                scores[model_name] = {
                    "score": round(info.get("score", 0), 2),
                    "weight": round(info.get("weight", 0), 2),
                }
            elif isinstance(info, (int, float)):
                scores[model_name] = {"score": round(float(info), 2)}
    return scores


def _determine_squawk_type(pipeline_decision: str, score: float, user_passes: bool) -> str:
    """Determina el tipo de squawk según la decisión y los guardrails del usuario."""
    if pipeline_decision == "BUY" and user_passes:
        return "BUY"
    if pipeline_decision == "BUY" and not user_passes:
        return "INFO"  # El pipeline dice BUY pero los guardrails del usuario lo rechazan
    if score >= 40:
        return "HOLD"  # Score decente pero no suficiente
    return "HOLD"


def _determine_priority(squawk_type: str, score: float) -> str:
    """Determina la prioridad del squawk."""
    if squawk_type == "BUY" and score >= 75:
        return "high"
    if squawk_type == "BUY":
        return "medium"
    return "low"


def _generate_motivo(
    ticker: str,
    squawk_type: str,
    score: float,
    market_data: dict,
    user_passes: bool,
    user_motivo: str,
    pipeline_motivo: str,
    locale: str,
) -> str:
    """Genera el texto explicativo del squawk."""
    rsi = market_data.get("rsi_14")
    macd_line = market_data.get("macd_line", 0)
    macd_signal = market_data.get("macd_signal", 0)
    price = market_data.get("close")

    if locale.startswith("es"):
        return _motivo_es(
            ticker, squawk_type, score, rsi, macd_line, macd_signal,
            price, user_passes, user_motivo, pipeline_motivo,
        )
    return _motivo_en(
        ticker, squawk_type, score, rsi, macd_line, macd_signal,
        price, user_passes, user_motivo, pipeline_motivo,
    )


def _motivo_es(
    ticker, squawk_type, score, rsi, macd_line, macd_signal,
    price, user_passes, user_motivo, pipeline_motivo,
) -> str:
    """Texto en español."""
    parts = [f"{ticker} {squawk_type} — Score {score:.0f}/100."]

    if price:
        parts.append(f"Precio: ${price:.2f}.")

    if rsi is not None:
        if rsi < 30:
            parts.append(f"RSI {rsi:.0f} (sobreventa).")
        elif rsi > 70:
            parts.append(f"RSI {rsi:.0f} (sobrecompra).")
        else:
            parts.append(f"RSI {rsi:.0f} (neutral).")

    if macd_line and macd_signal:
        if macd_line > macd_signal:
            parts.append("MACD alcista.")
        else:
            parts.append("MACD bajista.")

    if not user_passes and user_motivo:
        parts.append(f"Bloqueado por: {user_motivo}.")
    elif pipeline_motivo:
        parts.append(f"Pipeline: {pipeline_motivo}.")

    return " ".join(parts)


def _motivo_en(
    ticker, squawk_type, score, rsi, macd_line, macd_signal,
    price, user_passes, user_motivo, pipeline_motivo,
) -> str:
    """Texto en inglés."""
    parts = [f"{ticker} {squawk_type} — Score {score:.0f}/100."]

    if price:
        parts.append(f"Price: ${price:.2f}.")

    if rsi is not None:
        if rsi < 30:
            parts.append(f"RSI {rsi:.0f} (oversold).")
        elif rsi > 70:
            parts.append(f"RSI {rsi:.0f} (overbought).")
        else:
            parts.append(f"RSI {rsi:.0f} (neutral).")

    if macd_line and macd_signal:
        if macd_line > macd_signal:
            parts.append("MACD bullish.")
        else:
            parts.append("MACD bearish.")

    if not user_passes and user_motivo:
        parts.append(f"Blocked by: {user_motivo}.")
    elif pipeline_motivo:
        parts.append(f"Pipeline: {pipeline_motivo}.")

    return " ".join(parts)


def _evaluate_guardrails_detail(row, score, cfg_gr, estado) -> dict:
    """Evalúa cada guardrail individualmente y devuelve el resultado."""
    results = {}
    guardrail_names = [
        "score_minimo", "rsi", "macd", "bollinger", "atr_volatilidad",
        "volumen", "ema_trend", "vwap", "sentiment",
        "horario_mercado", "posicion_abierta", "max_posiciones",
        "ordenes_diarias_max", "circuit_breaker",
    ]
    for name in guardrail_names:
        gr_config = cfg_gr.get(name, {})
        if isinstance(gr_config, dict) and gr_config.get("activo"):
            # Evaluar solo este guardrail
            single_cfg = {name: gr_config, "score_threshold": cfg_gr.get("score_threshold", 50)}
            passes, _ = check_guardrails(row, score, single_cfg, estado)
            results[name] = passes
    return results


def _save_squawk(
    user_id: str,
    ticker: str,
    squawk_type: str,
    priority: str,
    score: float,
    decision: str,
    motivo: str,
    motivo_rechazo: str,
    guardrails_passed: dict,
    guardrails_config: dict,
    market_data: dict,
    model_scores: dict,
    run_id: str,
    decision_ts: str,
    audio_locale: str,
) -> str | None:
    """Escribe un squawk en gold_squawks. Devuelve el id del squawk creado."""
    from shared.db import query_one as _query_one

    row = _query_one(
        """INSERT INTO gold_squawks
           (user_id, ticker, squawk_type, priority, score, decision,
            motivo, motivo_rechazo, guardrails_passed, guardrails_config,
            market_data, model_scores, run_id, decision_ts, audio_locale)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        [
            user_id, ticker, squawk_type, priority, round(score, 2), decision,
            motivo, motivo_rechazo,
            json.dumps(guardrails_passed), json.dumps(guardrails_config),
            json.dumps(market_data), json.dumps(model_scores),
            run_id, decision_ts, audio_locale,
        ],
    )
    return str(row["id"]) if row else None
