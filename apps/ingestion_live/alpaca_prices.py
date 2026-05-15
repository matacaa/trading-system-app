"""
alpaca_prices.py
────────────────
Descarga las últimas N barras de precio desde Alpaca
y las guarda en raw_ohlcv_rt en Supabase.

Uso:
    from apps.ingestion_live.alpaca_prices import fetch_prices
    fetch_prices(tickers=["AAPL"], timeframe="1m", bars=100)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from shared.config import cfg
from shared.db import upsert

log = logging.getLogger(__name__)

_TIMEFRAMES = {
    "1m": TimeFrame(1, TimeFrameUnit.Minute),
    "5m": TimeFrame(5, TimeFrameUnit.Minute),
    "15m": TimeFrame(15, TimeFrameUnit.Minute),
}


def fetch_prices(
    tickers: list[str],
    timeframe: str = "1m",
    bars: int = 100,
) -> pd.DataFrame:
    """Descarga últimas N barras y guarda en raw_ohlcv_rt."""
    if timeframe not in _TIMEFRAMES:
        raise ValueError(f"Timeframe no soportado: {timeframe}")

    client = StockHistoricalDataClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)

    end = datetime.now(UTC)
    start = end - timedelta(minutes=bars * int(timeframe.replace("m", "")))

    log.info(f"Descargando {bars} barras {timeframe} para {tickers}")

    request = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=_TIMEFRAMES[timeframe],
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )

    bars_data = client.get_stock_bars(request)
    df = bars_data.df.reset_index()

    if df.empty:
        log.warning("No se obtuvieron barras de Alpaca")
        return df

    df = df.rename(columns={"symbol": "ticker", "timestamp": "ts"})
    df["timeframe"] = timeframe
    df["fetched_at"] = datetime.now(UTC).isoformat()

    rows = df[["ticker", "timeframe", "ts", "open", "high", "low", "close", "volume", "fetched_at"]].copy()
    rows["ts"] = rows["ts"].astype(str)

    records = rows.to_dict(orient="records")
    if records:
        upsert("raw_ohlcv_rt", records, conflict="ticker,timeframe,ts")
        log.info(f"  {len(records)} barras guardadas en raw_ohlcv_rt")

    return df
