"""
downloader.py
─────────────
Descarga OHLCV desde yfinance por bloques.

yfinance tiene límites por intervalo:
    - 1m: máximo 7 días por request
    - 5m/15m: máximo 60 días por request
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# Máximo de días por request según intervalo
MAX_DAYS = {"1m": 7, "5m": 60, "15m": 60}


def get_date_blocks(
    interval: str, days: int = 7
) -> list[tuple[datetime, datetime]]:
    """Genera bloques de fechas respetando los límites de yfinance."""
    max_days = MAX_DAYS.get(interval, 7)
    block_days = min(days, max_days)

    now = datetime.now(tz=UTC)
    start = now - timedelta(days=days)

    blocks = []
    current = start
    while current < now:
        end = min(current + timedelta(days=block_days), now)
        blocks.append((current, end))
        current = end

    return blocks


def download_block(
    ticker: str,
    start: datetime,
    end: datetime,
    interval: str,
) -> pd.DataFrame:
    """
    Descarga un bloque de OHLCV desde yfinance.

    Returns:
        DataFrame con columnas: ts, open, high, low, close, volume, ticker
    """
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=interval,
        )

        if df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df = df.rename(columns={
            "Datetime": "ts", "Date": "ts",
            "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })

        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df["ticker"] = ticker

        return df[["ts", "ticker", "open", "high", "low", "close", "volume"]]

    except Exception as e:
        log.error(f"Error descargando {ticker} [{interval}]: {e}")
        return pd.DataFrame()
