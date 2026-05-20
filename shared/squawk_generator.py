"""
shared/squawk_generator.py
──────────────────────────
Convierte decisiones del pipeline en squawks personalizados por usuario.

Fase 6.11: LONG/SHORT en vez de BUY/SELL, señales rule-based en el texto.

Flujo (pipeline multi-usuario):
    1. Pipeline calcula score sistema + señales (compartido por ticker)
    2. Para cada usuario: PRE guardrails → custom models → POST → squawk
    3. generate_squawk_for_user() genera UN squawk con audio TTS

También mantiene generate_squawks() para backward compat con el flujo antiguo.

Uso:
    from shared.squawk_generator import generate_squawk_for_user
    generate_squawk_for_user(user, ticker, squawk_type, score, ...)
"""

from __future__ import annotations

import json
import logging

from shared.db import execute, query
from shared.guardrails import check_guardrails

log = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_GUARDRAILS = {
    "score_threshold": 50,
    "horario_mercado": {"activo": True},
    "posicion_abierta": {"activo": True},
}


# ── Nuevo: generar squawk para UN usuario (Fase 6.11) ─────────────────────────


def generate_squawk_for_user(
    user_id: str,
    ticker: str,
    squawk_type: str,
    score: float,
    row,
    detalle: dict,
    signal_texts: list[str] | None = None,
    motivo_rechazo: str = "",
    guardrails_config: dict | None = None,
    run_id: str = "",
    decision_ts: str = "",
    locale: str = "es",
    ticker_direction: str = "long",
) -> str | None:
    """
    Genera UN squawk para un usuario específico.

    Llamado desde el pipeline multi-usuario (Paso 4).

    Args:
        user_id:          ID del usuario
        ticker:           ticker de la alerta
        squawk_type:      "LONG", "SHORT", "HOLD", "INFO"
        score:            score final del usuario (0-100)
        row:              última vela (pd.Series)
        detalle:          scores por modelo
        signal_texts:     textos de señales rule-based disparadas
        motivo_rechazo:   motivo si fue rechazado por guardrails
        guardrails_config: configuración de guardrails usada
        run_id:           ID de la ejecución del pipeline
        decision_ts:      timestamp de la decisión
        locale:           idioma del usuario (es, en)
        ticker_direction: dirección preferida del usuario (long, short)

    Returns:
        ID del squawk creado, o None si falla
    """
    market_data = _extract_market_data(row)
    model_scores = _extract_model_scores(detalle)
    priority = _determine_priority(squawk_type, score)

    # Generar texto explicativo incluyendo señales
    motivo_text = _generate_motivo_v2(
        ticker=ticker,
        squawk_type=squawk_type,
        score=score,
        market_data=market_data,
        signal_texts=signal_texts or [],
        motivo_rechazo=motivo_rechazo,
        locale=locale,
        ticker_direction=ticker_direction,
    )

    # Evaluar guardrails detail (para info del squawk)
    guardrails_passed = {}
    if guardrails_config:
        guardrails_passed = _evaluate_guardrails_detail(
            row, score, guardrails_config, {"posicion_abierta": False, "n_posiciones": 0, "ordenes_hoy": 0}
        )

    # Escribir squawk
    squawk_id = _save_squawk(
        user_id=user_id,
        ticker=ticker,
        squawk_type=squawk_type,
        priority=priority,
        score=score,
        decision=squawk_type,
        motivo=motivo_text,
        motivo_rechazo=motivo_rechazo,
        guardrails_passed=guardrails_passed,
        guardrails_config=guardrails_config or {},
        market_data=market_data,
        model_scores=model_scores,
        run_id=run_id,
        decision_ts=decision_ts,
        audio_locale=locale,
    )

    # Generar audio TTS
    if squawk_id and motivo_text:
        _generate_tts(squawk_id, motivo_text, locale)

    return squawk_id


# ── Backward compat: generate_squawks() para flujo antiguo ────────────────────


def generate_squawks(
    decision: dict,
    row,
    detalle: dict,
    run_id: str = "",
) -> int:
    """
    Genera squawks para todos los usuarios que siguen el ticker.
    Backward compat con el flujo pre-6.11 (usado por backtest).
    """
    ticker = decision["ticker"]
    score = decision["score_final"]
    pipeline_decision = decision["decision"]
    motivo_rechazo = decision.get("motivo_rechazo", "")

    users = _get_users_for_ticker(ticker)
    if not users:
        return 0

    market_data = _extract_market_data(row)
    model_scores = _extract_model_scores(detalle)

    squawks_created = 0

    for user in users:
        try:
            user_id = str(user["id"])
            user_guardrails = user.get("guardrail_overrides") or {}
            user_locale = user.get("locale", "es")

            ticker_guardrails = user_guardrails.get(ticker, user_guardrails)
            merged_guardrails = {**DEFAULT_GUARDRAILS, **ticker_guardrails}

            estado_user = {
                "posicion_abierta": False,
                "n_posiciones": 0,
                "ordenes_hoy": 0,
            }
            user_passes, user_motivo = check_guardrails(
                row, score, merged_guardrails, estado_user
            )

            squawk_type = _determine_squawk_type(
                pipeline_decision, score, user_passes
            )
            priority = _determine_priority(squawk_type, score)

            motivo_text = _generate_motivo(
                ticker, squawk_type, score, market_data,
                user_passes, user_motivo, motivo_rechazo, user_locale
            )

            guardrails_passed = _evaluate_guardrails_detail(
                row, score, merged_guardrails, estado_user
            )

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

            if squawk_id and motivo_text:
                _generate_tts(squawk_id, motivo_text, user_locale)

            squawks_created += 1

        except Exception as e:
            log.error("Error generando squawk para user %s: %s", user.get("id"), e)

    if squawks_created:
        log.info(
            "  %s: %d squawks generados (%s, score %.1f)",
            ticker, squawks_created, pipeline_decision, score,
        )

    return squawks_created


# ── Helpers privados ──────────────────────────────────────────────────────────


def _generate_tts(squawk_id: str, text: str, locale: str) -> None:
    """Genera audio TTS para un squawk. No bloquea si falla."""
    try:
        from shared.tts import generate_audio

        audio_url, audio_duration = generate_audio(squawk_id, text, locale)
        if audio_url:
            if audio_duration is not None:
                execute(
                    "UPDATE gold_squawks SET audio_url = %s, audio_duration = %s WHERE id = %s",
                    [audio_url, audio_duration, squawk_id],
                )
            else:
                execute(
                    "UPDATE gold_squawks SET audio_url = %s WHERE id = %s",
                    [audio_url, squawk_id],
                )
    except Exception as e:
        log.warning("  TTS falló para squawk %s: %s", squawk_id, e)


def _get_users_for_ticker(ticker: str) -> list[dict]:
    """Busca usuarios activos que siguen este ticker."""
    rows = query(
        """SELECT u.id, u.locale, up.guardrail_overrides,
                  up.models_config, up.ticker_direction
           FROM users u
           JOIN user_preferences up ON up.user_id = u.id
           WHERE u.is_active = true
             AND up.tickers @> %s::jsonb""",
        [json.dumps([ticker])],
    )
    return rows


def _extract_market_data(row) -> dict:
    """Extrae indicadores técnicos relevantes del row."""
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
    """Determina tipo de squawk (backward compat)."""
    if pipeline_decision in ("LONG", "SHORT", "BUY") and user_passes:
        return pipeline_decision
    if pipeline_decision in ("LONG", "SHORT", "BUY") and not user_passes:
        return "INFO"
    return "HOLD"


def _determine_priority(squawk_type: str, score: float) -> str:
    """Determina la prioridad del squawk."""
    if squawk_type in ("LONG", "SHORT", "BUY") and score >= 75:
        return "high"
    if squawk_type in ("LONG", "SHORT", "BUY"):
        return "medium"
    return "low"


# ── Texto del squawk (v2: con señales) ────────────────────────────────────────


def _generate_motivo_v2(
    ticker: str,
    squawk_type: str,
    score: float,
    market_data: dict,
    signal_texts: list[str],
    motivo_rechazo: str,
    locale: str,
    ticker_direction: str,
) -> str:
    """Genera texto del squawk incluyendo señales disparadas (Fase 6.10)."""
    rsi = market_data.get("rsi_14")
    macd_line = market_data.get("macd_line", 0)
    macd_signal = market_data.get("macd_signal", 0)
    price = market_data.get("close")

    if locale.startswith("es"):
        parts = [f"{ticker} {squawk_type} — Score {score:.0f}/100."]

        if price:
            parts.append(f"Precio: ${price:.2f}.")

        if rsi is not None:
            if rsi < 30:
                parts.append(f"RSI {rsi:.0f} (sobreventa).")
            elif rsi > 70:
                parts.append(f"RSI {rsi:.0f} (sobrecompra).")

        if macd_line and macd_signal:
            if macd_line > macd_signal:
                parts.append("MACD alcista.")
            else:
                parts.append("MACD bajista.")

        # Señales rule-based disparadas
        if signal_texts:
            n = len(signal_texts)
            parts.append(f"{n} señales activas:")
            # Incluir las 3 más relevantes
            for text in signal_texts[:3]:
                parts.append(text + ".")
            if n > 3:
                parts.append(f"(+{n - 3} más).")

        if motivo_rechazo:
            parts.append(f"Bloqueado: {motivo_rechazo}.")

    else:
        parts = [f"{ticker} {squawk_type} — Score {score:.0f}/100."]

        if price:
            parts.append(f"Price: ${price:.2f}.")

        if rsi is not None:
            if rsi < 30:
                parts.append(f"RSI {rsi:.0f} (oversold).")
            elif rsi > 70:
                parts.append(f"RSI {rsi:.0f} (overbought).")

        if macd_line and macd_signal:
            if macd_line > macd_signal:
                parts.append("MACD bullish.")
            else:
                parts.append("MACD bearish.")

        if signal_texts:
            n = len(signal_texts)
            parts.append(f"{n} active signals:")
            for text in signal_texts[:3]:
                parts.append(text + ".")
            if n > 3:
                parts.append(f"(+{n - 3} more).")

        if motivo_rechazo:
            parts.append(f"Blocked: {motivo_rechazo}.")

    return " ".join(parts)


# ── Texto del squawk (v1: backward compat) ────────────────────────────────────


def _generate_motivo(
    ticker, squawk_type, score, market_data,
    user_passes, user_motivo, pipeline_motivo, locale,
) -> str:
    """Genera texto del squawk (backward compat)."""
    rsi = market_data.get("rsi_14")
    macd_line = market_data.get("macd_line", 0)
    macd_signal = market_data.get("macd_signal", 0)
    price = market_data.get("close")

    if locale.startswith("es"):
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
            parts.append("MACD alcista." if macd_line > macd_signal else "MACD bajista.")
        if not user_passes and user_motivo:
            parts.append(f"Bloqueado por: {user_motivo}.")
        elif pipeline_motivo:
            parts.append(f"Pipeline: {pipeline_motivo}.")
    else:
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
            parts.append("MACD bullish." if macd_line > macd_signal else "MACD bearish.")
        if not user_passes and user_motivo:
            parts.append(f"Blocked by: {user_motivo}.")
        elif pipeline_motivo:
            parts.append(f"Pipeline: {pipeline_motivo}.")

    return " ".join(parts)


def _evaluate_guardrails_detail(row, score, cfg_gr, estado) -> dict:
    """Evalúa cada guardrail individualmente."""
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
    """Escribe un squawk en gold_squawks."""
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
