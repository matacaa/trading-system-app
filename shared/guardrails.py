"""
guardrails.py
─────────────
check_guardrails() unificado — usado tanto por el backtest
(apps/ml_sandbox/backtest.py) como por el live (apps/trading_engine/).

Contiene los 14 guardrails del engine.py original, incluyendo
atr_volatilidad y circuit_breaker que backtest.py no tenía (F-17).

Cambios respecto a los originales:
    - F-17: backtest ahora tiene los 14 guardrails (antes solo 12)
    - F-18: circuit_breaker usa shared.db.sb (antes creaba cliente por iteración)
    - F-19: circuit_breaker falla gracefully con warning
    - F-21: score_threshold configurable desde yaml (antes hardcoded 50)
    - F-22: atr_volatilidad renombrado a max_atr_pct (antes max_multiplicador)
    - F-23: is_market_open default False (fail-closed, antes True)
    - F-24: sentiment None se trata como "sin datos" configurable
    - decide() también unificada aquí (usada por backtest y live)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger(__name__)

# F-21: threshold por defecto, sobreescribible desde yaml
DEFAULT_SCORE_THRESHOLD = 50


def check_guardrails(
    row: pd.Series,
    score: float,
    cfg_gr: dict,
    estado: dict,
) -> tuple[bool, str]:
    """
    Evalúa los guardarraíles para una vela.

    Args:
        row:    última vela de silver_features (o silver_features_rt en live)
        score:  score ponderado de los modelos (0-100)
        cfg_gr: configuración de guardarraíles del yaml
        estado: estado actual del portfolio

    Returns:
        (pasa, motivo_rechazo)
    """
    # F-21: score threshold configurable desde yaml
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

    # 5. ATR volatilidad (F-17: faltaba en backtest)
    # F-22: renombrado de max_multiplicador a max_atr_pct (acepta ambos por compat)
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
    # F-24: None se trata como "sin datos". Si bloquear_sin_datos=true, bloquea.
    gr = cfg_gr.get("sentiment", {})
    if gr.get("activo"):
        sent_score = row.get("sentiment_score")
        if sent_score is None:
            if gr.get("bloquear_sin_datos", False):
                return False, "sentiment_sin_datos"
        elif sent_score < gr.get("min_score", 0.0):
            return False, f"sentiment_negativo ({sent_score:.3f})"

    # 10. Horario mercado
    # F-23: default False (fail-closed — si no hay dato, asume cerrado)
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

    # 14. Circuit breaker (F-17: faltaba en backtest, F-18/F-19: usa sb singleton)
    gr = cfg_gr.get("circuit_breaker", {})
    if gr.get("activo"):
        try:
            from shared.db import sb

            resp = (
                sb.table("config")
                .select("trading_enabled")
                .eq("id", 1)
                .single()
                .execute()
            )
            if resp.data and not resp.data.get("trading_enabled", True):
                return False, "circuit_breaker_activo"
        except Exception as e:
            # F-19: si la tabla no existe, log warning claro
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
    Toma la decisión final para un ticker.

    Args:
        ticker:      ticker a evaluar
        score_final: score ponderado de los modelos (0-100)
        row:         última vela
        cfg_gr:      configuración de guardarraíles
        estado:      estado actual del portfolio

    Returns:
        dict con decision, score_final, ejecutada, motivo_rechazo
    """
    ts = row.get("ts", datetime.now(timezone.utc).isoformat())

    pasa, motivo = check_guardrails(row, score_final, cfg_gr, estado)

    # F-21: score_threshold configurable
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
