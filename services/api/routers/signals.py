"""Endpoints de señales, decisiones y trades."""
from datetime import datetime, timezone

from fastapi import APIRouter
from shared.db import sb

router = APIRouter()

@router.get("/signals/latest")
async def latest_signals(ticker: str = "AAPL"):
    resp = sb.table("gold_signals").select(
        "ts,ticker,experiment_name,y_pred,y_prob,score,run_at"
    ).eq("ticker", ticker).order("run_at", desc=True).limit(30).execute()
    if not resp.data:
        return {"signals": [], "run_at": None}
    latest_run = resp.data[0]["run_at"]
    return {"signals": [s for s in resp.data if s["run_at"] == latest_run], "run_at": latest_run}

@router.get("/decisions/today")
async def today_decisions(ticker: str = "AAPL"):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resp = sb.table("gold_decisions").select(
        "ts,decision,score_final,ejecutada,motivo_rechazo"
    ).eq("ticker", ticker).gte("ts", today).order("ts", desc=True).execute()
    return {"decisions": resp.data or []}

@router.get("/trades")
async def get_trades(ticker: str = "AAPL", limit: int = 20):
    resp = sb.table("gold_trades").select(
        "ticker,ts_entrada,precio_entrada,ts_salida,precio_salida,pnl,pnl_pct,status,motivo_salida,qty"
    ).eq("ticker", ticker).order("ts_entrada", desc=True).limit(limit).execute()
    return {"trades": resp.data or []}
