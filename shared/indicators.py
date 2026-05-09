"""
indicators.py
─────────────
Indicadores técnicos unificados. Esta es la FUENTE ÚNICA de verdad
para el cálculo de features, usada tanto por el pipeline histórico
(apps/ingestion_historical/silver.py) como por el live
(apps/ingestion_live/silver_rt.py).

Resuelve los issues F-88, F-89, F-90, F-91 del informe de Fase 2
(divergencia de fórmulas entre training y live).

Fórmulas usadas (las "canónicas" del silver.py original):
    - RSI: EMA Wilder (alpha=1/period)
    - ATR: EMA Wilder
    - MACD: EMA 12/26/9 estándar
    - Bollinger: SMA 20 + 2 std
    - VWAP: reset diario (groupby por fecha)
    - Returns: log returns np.log(close/shift(1))

Implementado en Bloque 4. silver.py y silver_rt.py ya consumen
estas funciones (paridad training/live resuelta).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average estándar (adjust=False)."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI Wilder (EMA-based). Estándar de la literatura técnica.
    
    Tanto silver.py como silver_rt.py usan esta función (paridad resuelta).
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD estándar (12, 26, 9). Retorna (line, signal, histogram)."""
    ema_fast = ema(close, 12)
    ema_slow = ema(close, 26)
    macd_line = ema_fast - ema_slow
    macd_sig = ema(macd_line, 9)
    macd_hist = macd_line - macd_sig
    return macd_line, macd_sig, macd_hist


def bollinger(
    close: pd.Series, period: int = 20, std_multiplier: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands (period=20, std=2). Retorna (upper, middle, lower, width, pct_b)."""
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + std_multiplier * std
    lower = middle - std_multiplier * std
    width = (upper - lower) / middle.replace(0, np.nan)
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return upper, middle, lower, width, pct_b


def vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP con reset diario (groupby por fecha).
    
    Tanto silver.py como silver_rt.py usan esta función (paridad resuelta).
    df debe tener columnas: high, low, close, volume, y un índice datetime o columna 'ts'.
    """
    df = df.copy()
    if isinstance(df.index, pd.DatetimeIndex):
        df["_date"] = df.index.date
    elif "ts" in df.columns:
        df["_date"] = pd.to_datetime(df["ts"]).dt.date
    else:
        raise ValueError("vwap() requiere índice DatetimeIndex o columna 'ts'")
    df["_tp"] = (df["high"] + df["low"] + df["close"]) / 3
    df["_tpvol"] = df["_tp"] * df["volume"]
    cum_tpvol = df.groupby("_date")["_tpvol"].cumsum()
    cum_vol = df.groupby("_date")["volume"].cumsum()
    return cum_tpvol / cum_vol.replace(0, np.nan)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range Wilder (EMA-based).
    
    Tanto silver.py como silver_rt.py usan esta función (paridad resuelta).
    df debe tener columnas: high, low, close.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def log_returns(close: pd.Series, period: int = 1) -> pd.Series:
    """Log returns. np.log(close / shift(period)).
    
    Tanto silver.py como silver_rt.py usan esta función (paridad resuelta).
    """
    return np.log(close / close.shift(period))


# Mejoras pendientes:
# - F-93 ideal: per-bar FinBERT en RT (requiere refactor de finbert_rt pipeline)


def is_market_open(ts_series: pd.Series) -> pd.Series:
    """Detecta si cada timestamp cae dentro del horario NYSE.

    Usa exchange_calendars para manejar DST (F-76) y festivos US (F-77).
    Retorna 1 si abierto, 0 si cerrado.

    Args:
        ts_series: Series de timestamps UTC (datetime64[ns, UTC])
    """
    import exchange_calendars as xcals

    nyse = xcals.get_calendar("XNYS")

    # Rango de fechas a consultar
    dates = pd.to_datetime(ts_series).dt.date.unique()
    start = pd.Timestamp(min(dates))
    end = pd.Timestamp(max(dates)) + pd.Timedelta(days=1)

    # Obtener sesiones y horarios
    schedule = nyse.sessions_in_range(start, end)
    schedule_set = set(schedule.date)

    result = pd.Series(0, index=ts_series.index, dtype=int)

    for date in dates:
        if date not in schedule_set:
            # Festivo o fin de semana → cerrado
            continue

        session = pd.Timestamp(date)
        try:
            market_open = nyse.session_open(session)
            market_close = nyse.session_close(session)
        except Exception:
            continue

        mask = (
            (pd.to_datetime(ts_series).dt.date == date)
            & (pd.to_datetime(ts_series) >= market_open)
            & (pd.to_datetime(ts_series) < market_close)
        )
        result[mask] = 1

    return result


def enrich_sentiment(
    df: pd.DataFrame,
    ticker: str,
    news_table: str = "silver_news_alpaca",
    window_minutes: int = 15,
) -> pd.DataFrame:
    """Asigna sentiment por barra usando ventana temporal (F-93).

    Para cada vela, busca la noticia más reciente en los últimos
    `window_minutes` minutos y asigna su sentiment.

    Resuelve F-93: antes silver_rt.py propagaba el mismo sentiment
    a todas las barras, eliminando la señal temporal para LSTM/GRU/Transformer.

    Args:
        df:             DataFrame con índice datetime UTC
        ticker:         ticker a consultar
        news_table:     tabla de noticias con sentiment (silver_news_alpaca)
        window_minutes: ventana de búsqueda hacia atrás en minutos

    Returns:
        DataFrame con sentiment_label y sentiment_score por barra
    """
    from shared.db import sb

    df = df.copy()
    df["sentiment_label"] = None
    df["sentiment_score"] = None

    # Determinar rango temporal
    if hasattr(df.index, "min"):
        ts_min, ts_max = df.index.min(), df.index.max()
    elif "ts" in df.columns:
        ts_min = pd.to_datetime(df["ts"]).min()
        ts_max = pd.to_datetime(df["ts"]).max()
    else:
        return df

    try:
        resp = (
            sb.table(news_table)
            .select("published_at,sentiment_label,sentiment_score")
            .eq("ticker", ticker)
            .gte("published_at", (ts_min - pd.Timedelta(minutes=window_minutes)).isoformat())
            .lte("published_at", ts_max.isoformat())
            .order("published_at")
            .execute()
        )
        news_data = resp.data or []
    except Exception:
        return df

    if not news_data:
        return df

    news_df = pd.DataFrame(news_data)
    news_df["published_at"] = pd.to_datetime(news_df["published_at"], utc=True)
    news_df = news_df.sort_values("published_at")

    # F-96: merge_asof vectorizado en vez de loop O(n×m)
    timestamps = df.index if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df["ts"])
    bar_df = pd.DataFrame({"_bar_ts": timestamps}).reset_index(drop=True)
    bar_df["_bar_ts"] = pd.to_datetime(bar_df["_bar_ts"], utc=True)
    bar_df = bar_df.sort_values("_bar_ts")

    merged = pd.merge_asof(
        bar_df,
        news_df[["published_at", "sentiment_label", "sentiment_score"]].rename(
            columns={"published_at": "_bar_ts"}
        ),
        on="_bar_ts",
        direction="backward",
        tolerance=pd.Timedelta(minutes=window_minutes),
    )

    df["sentiment_label"] = merged["sentiment_label"].values
    df["sentiment_score"] = merged["sentiment_score"].values

    return df
