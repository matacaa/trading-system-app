"""
guardrails.py
─────────────
Guardrails del pipeline — PRE (mercado) y POST (score).

Pipeline Fase 6.11:
    PRE:  13 guardrails de mercado (sin score ML) — si no pasa → HOLD
    POST: 1 guardrail (score_minimo) — evaluado con score FINAL

También exporta check_guardrails() y decide() originales para
backward compat con backtest.

Cambios respecto al original:
    - 6.11: split en check_guardrails_pre() y check_guardrails_post()
    - 6.12: variable 'row' renombrada a 'cfg_row' en circuit_breaker
    - F-17 a F-24: cambios de fases anteriores preservados
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd

log = logging.getLogger(__name__)

# F-21: threshold por defecto, sobreescribible desde yaml
DEFAULT_SCORE_THRESHOLD = 50


# ── PRE guardrails (13, solo datos de mercado, sin score ML) ──────────


def check_guardrails_pre(
    row: pd.Series,
    cfg_gr: dict,
    estado: dict,
) -> tuple[bool, str]:
    """
    Evalúa los 13 guardrails de mercado SIN score ML.

    Usado en Paso 1 del pipeline multi-usuario.
    Si no pasa → HOLD, no se ejecuta inferencia.

    Guardrails direccionales (RSI, MACD, Bollinger, EMA, VWAP) se evalúan
    en ambas direcciones: si CUALQUIER condición extrema se cumple, bloquea.

    Args:
        row:    última vela de silver_features_rt
        cfg_gr: configuración de guardarraíles (JSONB o yaml)
        estado: estado actual del portfolio del usuario

    Returns:
        (pasa, motivo_rechazo)
    """
    # 2. RSI — en PRE, bloquea si está en extremos (sin dirección)
    gr = cfg_gr.get("rsi", {})
    if gr.get("activo"):
        rsi = row.get("rsi_14")
        if rsi is not None:
            if rsi > gr.get("compra_max", 70):
                return False, f"rsi_sobrecompra ({rsi:.1f} > {gr['compra_max']})"
            if rsi < gr.get("venta_min", 30):
                return False, f"rsi_sobreventa ({rsi:.1f} < {gr['venta_min']})"

    # 3. MACD — en PRE, solo informativo (no bloquea sin dirección)
    # Se evalúa en check_guardrails() completo para backtest

    # 4. Bollinger — en PRE, bloquea si en extremos
    gr = cfg_gr.get("bollinger", {})
    if gr.get("activo"):
        bb_pct = row.get("bb_pct")
        if bb_pct is not None:
            if bb_pct > gr.get("compra_max", 0.95):
                return False, f"bollinger_techo ({bb_pct:.2f} > {gr['compra_max']})"
            if bb_pct < gr.get("venta_min", 0.05):
                return False, f"bollinger_suelo ({bb_pct:.2f} < {gr.get('venta_min', 0.05)})"

    # 5. ATR volatilidad
    gr = cfg_gr.get("atr_volatilidad", {})
    if gr.get("activo"):
        atr_val = row.get("atr_14", 0)
        close = row.get("close", 1)
        atr_pct = atr_val / close * 100 if close > 0 else 0
        max_atr = gr.get("max_atr_pct", gr.get("max_multiplicador", 2.0))
        if atr_pct > max_atr:
            return False, f"atr_volatilidad ({atr_pct:.2f}% > {max_atr}%)"

    # 6. Volumen
    gr = cfg_gr.get("volumen", {})
    if gr.get("activo"):
        vol_norm = row.get("volume_norm")
        if vol_norm is not None and vol_norm < gr.get("min_volume_norm", 0.5):
            return False, f"volumen_bajo ({vol_norm:.2f} < {gr['min_volume_norm']})"

    # 7. EMA tendencia — en PRE, no bloquea (necesita dirección)

    # 8. VWAP spread — en PRE, no bloquea (necesita dirección)

    # 9. Sentiment
    gr = cfg_gr.get("sentiment", {})
    if gr.get("activo"):
        sent_score = row.get("sentiment_score")
        if sent_score is None:
            if gr.get("bloquear_sin_datos", False):
                return False, "sentiment_sin_datos"
        elif sent_score < gr.get("min_score", 0.0):
            return False, f"sentiment_negativo ({sent_score:.3f})"

    # 10. Horario mercado
    gr = cfg_gr.get("horario_mercado", {})
    if gr.get("activo"):
        if not row.get("is_market_open", False):
            return False, "fuera_horario_mercado"

    # 11. Posición abierta
    gr = cfg_gr.get("posicion_abierta", {})
    if gr.get("activo") and estado.get("posicion_abierta"):
        return False, "posicion_ya_abierta"

    # 12. Max posiciones
    gr = cfg_gr.get("max_posiciones", {})
    if gr.get("activo") and estado.get("n_posiciones", 0) >= gr.get("valor", 3):
        return False, f"max_posiciones ({estado['n_posiciones']})"

    # 13. Órdenes diarias max
    gr = cfg_gr.get("ordenes_diarias_max", {})
    if gr.get("activo") and estado.get("ordenes_hoy", 0) >= gr.get("valor", 5):
        return False, f"ordenes_diarias_max ({estado['ordenes_hoy']})"

    # 14. Circuit breaker
    gr = cfg_gr.get("circuit_breaker", {})
    if gr.get("activo"):
        try:
            from shared.db import query_one

            cfg_row = query_one("SELECT trading_enabled FROM config WHERE id = 1")
            if cfg_row and not cfg_row.get("trading_enabled", True):
                return False, "circuit_breaker_activo"
        except Exception as e:
            log.warning(
                f"Circuit breaker: no se pudo leer tabla 'config': {e}. "
                f"Asegúrate de que existe (ver scripts/schema_fixes.sql)."
            )

    return True, ""


# ── POST guardrail (score_minimo) ─────────────────────────────────────


def check_guardrails_post(
    score_final: float,
    cfg_gr: dict,
) -> tuple[bool, str]:
    """
    Evalúa el guardrail POST (score_minimo) con el score FINAL.

    Usado en Paso 4 del pipeline multi-usuario.
    Si pasa → señal LONG o SHORT (según ticker_direction del usuario).

    Args:
        score_final: score combinado (sistema + custom + señales), 0-100
        cfg_gr:      configuración de guardarraíles

    Returns:
        (pasa, motivo_rechazo)
    """
    score_threshold = cfg_gr.get("score_threshold", DEFAULT_SCORE_THRESHOLD)

    gr = cfg_gr.get("score_minimo", {})
    min_score = gr.get("valor", score_threshold)

    if gr.get("activo") and score_final < min_score:
        return False, f"score_minimo ({score_final:.1f} < {min_score})"

    # También verificar contra score_threshold general
    if score_final < score_threshold:
        return False, f"score_bajo ({score_final:.1f} < {score_threshold})"

    return True, ""


# ── Backward compat: check_guardrails() y decide() originales ─────────


def check_guardrails(
    row: pd.Series,
    score: float,
    cfg_gr: dict,
    estado: dict,
) -> tuple[bool, str]:
    """
    Evalúa TODOS los guardarraíles (PRE + POST). Backward compat para backtest.

    Args:
        row:    última vela
        score:  score ponderado de los modelos (0-100)
        cfg_gr: configuración de guardarraíles
        estado: estado actual del portfolio

    Returns:
        (pasa, motivo_rechazo)
    """
    score_threshold = cfg_gr.get("score_threshold", DEFAULT_SCORE_THRESHOLD)
    is_bullish = score >= score_threshold

    # 1. Score mínimo
    gr = cfg_gr.get("score_minimo", {})
    if gr.get("activo") and score < gr.get("valor", 65):
        return False, f"score_minimo ({score:.1f} < {gr['valor']})"

    # 2. RSI
    gr = cfg_gr.get("rsi", {})
    if gr.get("activo"):
        rsi = row.get("rsi_14")
        if rsi is not None:
            if is_bullish and rsi > gr.get("compra_max", 70):
                return False, f"rsi_sobrecompra ({rsi:.1f} > {gr['compra_max']})"
            if not is_bullish and rsi < gr.get("venta_min", 30):
                return False, f"rsi_sobreventa ({rsi:.1f} < {gr['venta_min']})"

    # 3. MACD
    gr = cfg_gr.get("macd", {})
    if gr.get("activo"):
        if is_bullish and row.get("macd_line", 0) < row.get("macd_signal", 0):
            return False, "macd_bajista"

    # 4. Bollinger
    gr = cfg_gr.get("bollinger", {})
    if gr.get("activo"):
        bb_pct = row.get("bb_pct")
        if bb_pct is not None and is_bullish and bb_pct > gr.get("compra_max", 0.95):
            return False, f"bollinger_techo ({bb_pct:.2f} > {gr['compra_max']})"

    # 5. ATR volatilidad
    gr = cfg_gr.get("atr_volatilidad", {})
    if gr.get("activo"):
        atr_val = row.get("atr_14", 0)
        close = row.get("close", 1)
        atr_pct = atr_val / close * 100 if close > 0 else 0
        max_atr = gr.get("max_atr_pct", gr.get("max_multiplicador", 2.0))
        if atr_pct > max_atr:
            return False, f"atr_volatilidad ({atr_pct:.2f}% > {max_atr}%)"

    # 6. Volumen
    gr = cfg_gr.get("volumen", {})
    if gr.get("activo"):
        vol_norm = row.get("volume_norm")
        if vol_norm is not None and vol_norm < gr.get("min_volume_norm", 0.5):
            return False, f"volumen_bajo ({vol_norm:.2f} < {gr['min_volume_norm']})"

    # 7. EMA tendencia
    gr = cfg_gr.get("ema_tendencia", {})
    if gr.get("activo"):
        close = row.get("close", 0)
        ema_21 = row.get("ema_21", 0)
        if is_bullish and close < ema_21:
            return False, f"ema_bajista (close {close:.2f} < ema_21 {ema_21:.2f})"

    # 8. VWAP spread
    gr = cfg_gr.get("vwap_spread", {})
    if gr.get("activo"):
        close = row.get("close", 0)
        vwap_val = row.get("vwap", 0)
        if vwap_val > 0 and is_bullish:
            spread = (close - vwap_val) / vwap_val * 100
            if spread > gr.get("max_spread_pct", 2.0):
                return False, f"vwap_spread ({spread:.2f}% > {gr['max_spread_pct']}%)"

    # 9. Sentiment
    gr = cfg_gr.get("sentiment", {})
    if gr.get("activo"):
        sent_score = row.get("sentiment_score")
        if sent_score is None:
            if gr.get("bloquear_sin_datos", False):
                return False, "sentiment_sin_datos"
        elif sent_score < gr.get("min_score", 0.0):
            return False, f"sentiment_negativo ({sent_score:.3f})"

    # 10. Horario mercado
    gr = cfg_gr.get("horario_mercado", {})
    if gr.get("activo"):
        if not row.get("is_market_open", False):
            return False, "fuera_horario_mercado"

    # 11. Posición abierta
    gr = cfg_gr.get("posicion_abierta", {})
    if gr.get("activo") and estado.get("posicion_abierta"):
        return False, "posicion_ya_abierta"

    # 12. Max posiciones
    gr = cfg_gr.get("max_posiciones", {})
    if gr.get("activo") and estado.get("n_posiciones", 0) >= gr.get("valor", 3):
        return False, f"max_posiciones ({estado['n_posiciones']})"

    # 13. Órdenes diarias max
    gr = cfg_gr.get("ordenes_diarias_max", {})
    if gr.get("activo") and estado.get("ordenes_hoy", 0) >= gr.get("valor", 5):
        return False, f"ordenes_diarias_max ({estado['ordenes_hoy']})"

    # 14. Circuit breaker
    gr = cfg_gr.get("circuit_breaker", {})
    if gr.get("activo"):
        try:
            from shared.db import query_one

            cfg_row = query_one("SELECT trading_enabled FROM config WHERE id = 1")
            if cfg_row and not cfg_row.get("trading_enabled", True):
                return False, "circuit_breaker_activo"
        except Exception as e:
            log.warning(
                f"Circuit breaker: no se pudo leer tabla 'config': {e}. "
                f"Asegúrate de que existe (ver scripts/schema_fixes.sql)."
            )

    return True, ""


def decide(
    ticker: str,
    score_final: float,
    row: pd.Series,
    cfg_gr: dict,
    estado: dict,
) -> dict:
    """
    Toma la decisión final para un ticker (backward compat con backtest).

    Args:
        ticker:      ticker a evaluar
        score_final: score ponderado de los modelos (0-100)
        row:         última vela
        cfg_gr:      configuración de guardarraíles
        estado:      estado actual del portfolio

    Returns:
        dict con decision, score_final, ejecutada, motivo_rechazo
    """
    ts = row.get("ts", datetime.now(UTC).isoformat())

    pasa, motivo = check_guardrails(row, score_final, cfg_gr, estado)

    score_threshold = cfg_gr.get("score_threshold", DEFAULT_SCORE_THRESHOLD)

    if not pasa:
        log.info(f"  {ticker}: RECHAZADO — {motivo}")
        return {
            "ts": str(ts),
            "ticker": ticker,
            "decision": "HOLD",
            "score_final": round(score_final, 2),
            "ejecutada": False,
            "motivo_rechazo": motivo,
        }

    decision = "BUY" if score_final >= score_threshold else "HOLD"
    log.info(f"  {ticker}: {decision} — score {score_final:.1f}")

    return {
        "ts": str(ts),
        "ticker": ticker,
        "decision": decision,
        "score_final": round(score_final, 2),
        "ejecutada": False,
        "motivo_rechazo": "",
    }
