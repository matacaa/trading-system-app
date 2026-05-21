"""Endpoints de control de trading (activar/desactivar inversión)."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.api.auth.dependencies import get_current_user
from shared.db import execute, query_one

log = logging.getLogger(__name__)
router = APIRouter()


class TradingToggle(BaseModel):
    enabled: bool


@router.get("/trading/status")
async def trading_status(_user: dict = Depends(get_current_user)):
    try:
        row = query_one("SELECT trading_enabled, updated_at FROM config WHERE id = 1")
        if row:
            return {"trading_enabled": row.get("trading_enabled", False), "updated_at": row.get("updated_at")}
        return {"trading_enabled": False}
    except Exception as e:
        return {"trading_enabled": False, "error": str(e)}


@router.post("/trading/toggle")
async def toggle_trading(body: TradingToggle, user: dict = Depends(get_current_user)):
    # Solo admin puede activar/desactivar trading
    if user["plan"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Solo administradores pueden cambiar el estado de trading",
        )
    try:
        execute(
            "UPDATE config SET trading_enabled = %s, updated_at = %s WHERE id = 1",
            [body.enabled, datetime.now(UTC).isoformat()],
        )
        status = "activado" if body.enabled else "desactivado"
        log.info("Trading %s por %s", status, user["email"])
        return {"trading_enabled": body.enabled, "status": status}
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e


@router.get("/portfolio")
async def get_portfolio(_user: dict = Depends(get_current_user)):
    try:
        from apps.trading_engine.alpaca_trader import get_portfolio_state

        return get_portfolio_state()
    except Exception as e:
        return {"capital": 0, "posiciones": {}, "n_posiciones": 0, "portfolio_value": 0, "error": str(e)}
