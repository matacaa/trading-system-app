"""
services/api/routers/live.py
────────────────────────────
Endpoints del motor live — Fase 6.6: config ensemble → DB.

GET  /live/config  — lee config de DB
POST /live/config  — escribe config a DB
GET  /live/status  — estado del pipeline
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.api.auth.dependencies import get_active_user, get_current_user
from shared.db import get_conn, query

log = logging.getLogger(__name__)
router = APIRouter()


class LiveEnsembleConfig(BaseModel):
    tickers: list[str] = ["AAPL"]
    context_tickers: list[str] = []
    modelos: list[dict] = []
    guardrails: dict = {}
    capital: dict = {}


@router.get("/live/config")
async def get_live_config(user: dict = Depends(get_current_user)):
    """Lee la configuración activa del ensemble desde DB."""
    rows = query(
        """SELECT guardrail_overrides, models_config, tickers
           FROM user_preferences WHERE user_id = %s""",
        [user["id"]],
    )
    if not rows:
        return {"config": None, "source": "none"}
    pref = rows[0]
    return {
        "config": {
            "tickers": pref.get("tickers") or [],
            "guardrails": pref.get("guardrail_overrides") or {},
            "models_config": pref.get("models_config") or {},
        },
        "source": "database",
    }


@router.post("/live/config")
async def set_live_config(body: LiveEnsembleConfig, user: dict = Depends(get_active_user)):
    """Escribe config del ensemble a DB (antes era a YAML en disco)."""
    user_id = user["id"]

    models_config = {}
    for m in body.modelos:
        name = m.get("experiment_name", "")
        if name and m.get("activo", True):
            models_config[name] = m.get("peso", 0.15)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE user_preferences
                   SET tickers = %s, guardrail_overrides = %s, models_config = %s
                   WHERE user_id = %s""",
                [
                    json.dumps(body.tickers),
                    json.dumps(body.guardrails),
                    json.dumps(models_config),
                    user_id,
                ],
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error guardando config: {e}") from e
    finally:
        conn.close()

    return {
        "status": "saved",
        "source": "database",
        "message": "Config guardada. Se aplica en el próximo ciclo del pipeline.",
    }


@router.get("/live/status")
async def live_status(user: dict = Depends(get_current_user)):
    """Estado del pipeline live."""
    last_log = query(
        "SELECT run_at, status, duration_s, errores FROM gold_logs ORDER BY run_at DESC LIMIT 1"
    )
    trading_enabled = False
    try:
        cfg_rows = query("SELECT trading_enabled FROM config WHERE id = 1")
        if cfg_rows:
            trading_enabled = bool(cfg_rows[0].get("trading_enabled", False))
    except Exception:
        pass
    return {
        "trading_enabled": trading_enabled,
        "last_run": last_log[0] if last_log else None,
    }
