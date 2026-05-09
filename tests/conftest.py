"""pytest configuration compartida."""

import pytest
import numpy as np
import pandas as pd


@pytest.fixture
def sample_ohlcv():
    """DataFrame OHLCV de ejemplo — 100 barras, 1 día."""
    dates = pd.date_range("2026-04-01 13:30", periods=100, freq="1min", tz="UTC")
    np.random.seed(42)
    close = 150 + np.cumsum(np.random.randn(100) * 0.1)

    return pd.DataFrame({
        "ts": dates,
        "open": close + np.random.randn(100) * 0.05,
        "high": close + np.abs(np.random.randn(100) * 0.1),
        "low": close - np.abs(np.random.randn(100) * 0.1),
        "close": close,
        "volume": np.random.randint(10000, 50000, 100),
    }).set_index("ts")


@pytest.fixture
def multiday_ohlcv():
    """DataFrame OHLCV de ejemplo — 780 barras, 2 días (390 barras/día).

    Crítico para testear VWAP con reset diario (F-89).
    """
    np.random.seed(123)

    day1 = pd.date_range("2026-04-01 13:30", periods=390, freq="1min", tz="UTC")
    day2 = pd.date_range("2026-04-02 13:30", periods=390, freq="1min", tz="UTC")
    dates = day1.append(day2)

    close = 200 + np.cumsum(np.random.randn(780) * 0.15)
    close = np.maximum(close, 50)  # evitar precios negativos

    return pd.DataFrame({
        "ts": dates,
        "ticker": "TEST",
        "open": close + np.random.randn(780) * 0.05,
        "high": close + np.abs(np.random.randn(780) * 0.2),
        "low": close - np.abs(np.random.randn(780) * 0.2),
        "close": close,
        "volume": np.random.randint(10000, 100000, 780),
    }).set_index("ts")
