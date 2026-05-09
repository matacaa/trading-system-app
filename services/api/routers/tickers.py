"""Endpoints de tickers y velas."""
from fastapi import APIRouter
from shared.db import sb
from shared.symbols import ALL_SYMBOLS

router = APIRouter()

@router.get("/tickers")
async def list_tickers():
    tickers_with_data: set[str] = set()
    for ticker in ALL_SYMBOLS:
        try:
            resp = sb.table("silver_features_1m").select("ticker").eq("ticker", ticker).limit(1).execute()
            if resp.data:
                tickers_with_data.add(ticker)
        except Exception:
            pass
    return {"tickers": [
        {"ticker": t, "name": n, "has_data": t in tickers_with_data}
        for t, n in ALL_SYMBOLS.items()
    ]}

@router.get("/candles")
async def get_candles(ticker: str = "AAPL", limit: int = 200):
    resp = (
        sb.table("raw_ohlcv_rt")
        .select("ts,open,high,low,close,volume")
        .eq("ticker", ticker)
        .order("ts", desc=True)
        .limit(limit)
        .execute()
    )
    candles = sorted(resp.data or [], key=lambda x: x["ts"])
    return {"candles": candles, "ticker": ticker}

@router.get("/candles/historical")
async def get_candles_historical(
    ticker: str = "AAPL", timeframe: str = "1m",
    start: str = "", end: str = "", limit: int = 500,
):
    table = f"raw_ohlcv_{timeframe}" if timeframe in ("1m","5m","15m") else "raw_ohlcv_1m"
    q = sb.table(table).select("ts,open,high,low,close,volume").eq("ticker", ticker)
    if start:
        q = q.gte("ts", start)
    if end:
        q = q.lte("ts", end)
    resp = q.order("ts", desc=True).limit(limit).execute()
    candles = sorted(resp.data or [], key=lambda x: x["ts"])
    return {"candles": candles, "ticker": ticker, "source": table}
