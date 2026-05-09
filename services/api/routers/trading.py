"""Endpoints de control de trading (activar/desactivar inversión)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from shared.db import sb

log = logging.getLogger(__name__)
router = APIRouter()

class TradingToggle(BaseModel):
    enabled: bool

@router.get("/trading/status")
async def trading_status():
    try:
        resp = sb.table("config").select("trading_enabled,updated_at").eq("id", 1).single().execute()
        return {"trading_enabled": resp.data.get("trading_enabled", False), "updated_at": resp.data.get("updated_at")}
    except Exception as e:
        return {"trading_enabled": False, "error": str(e)}

@router.post("/trading/toggle")
async def toggle_trading(body: TradingToggle):
    try:
        sb.table("config").update({
            "trading_enabled": body.enabled,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", 1).execute()
        status = "activado" if body.enabled else "desactivado"
        log.info(f"Trading {status}")
        return {"trading_enabled": body.enabled, "status": status}
    except Exception as e:
        raise HTTPException(500, f"Error: {e}")

@router.get("/portfolio")
async def get_portfolio():
    try:
        from apps.trading_engine.alpaca_trader import get_portfolio_state
        return get_portfolio_state()
    except Exception as e:
        return {"capital": 0, "posiciones": {}, "n_posiciones": 0, "portfolio_value": 0, "error": str(e)}
