"""Endpoints de tickers y velas."""
from fastapi import APIRouter

from shared.db import query
from shared.symbols import ALL_SYMBOLS

router = APIRouter()

@router.get("/tickers")
async def list_tickers():
    tickers_with_data: set[str] = set()
    for ticker in ALL_SYMBOLS:
        try:
            rows = query(
                "SELECT ticker FROM silver_features_1m WHERE ticker = %s LIMIT 1",
                [ticker],
            )
            if rows:
                tickers_with_data.add(ticker)
        except Exception:
            pass
    return {"tickers": [
        {"ticker": t, "name": n, "has_data": t in tickers_with_data}
        for t, n in ALL_SYMBOLS.items()
    ]}

@router.get("/candles")
async def get_candles(ticker: str = "AAPL", limit: int = 200):
    rows = query(
        """SELECT ts, open, high, low, close, volume
           FROM raw_ohlcv_rt WHERE ticker = %s ORDER BY ts DESC LIMIT %s""",
        [ticker, limit],
    )
    candles = sorted(rows, key=lambda x: x["ts"])
    return {"candles": candles, "ticker": ticker}

@router.get("/candles/historical")
async def get_candles_historical(
    ticker: str = "AAPL", timeframe: str = "1m",
    start: str = "", end: str = "", limit: int = 500,
):
    table = f"raw_ohlcv_{timeframe}" if timeframe in ("1m","5m","15m") else "raw_ohlcv_1m"
    conditions = ["ticker = %s"]
    params: list = [ticker]
    if start:
        conditions.append("ts >= %s")
        params.append(start)
    if end:
        conditions.append("ts <= %s")
        params.append(end)
    where = " AND ".join(conditions)
    params.append(limit)
    rows = query(
        f"SELECT ts, open, high, low, close, volume FROM {table} WHERE {where} ORDER BY ts DESC LIMIT %s",
        params,
    )
    candles = sorted(rows, key=lambda x: x["ts"])
    return {"candles": candles, "ticker": ticker, "source": table}
