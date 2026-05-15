"""
silver_rt.py
────────────
Calcula indicadores técnicos sobre las barras RT
y los guarda en silver_features_rt en PostgreSQL.

CAMBIO CRÍTICO respecto al original:
    Todos los indicadores ahora vienen de shared.indicators,
    que es la MISMA fuente que usa el pipeline histórico.
    Esto resuelve la divergencia de paridad training/live:

    - F-88: RSI ahora usa EMA Wilder (antes: SMA)
    - F-89: VWAP ahora resetea por día (antes: cumsum sin reset)
    - F-90: ATR ahora usa EMA Wilder (antes: SMA)
    - F-91: Returns ahora usa log returns (antes: pct_change)

Uso:
    from apps.ingestion_live.silver_rt import compute_silver_rt
    df = compute_silver_rt(tickers=["AAPL"], timeframe="1m")
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from shared.db import query, upsert
from shared.indicators import (
    atr,
    bollinger,
    ema,
    enrich_sentiment,
    is_market_open,
    log_returns,
    macd,
    rsi,
    vwap,
)

log = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula indicadores técnicos usando shared.indicators (fuente canónica).

    F-84: esta función asume un DataFrame de UN SOLO ticker.
    Si se pasan múltiples tickers, los EMAs/RSI/etc se mezclarían.

    El DataFrame debe tener columnas: ts, ticker, open, high, low, close, volume.
    """
    # F-84: validar que es single-ticker
    if "ticker" in df.columns and df["ticker"].nunique() > 1:
        raise ValueError(
            f"compute_indicators espera un solo ticker, "
            f"recibió {df['ticker'].nunique()}: {df['ticker'].unique().tolist()}"
        )

    df = df.sort_values("ts").copy()

    close = df["close"]
    volume = df["volume"]

    # EMAs
    df["ema_9"] = ema(close, 9)
    df["ema_12"] = ema(close, 12)
    df["ema_21"] = ema(close, 21)
    df["ema_50"] = ema(close, 50)

    # RSI — F-88: ahora EMA Wilder (canónico), antes era SMA
    df["rsi_14"] = rsi(close, 14)

    # MACD
    df["macd_line"], df["macd_signal"], df["macd_hist"] = macd(close)

    # Bollinger Bands
    df["bb_upper"], df["bb_middle"], df["bb_lower"], df["bb_width"], df["bb_pct"] = (
        bollinger(close, 20)
    )

    # VWAP — F-89: ahora reset diario (canónico), antes era cumsum sin reset
    df["vwap"] = vwap(df)

    # ATR — F-90: ahora EMA Wilder (canónico), antes era SMA
    df["atr_14"] = atr(df, 14)

    # Returns — F-91: ahora log returns (canónico), antes era pct_change
    df["returns"] = log_returns(close, 1)
    df["returns_5"] = log_returns(close, 5)
    df["returns_15"] = log_returns(close, 15)
    df["range_pct"] = (df["high"] - df["low"]) / close.replace(0, np.nan)

    # Volume norm
    vol_mean = volume.rolling(20).mean().replace(0, np.nan)
    df["volume_norm"] = volume / vol_mean

    # Time features
    df["hour"] = df["ts"].dt.hour
    df["dayofweek"] = df["ts"].dt.dayofweek

    # Market open (F-76: DST, F-77: festivos via exchange_calendars)
    df["is_market_open"] = is_market_open(df["ts"])

    return df


def compute_silver_rt(
    tickers: list[str],
    timeframe: str = "1m",
) -> pd.DataFrame:
    """
    Lee raw_ohlcv_rt, calcula indicadores y guarda en silver_features_rt.

    N-10: parámetro sentiment eliminado — enrich_sentiment consulta
    PostgreSQL directamente por barra (ventana 15min).

    Args:
        tickers:   lista de tickers
        timeframe: granularidad

    Returns:
        DataFrame con features calculadas
    """
    all_dfs = []

    for ticker in tickers:
        try:
            # Leer raw_ohlcv_rt
            rows_data = query(
                """SELECT ticker, timeframe, ts, open, high, low, close, volume
                   FROM raw_ohlcv_rt WHERE ticker = %s AND timeframe = %s
                   ORDER BY ts DESC LIMIT 200""",
                [ticker, timeframe],
            )

            if not rows_data:
                log.warning(f"  {ticker}: sin datos en raw_ohlcv_rt")
                continue

            df = pd.DataFrame(rows_data)
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            df = df.sort_values("ts").reset_index(drop=True)

            # Calcular indicadores (ahora con shared.indicators)
            df = compute_indicators(df)

            # Añadir sentiment por barra (F-93: antes era constante para todas)
            df = enrich_sentiment(df, ticker, news_table="silver_news_alpaca")
            label_map = {"positive": 1, "neutral": 0, "negative": -1}
            df["sentiment_label_encoded"] = df["sentiment_label"].map(label_map).fillna(0).astype(int)

            # I-02: news_count features (paridad con silver histórico)
            df["news_count_1h"] = 0
            df["news_count_24h"] = 0
            df["has_news"] = 0
            try:
                ts_min = df["ts"].min() - pd.Timedelta(hours=24)
                ts_max = df["ts"].max()
                news_rows = query(
                    """SELECT published_at FROM silver_news_alpaca
                       WHERE ticker = %s AND published_at >= %s AND published_at <= %s
                       ORDER BY published_at""",
                    [ticker, ts_min.isoformat(), ts_max.isoformat()],
                )
                if news_rows:
                    news_ts = pd.to_datetime(
                        [n["published_at"] for n in news_rows], utc=True
                    ).sort_values()
                    for i, ts_val in enumerate(df["ts"]):
                        c1 = int(((news_ts >= ts_val - pd.Timedelta(hours=1)) & (news_ts <= ts_val)).sum())
                        c24 = int(((news_ts >= ts_val - pd.Timedelta(hours=24)) & (news_ts <= ts_val)).sum())
                        df.loc[df.index[i], "news_count_1h"] = c1
                        df.loc[df.index[i], "news_count_24h"] = c24
                        df.loc[df.index[i], "has_news"] = 1 if c1 > 0 else 0
            except Exception as e:
                log.warning(f"  {ticker}: error calculando news_count: {e}")

            # F-82: solo guardar las últimas N barras nuevas (no las 100)
            # Consultamos la última barra guardada para este ticker
            try:
                last_rows = query(
                    """SELECT ts FROM silver_features_rt
                       WHERE ticker = %s ORDER BY ts DESC LIMIT 1""",
                    [ticker],
                )
                if last_rows:
                    last_saved_ts = pd.to_datetime(last_rows[0]["ts"], utc=True)
                    df_new = df[df["ts"] > last_saved_ts].copy()
                else:
                    df_new = df.tail(100).copy()
            except Exception:
                df_new = df.tail(100).copy()

            if df_new.empty:
                log.info(f"  {ticker}: sin barras nuevas")
                all_dfs.append(df)
                continue

            # Columnas a guardar
            cols = [
                "ts", "ticker", "open", "high", "low", "close", "volume",
                "ema_9", "ema_12", "ema_21", "ema_50",
                "rsi_14", "macd_line", "macd_signal", "macd_hist",
                "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pct",
                "vwap", "atr_14",
                "returns", "returns_5", "returns_15", "range_pct", "volume_norm",
                "hour", "dayofweek", "is_market_open",
                "sentiment_label", "sentiment_score", "sentiment_label_encoded",
                "news_count_1h", "news_count_24h", "has_news",
            ]

            rows = df_new[cols].copy()
            rows["ts"] = rows["ts"].astype(str)
            rows = rows.replace({np.nan: None, np.inf: None, -np.inf: None})

            records = rows.to_dict(orient="records")
            if records:
                upsert("silver_features_rt", records, conflict="ticker,ts")
                log.info(
                    f"  {ticker}: {len(records)} barras nuevas guardadas en silver_features_rt"
                )

            all_dfs.append(df)

        except Exception as e:
            log.error(f"  Error procesando {ticker}: {e}")

    return pd.concat(all_dfs) if all_dfs else pd.DataFrame()
