"""Endpoints de señales, decisiones y trades."""
from datetime import UTC, datetime

from fastapi import APIRouter

from shared.db import query

router = APIRouter()

@router.get("/signals/latest")
async def latest_signals(ticker: str = "AAPL"):
    rows = query(
        """SELECT ts, ticker, experiment_name, y_pred, y_prob, score, run_at
           FROM gold_signals WHERE ticker = %s ORDER BY run_at DESC LIMIT 30""",
        [ticker],
    )
    if not rows:
        return {"signals": [], "run_at": None}
    latest_run = rows[0]["run_at"]
    return {"signals": [s for s in rows if s["run_at"] == latest_run], "run_at": latest_run}

@router.get("/decisions/today")
async def today_decisions(ticker: str = "AAPL"):
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    rows = query(
        """SELECT ts, decision, score_final, ejecutada, motivo_rechazo
           FROM gold_decisions WHERE ticker = %s AND ts >= %s ORDER BY ts DESC""",
        [ticker, today],
    )
    return {"decisions": rows}

@router.get("/trades")
async def get_trades(ticker: str = "AAPL", limit: int = 20):
    rows = query(
        """SELECT ticker, ts_entrada, precio_entrada, ts_salida, precio_salida,
                  pnl, pnl_pct, status, motivo_salida, qty
           FROM gold_trades WHERE ticker = %s ORDER BY ts_entrada DESC LIMIT %s""",
        [ticker, limit],
    )
    return {"trades": rows}
