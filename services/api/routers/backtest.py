"""Endpoints de backtest."""
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from shared.db import sb

log = logging.getLogger(__name__)
router = APIRouter()

class BacktestRequest(BaseModel):
    name: str = ""
    tickers: list[str] = ["AAPL"]
    context_tickers: list[str] = []
    test_start: str
    test_end: str
    timeframe: str = "1m"
    modelos: list[dict[str, Any]]
    guardrails: dict[str, Any] = {}
    capital: dict[str, Any] = {}

@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    """Encola un backtest.
    TODO fase 4: encolar en Service Bus + cacheo inteligente.
    """
    from apps.api.main import _generate_backtest_yaml, _run_pipeline
    import sys
    tmp, bt_name = _generate_backtest_yaml(req)
    result = _run_pipeline(
        [sys.executable, "-m", "apps.ml_sandbox.backtest", str(tmp)],
        timeout=600,
    )
    return {"backtest_name": bt_name, **result}

@router.get("/backtest/list")
async def list_backtests():
    resp = (
        sb.table("backtest_runs")
        .select("id,name,config,status,created_at,total_trades,pnl_total,pnl_pct,win_rate,sharpe_ratio")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"backtests": resp.data or []}
