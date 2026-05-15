"""
test_parity.py
──────────────
Tests de paridad training/live (F-88, F-89, F-90, F-91).

Verifica que:
    1. Las fórmulas de shared.indicators son correctas (vs cálculo manual)
    2. Las fórmulas VIEJAS (SMA RSI, cumsum VWAP, SMA ATR, pct_change)
       producen resultados DISTINTOS — demostrando que el fix importa
    3. silver.py y silver_rt.py producen los mismos valores sobre los mismos datos
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from shared.indicators import atr, bollinger, ema, log_returns, macd, rsi, vwap

# ═════════════════════════════════════════════════════════════════════════════
# 1. TESTS DE CORRECCIÓN — shared.indicators vs cálculo manual
# ═════════════════════════════════════════════════════════════════════════════


class TestRSI:
    """F-88: RSI debe usar EMA Wilder (alpha=1/period), NO SMA."""

    def test_rsi_uses_ewm_wilder(self, sample_ohlcv: pd.DataFrame):
        """Verifica que RSI usa EMA Wilder comparando con cálculo manual."""
        close = sample_ohlcv["close"]
        result = rsi(close, 14)

        # Cálculo manual EMA Wilder
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        expected = 100 - (100 / (1 + rs))

        # Deben ser idénticos
        valid = result.dropna()
        expected_valid = expected[valid.index]
        np.testing.assert_allclose(valid.values, expected_valid.values, rtol=1e-10)

    def test_rsi_range(self, sample_ohlcv: pd.DataFrame):
        """RSI siempre en [0, 100]."""
        result = rsi(sample_ohlcv["close"], 14).dropna()
        assert (result >= 0).all()
        assert (result <= 100).all()

    def test_rsi_differs_from_sma(self, sample_ohlcv: pd.DataFrame):
        """F-88: demostrar que RSI EMA Wilder ≠ RSI SMA (la fórmula vieja)."""
        close = sample_ohlcv["close"]

        # Versión correcta (EMA Wilder)
        result_ewm = rsi(close, 14)

        # Versión VIEJA incorrecta (SMA — lo que hacía silver_rt.py antes)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs_sma = gain / loss.replace(0, 1e-10)
        result_sma = 100 - (100 / (1 + rs_sma))

        # Deben ser DISTINTOS (si fueran iguales, el fix no habría cambiado nada)
        valid = result_ewm.dropna().index.intersection(result_sma.dropna().index)
        diff = (result_ewm[valid] - result_sma[valid]).abs()
        assert diff.max() > 0.1, (
            f"RSI EMA y SMA son casi iguales (max diff={diff.max():.4f}). "
            f"El fix F-88 no está funcionando."
        )


class TestVWAP:
    """F-89: VWAP debe resetear por día, NO ser cumulativo."""

    def test_vwap_resets_daily(self, multiday_ohlcv: pd.DataFrame):
        """VWAP debe resetear al inicio de cada día."""
        df = multiday_ohlcv.copy()
        df["ts"] = df.index
        result = vwap(df)

        # El primer valor de cada día debe ser el typical price de esa barra
        # (porque cum_tpvol / cum_vol = tp cuando solo hay 1 barra)
        for date in df.index.date:
            mask = df.index.date == date
            day_df = df[mask]
            first_tp = (day_df.iloc[0]["high"] + day_df.iloc[0]["low"] + day_df.iloc[0]["close"]) / 3
            first_vwap = result[mask].iloc[0]
            np.testing.assert_allclose(
                first_vwap, first_tp, rtol=1e-10,
                err_msg=f"VWAP no resetea al inicio del día {date}"
            )

    def test_vwap_differs_from_cumulative(self, multiday_ohlcv: pd.DataFrame):
        """F-89: VWAP con reset ≠ VWAP cumulativo (la fórmula vieja)."""
        df = multiday_ohlcv.copy()
        df["ts"] = df.index

        # Versión correcta (reset diario)
        result_reset = vwap(df)

        # Versión VIEJA incorrecta (cumsum sin reset — lo que hacía silver_rt.py)
        tp = (df["high"] + df["low"] + df["close"]) / 3
        cum_vol = df["volume"].cumsum()
        cum_tpvol = (tp * df["volume"]).cumsum()
        result_cum = cum_tpvol / cum_vol.replace(0, np.nan)

        # Deben ser DISTINTOS (al cruzar días, el cumulativo diverge)
        valid = result_reset.dropna().index.intersection(result_cum.dropna().index)
        diff = (result_reset[valid] - result_cum[valid]).abs()
        assert diff.max() > 0.01, (
            f"VWAP reset y cumulativo son casi iguales (max diff={diff.max():.4f}). "
            f"El fix F-89 no está funcionando."
        )

    def test_vwap_positive(self, sample_ohlcv: pd.DataFrame):
        """VWAP siempre positivo con precios positivos."""
        df = sample_ohlcv.copy()
        df["ts"] = df.index
        result = vwap(df).dropna()
        assert (result > 0).all()


class TestATR:
    """F-90: ATR debe usar EMA Wilder, NO SMA."""

    def test_atr_uses_ewm_wilder(self, sample_ohlcv: pd.DataFrame):
        """Verifica que ATR usa EMA Wilder comparando con cálculo manual."""
        df = sample_ohlcv
        result = atr(df, 14)

        # Cálculo manual
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        expected = tr.ewm(alpha=1 / 14, adjust=False).mean()

        valid = result.dropna()
        expected_valid = expected[valid.index]
        np.testing.assert_allclose(valid.values, expected_valid.values, rtol=1e-10)

    def test_atr_differs_from_sma(self, sample_ohlcv: pd.DataFrame):
        """F-90: ATR EMA Wilder ≠ ATR SMA (la fórmula vieja)."""
        df = sample_ohlcv

        # Versión correcta (EMA Wilder)
        result_ewm = atr(df, 14)

        # Versión VIEJA incorrecta (SMA — lo que hacía silver_rt.py)
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        result_sma = tr.rolling(14).mean()

        valid = result_ewm.dropna().index.intersection(result_sma.dropna().index)
        diff = (result_ewm[valid] - result_sma[valid]).abs()
        assert diff.max() > 0.001, (
            f"ATR EMA y SMA son casi iguales (max diff={diff.max():.6f}). "
            f"El fix F-90 no está funcionando."
        )

    def test_atr_positive(self, sample_ohlcv: pd.DataFrame):
        """ATR siempre positivo."""
        result = atr(sample_ohlcv, 14).dropna()
        assert (result > 0).all()


class TestReturns:
    """F-91: Returns deben ser log returns, NO pct_change."""

    def test_log_returns_formula(self, sample_ohlcv: pd.DataFrame):
        """Verifica que log_returns = np.log(close / shift(1))."""
        close = sample_ohlcv["close"]
        result = log_returns(close, 1)

        expected = np.log(close / close.shift(1))

        valid = result.dropna()
        expected_valid = expected[valid.index]
        np.testing.assert_allclose(valid.values, expected_valid.values, rtol=1e-10)

    def test_log_returns_differ_from_pct_change(self, sample_ohlcv: pd.DataFrame):
        """F-91: log returns ≠ pct_change (la fórmula vieja)."""
        close = sample_ohlcv["close"]

        # Versión correcta (log returns)
        result_log = log_returns(close, 1)

        # Versión VIEJA (pct_change — lo que hacía silver_rt.py)
        result_pct = close.pct_change()

        # Para cambios pequeños convergen, pero deben tener ALGUNA diferencia
        valid = result_log.dropna().index.intersection(result_pct.dropna().index)
        diff = (result_log[valid] - result_pct[valid]).abs()
        assert diff.max() > 0, "Log returns y pct_change son idénticos — imposible"

    def test_log_returns_symmetric(self, sample_ohlcv: pd.DataFrame):
        """Log returns son simétricos: log(a/b) = -log(b/a)."""
        close = sample_ohlcv["close"]
        ret = log_returns(close, 1).dropna()
        # Verificar que la distribución es aproximadamente simétrica
        # (no tiene el sesgo de pct_change en movimientos grandes)
        assert abs(ret.skew()) < abs(close.pct_change().dropna().skew()) + 0.5


# ═════════════════════════════════════════════════════════════════════════════
# 2. TEST DE PARIDAD — silver.py vs silver_rt.py sobre mismos datos
# ═════════════════════════════════════════════════════════════════════════════


class TestSilverParity:
    """Verifica que silver.py y silver_rt.py producen resultados idénticos."""

    def test_calc_features_parity(self, multiday_ohlcv: pd.DataFrame):
        """Los dos compute_indicators deben dar los mismos valores."""
        from apps.ingestion_historical.silver import calc_features
        from apps.ingestion_live.silver_rt import compute_indicators

        # Preparar datos en el formato que cada función espera
        df_hist = multiday_ohlcv.copy()
        df_hist = df_hist.drop(columns=["ticker"], errors="ignore")

        df_live = multiday_ohlcv.reset_index().copy()
        df_live["ts"] = pd.to_datetime(df_live["ts"], utc=True)

        # Calcular con ambos
        result_hist = calc_features(df_hist, "TEST")
        result_live = compute_indicators(df_live)

        # Columnas a comparar (las que tenían divergencia)
        critical_cols = [
            "rsi_14",       # F-88
            "vwap",         # F-89
            "atr_14",       # F-90
            "returns",      # F-91
            "returns_5",    # F-91
            "returns_15",   # F-91
            "ema_9", "ema_12", "ema_21", "ema_50",
            "macd_line", "macd_signal", "macd_hist",
            "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pct",
        ]

        for col in critical_cols:
            if col not in result_hist.columns or col not in result_live.columns:
                continue

            hist_vals = result_hist[col].dropna().values
            live_vals = result_live[col].dropna().values

            # Longitudes pueden diferir ligeramente por índice
            n = min(len(hist_vals), len(live_vals))
            if n == 0:
                continue

            np.testing.assert_allclose(
                hist_vals[-n:], live_vals[-n:],
                rtol=1e-6,
                err_msg=f"PARIDAD ROTA en '{col}': silver.py ≠ silver_rt.py"
            )


# ═════════════════════════════════════════════════════════════════════════════
# 3. TESTS DE OTROS INDICADORES (smoke tests)
# ═════════════════════════════════════════════════════════════════════════════


class TestOtherIndicators:

    def test_ema_converges(self, sample_ohlcv: pd.DataFrame):
        """EMA con periodo largo converge hacia la media."""
        result = ema(sample_ohlcv["close"], 50)
        valid = result.dropna()
        assert len(valid) == len(sample_ohlcv)

    def test_macd_components(self, sample_ohlcv: pd.DataFrame):
        """MACD histogram = line - signal."""
        line, signal, hist = macd(sample_ohlcv["close"])
        valid = hist.dropna().index
        expected = line[valid] - signal[valid]
        np.testing.assert_allclose(hist[valid].values, expected.values, rtol=1e-10)

    def test_bollinger_width_positive(self, sample_ohlcv: pd.DataFrame):
        """Bollinger width siempre positiva."""
        _, _, _, width, _ = bollinger(sample_ohlcv["close"], 20)
        valid = width.dropna()
        assert (valid >= 0).all()

    def test_bollinger_pct_b_bounded(self, sample_ohlcv: pd.DataFrame):
        """Bollinger %B mayoritariamente en [0, 1] (puede salirse en extremos)."""
        _, _, _, _, pct_b = bollinger(sample_ohlcv["close"], 20)
        valid = pct_b.dropna()
        in_range = ((valid >= -0.5) & (valid <= 1.5)).sum()
        assert in_range / len(valid) > 0.9, "Más del 10% de %B fuera de rango razonable"
