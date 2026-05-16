"""Endpoints de control de trading (activar/desactivar inversión)."""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.db import execute, query_one

log = logging.getLogger(__name__)
router = APIRouter()

class TradingToggle(BaseModel):
    enabled: bool

@router.get("/trading/status")
async def trading_status():
    try:
        row = query_one("SELECT trading_enabled, updated_at FROM config WHERE id = 1")
        return {"trading_enabled": row.get("trading_enabled", False), "updated_at": row.get("updated_at")} if row else {"trading_enabled": False}
    except Exception as e:
        return {"trading_enabled": False, "error": str(e)}

@router.post("/trading/toggle")
async def toggle_trading(body: TradingToggle):
    try:
        execute(
            "UPDATE config SET trading_enabled = %s, updated_at = %s WHERE id = 1",
            [body.enabled, datetime.now(UTC).isoformat()],
        )
        status = "activado" if body.enabled else "desactivado"
        log.info(f"Trading {status}")
        return {"trading_enabled": body.enabled, "status": status}
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e

@router.get("/portfolio")
async def get_portfolio():
    try:
        from apps.trading_engine.alpaca_trader import get_portfolio_state
        return get_portfolio_state()
    except Exception as e:
        return {"capital": 0, "posiciones": {}, "n_posiciones": 0, "portfolio_value": 0, "error": str(e)}
