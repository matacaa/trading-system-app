"""Endpoints de backtest."""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.api.auth.dependencies import get_current_user
from shared.db import query

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
async def run_backtest(req: BacktestRequest, user: dict = Depends(get_current_user)):
    """Encola un backtest.
    TODO fase 6: encolar en Service Bus + cacheo inteligente.
    """
    import sys

    from apps.api.main import _generate_backtest_yaml, _run_pipeline

    tmp, bt_name = _generate_backtest_yaml(req)
    result = _run_pipeline(
        [sys.executable, "-m", "apps.ml_sandbox.backtest", str(tmp)],
        timeout=600,
    )
    return {"backtest_name": bt_name, "user_id": user["id"], **result}


@router.get("/backtest/list")
async def list_backtests(user: dict = Depends(get_current_user)):
    rows = query(
        """SELECT id, name, config, status, created_at, total_trades,
                  pnl_total, pnl_pct, win_rate, sharpe_ratio
           FROM backtest_runs
           WHERE user_id = %s OR user_id IS NULL
           ORDER BY created_at DESC LIMIT 50""",
        [user["id"]],
    )
    return {"backtests": rows}
