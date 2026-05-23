"""
guardrails.py
─────────────
Guardrails del pipeline — PRE (mercado) y POST (score).

Pipeline Fase 6.11:
    PRE:  13 guardrails de mercado (sin score ML) — si no pasa → HOLD
    POST: 1 guardrail (score_minimo) — evaluado con score FINAL

Sesión 16 — backtest dual-dirección:
    check_guardrails_for_direction(): evalúa guardrails con config
    específica para LONG o SHORT. Usada por el motor de backtest
    para evaluar AMBAS direcciones en cada barra.

    Guardrails direccionales (6+1):
        RSI, MACD, Bollinger, EMA, VWAP, Sentiment + Score mínimo
    Guardrails comunes (7):
        Horario, Posición, Volumen, ATR, Máx posiciones, Órdenes, Circuit Breaker

También exporta check_guardrails() y decide() originales para
backward compat con backtest legacy y squawk pipeline.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd

log = logging.getLogger(__name__)

# F-21: threshold por defecto, sobreescribible desde yaml
DEFAULT_SCORE_THRESHOLD = 50


# ══════════════════════════════════════════════════════════════════════════════
# COMMON guardrails (idénticos para LONG y SHORT) — 7 guardrails
# ══════════════════════════════════════════════════════════════════════════════


def _check_common_guardrails(
    row: pd.Series,
    cfg_gr: dict,
    estado: dict,
) -> tuple[bool, str]:
    """
    Evalúa los 7 guardrails comunes (sin dirección).

    1. Horario mercado
    2. Posición abierta
    3. Volumen mínimo
    4. ATR volatilidad
    5. Máx posiciones
    6. Órdenes diarias
    7. Circuit breaker
    """
    # 1. Horario mercado
    gr = cfg_gr.get("horario_mercado", {})
    if gr.get("activo") or gr.get("on"):
        if not row.get("is_market_open", False):
            return False, "fuera_horario_mercado"

    # 2. Posición abierta
    gr = cfg_gr.get("posicion_abierta", {})
    if (gr.get("activo") or gr.get("on")) and estado.get("posicion_abierta"):
        return False, "posicion_ya_abierta"

    # 3. Volumen mínimo
    gr = cfg_gr.get("volumen", {})
    if gr.get("activo") or gr.get("on"):
        vol_norm = row.get("volume_norm")
        min_vol = gr.get("min_volume_norm", 0.5)
        if vol_norm is not None and vol_norm < min_vol:
            return False, f"volumen_bajo ({vol_norm:.2f} < {min_vol})"

    # 4. ATR volatilidad
    gr = cfg_gr.get("atr_volatilidad", {})
    if gr.get("activo") or gr.get("on"):
        atr_val = row.get("atr_14", 0)
        close = row.get("close", 1)
        atr_pct = atr_val / close * 100 if close > 0 else 0
        max_atr = gr.get("max_atr_pct", gr.get("max_multiplicador", 2.0))
        if atr_pct > max_atr:
            return False, f"atr_volatilidad ({atr_pct:.2f}% > {max_atr}%)"

    # 5. Máx posiciones
    gr = cfg_gr.get("max_posiciones", {})
    if (gr.get("activo") or gr.get("on")) and estado.get("n_posiciones", 0) >= gr.get("valor", 3):
        return False, f"max_posiciones ({estado['n_posiciones']})"

    # 6. Órdenes diarias max
    gr = cfg_gr.get("ordenes_diarias_max", {})
    if (gr.get("activo") or gr.get("on")) and estado.get("ordenes_hoy", 0) >= gr.get("valor", 5):
        return False, f"ordenes_diarias_max ({estado['ordenes_hoy']})"

    # 7. Circuit breaker
    gr = cfg_gr.get("circuit_breaker", {})
    if gr.get("activo") or gr.get("on"):
        try:
            from shared.db import query_one

            cfg_row = query_one("SELECT trading_enabled FROM config WHERE id = 1")
            if cfg_row and not cfg_row.get("trading_enabled", True):
                return False, "circuit_breaker_activo"
        except Exception as e:
            log.warning(f"Circuit breaker: no se pudo leer tabla 'config': {e}")

    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# DIRECTIONAL guardrails — LONG o SHORT — 6 guardrails
# ══════════════════════════════════════════════════════════════════════════════


def _check_directional_guardrails(
    row: pd.Series,
    cfg_gr: dict,
    direction: str,
) -> tuple[bool, str]:
    """
    Evalúa los 6 guardrails direccionales para LONG o SHORT.

    LONG busca condiciones de subida:
        RSI < X (sobreventa), MACD alcista, BB baja, precio > EMA,
        precio < VWAP (infravalorado), sentiment positivo

    SHORT busca condiciones de bajada:
        RSI > Y (sobrecompra), MACD bajista, BB alta, precio < EMA,
        precio > VWAP (sobrevalorado), sentiment negativo
    """
    is_long = direction == "long"

    # 1. RSI
    gr = cfg_gr.get("rsi", {})
    if gr.get("activo") or gr.get("on"):
        rsi = row.get("rsi_14")
        if rsi is not None:
            if is_long:
                # LONG: RSI debe ser < long_max (sobreventa → rebote)
                limit = gr.get("long_max", gr.get("compra_max", 30))
                if rsi > limit:
                    return False, f"rsi_long ({rsi:.1f} > {limit})"
            else:
                # SHORT: RSI debe ser > short_min (sobrecompra → caída)
                limit = gr.get("short_min", gr.get("venta_min", 70))
                if rsi < limit:
                    return False, f"rsi_short ({rsi:.1f} < {limit})"

    # 2. MACD
    gr = cfg_gr.get("macd", {})
    if gr.get("activo") or gr.get("on"):
        macd_line = row.get("macd_line", 0)
        macd_signal = row.get("macd_signal", 0)
        if is_long:
            # LONG: MACD line > signal (cruce alcista)
            if macd_line < macd_signal:
                return False, "macd_bajista_for_long"
        else:
            # SHORT: MACD line < signal (cruce bajista)
            if macd_line > macd_signal:
                return False, "macd_alcista_for_short"

    # 3. Bollinger Bands
    gr = cfg_gr.get("bollinger", {})
    if gr.get("activo") or gr.get("on"):
        bb_pct = row.get("bb_pct")
        if bb_pct is not None:
            if is_long:
                # LONG: bb_pct < X (banda baja → rebote)
                limit = gr.get("long_max", gr.get("compra_max", 0.2))
                if bb_pct > limit:
                    return False, f"bollinger_long ({bb_pct:.2f} > {limit})"
            else:
                # SHORT: bb_pct > Y (banda alta → caída)
                limit = gr.get("short_min", 0.8)
                if bb_pct < limit:
                    return False, f"bollinger_short ({bb_pct:.2f} < {limit})"

    # 4. EMA Tendencia
    gr = cfg_gr.get("ema_tendencia", {})
    if gr.get("activo") or gr.get("on"):
        close = row.get("close", 0)
        ema_21 = row.get("ema_21", 0)
        if is_long:
            # LONG: precio > EMA (tendencia alcista)
            if close < ema_21:
                return False, f"ema_bajista_for_long (close {close:.2f} < ema {ema_21:.2f})"
        else:
            # SHORT: precio < EMA (tendencia bajista)
            if close > ema_21:
                return False, f"ema_alcista_for_short (close {close:.2f} > ema {ema_21:.2f})"

    # 5. VWAP Spread
    gr = cfg_gr.get("vwap_spread", {})
    if gr.get("activo") or gr.get("on"):
        close = row.get("close", 0)
        vwap_val = row.get("vwap", 0)
        if vwap_val > 0:
            if is_long:
                # LONG: precio < VWAP (infravalorado)
                spread = (close - vwap_val) / vwap_val * 100
                max_spread = gr.get("max_spread_pct", 2.0)
                if spread > max_spread:
                    return False, f"vwap_long ({spread:.2f}% > {max_spread}%)"
            else:
                # SHORT: precio > VWAP (sobrevalorado)
                spread = (vwap_val - close) / vwap_val * 100
                max_spread = gr.get("max_spread_pct", 2.0)
                if spread > max_spread:
                    return False, f"vwap_short ({spread:.2f}% > {max_spread}%)"

    # 6. Sentiment
    gr = cfg_gr.get("sentiment", {})
    if gr.get("activo") or gr.get("on"):
        sent_score = row.get("sentiment_score")
        if sent_score is None:
            if gr.get("bloquear_sin_datos", False):
                return False, "sentiment_sin_datos"
        else:
            if is_long:
                # LONG: sentiment > X (positivo)
                min_score = gr.get("long_min", gr.get("min_score", 0.0))
                if sent_score < min_score:
                    return False, f"sentiment_negativo_for_long ({sent_score:.3f} < {min_score})"
            else:
                # SHORT: sentiment < -X (negativo)
                max_score = gr.get("short_max", 0.0)
                if sent_score > max_score:
                    return False, f"sentiment_positivo_for_short ({sent_score:.3f} > {max_score})"

    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST DUAL-DIRECCIÓN — función principal
# ══════════════════════════════════════════════════════════════════════════════


def check_guardrails_for_direction(
    row: pd.Series,
    cfg_gr: dict,
    estado: dict,
    direction: str,
) -> tuple[bool, str]:
    """
    Evalúa guardrails (comunes + direccionales) para una dirección.

    Usada por el motor de backtest dual-dirección para evaluar
    LONG y SHORT independientemente en cada barra.

    Args:
        row:       última vela
        cfg_gr:    configuración de guardrails
        estado:    estado del portfolio
        direction: "long" o "short"

    Returns:
        (pasa, motivo_rechazo)
    """
    # Primero: guardrails comunes
    pasa, motivo = _check_common_guardrails(row, cfg_gr, estado)
    if not pasa:
        return False, motivo

    # Segundo: guardrails direccionales
    pasa, motivo = _check_directional_guardrails(row, cfg_gr, direction)
    if not pasa:
        return False, motivo

    return True, ""


def check_score_for_direction(
    score: float,
    cfg_gr: dict,
    direction: str,
) -> tuple[bool, str]:
    """
    POST guardrail: evalúa si el score/confianza del modelo supera el
    umbral para la dirección indicada.

    Para LONG: el modelo debe predecir SUBIDA con confianza > umbral_long
    Para SHORT: el modelo debe predecir BAJADA con confianza > umbral_short

    Args:
        score:     probabilidad de SUBIDA del modelo (0-100)
        cfg_gr:    configuración de guardrails
        direction: "long" o "short"

    Returns:
        (pasa, motivo_rechazo)
    """
    gr = cfg_gr.get("score_minimo", {})

    if direction == "long":
        # LONG: score (P(subida)) debe ser alto
        threshold = gr.get("long_min", gr.get("valor", 60))
        if score < threshold:
            return False, f"score_long ({score:.1f} < {threshold})"
    else:
        # SHORT: score (P(subida)) debe ser bajo → P(bajada) alta
        # Convertimos: confianza_bajada = 100 - score
        threshold = gr.get("short_min", gr.get("valor", 60))
        confianza_bajada = 100 - score
        if confianza_bajada < threshold:
            return False, f"score_short (conf_bajada {confianza_bajada:.1f} < {threshold})"

    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# PRE guardrails (13, solo datos de mercado, sin score ML)
# Backward compat con squawk pipeline
# ══════════════════════════════════════════════════════════════════════════════


def check_guardrails_pre(
    row: pd.Series,
    cfg_gr: dict,
    estado: dict,
) -> tuple[bool, str]:
    """
    Evalúa los 13 guardrails de mercado SIN score ML.

    Usado en Paso 1 del pipeline multi-usuario (squawks).
    Si no pasa → HOLD, no se ejecuta inferencia.
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

    # 4. Bollinger — en PRE, bloquea si en extremos
    gr = cfg_gr.get("bollinger", {})
    if gr.get("activo"):
        bb_pct = row.get("bb_pct")
        if bb_pct is not None:
            if bb_pct > gr.get("compra_max", 0.95):
                return False, f"bollinger_techo ({bb_pct:.2f} > {gr['compra_max']})"
            if bb_pct < gr.get("venta_min", 0.05):
                return False, f"bollinger_suelo ({bb_pct:.2f} < {gr.get('venta_min', 0.05)})"

    # Common guardrails
    return _check_common_guardrails(row, cfg_gr, estado)


# ── POST guardrail (score_minimo) ─────────────────────────────────────


def check_guardrails_post(
    score_final: float,
    cfg_gr: dict,
) -> tuple[bool, str]:
    """
    Evalúa el guardrail POST (score_minimo) con el score FINAL.
    Backward compat con squawk pipeline.
    """
    score_threshold = cfg_gr.get("score_threshold", DEFAULT_SCORE_THRESHOLD)

    gr = cfg_gr.get("score_minimo", {})
    min_score = gr.get("valor", score_threshold)

    if gr.get("activo") and score_final < min_score:
        return False, f"score_minimo ({score_final:.1f} < {min_score})"

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
    Evalúa TODOS los guardarraíles (PRE + POST). Backward compat para
    backtest legacy y squawk pipeline.
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

    # Common guardrails (10-14)
    return _check_common_guardrails(row, cfg_gr, estado)


def decide(
    ticker: str,
    score_final: float,
    row: pd.Series,
    cfg_gr: dict,
    estado: dict,
) -> dict:
    """
    Toma la decisión final para un ticker (backward compat).
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
