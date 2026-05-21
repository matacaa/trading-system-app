"""
test_indicators.py
──────────────────
Tests unitarios de los indicadores técnicos compartidos.
Crítico para garantizar que el refactor de paridad training/live (F-88..F-91)
funciona correctamente.

TODO Fase 3.4: implementar tests comparando training vs live.
"""

from __future__ import annotations

import pandas as pd


def test_ema_smoke(sample_ohlcv: pd.DataFrame) -> None:
    """Smoke test: ema() no rompe con un df válido."""
    from shared.indicators import ema
    result = ema(sample_ohlcv["close"], 9)
    assert len(result) == len(sample_ohlcv)
    assert result.notna().sum() > 0  # al menos un valor no-NaN


def test_rsi_range(sample_ohlcv: pd.DataFrame) -> None:
    """RSI debe estar en rango [0, 100]."""
    from shared.indicators import rsi
    result = rsi(sample_ohlcv["close"], 14)
    valid = result.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_vwap_positive(sample_ohlcv: pd.DataFrame) -> None:
    """VWAP siempre positivo con precios positivos."""
    from shared.indicators import vwap
    result = vwap(sample_ohlcv)
    valid = result.dropna()
    assert (valid > 0).all()


# TODO Fase 3.4:
# - test_rsi_matches_pandas_ta_reference
# - test_vwap_resets_daily (crítico para paridad)
# - test_atr_ewm_wilder
