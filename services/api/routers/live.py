"""Endpoints del pipeline live."""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as PydanticModel
from shared.db import query, query_one
from shared.config import cfg as app_cfg

log = logging.getLogger(__name__)
router = APIRouter()

class LiveEnsembleConfig(PydanticModel):
    tickers: list[str] = ["AAPL"]
    context_tickers: list[str] = []
    modelos: list[dict[str, Any]]
    guardrails: dict[str, Any] = {}
    capital: dict[str, Any] = {}

@router.get("/live/status")
async def live_status():
    last_log = query(
        "SELECT run_at, status, duration_s, errores FROM gold_logs ORDER BY run_at DESC LIMIT 1"
    )
    trading_enabled = False
    try:
        cfg_row = query_one("SELECT trading_enabled FROM config WHERE id = 1")
        trading_enabled = bool(cfg_row.get("trading_enabled", False)) if cfg_row else False
    except Exception:
        pass
    return {
        "running": False,
        "trading_enabled": trading_enabled,
        "last_run": last_log[0] if last_log else None,
    }

@router.get("/live/config")
async def get_live_config():
    ensemble_path = app_cfg.config_dir / "live" / "ensemble.yaml"
    if not ensemble_path.exists():
        return {"config": None, "error": "ensemble.yaml no encontrado"}
    with open(ensemble_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return {"config": config}

@router.post("/live/config")
async def set_live_config(body: LiveEnsembleConfig):
    ensemble_path = app_cfg.config_dir / "live" / "ensemble.yaml"
    config = {
        "data": {"tickers": body.tickers, "context_tickers": body.context_tickers, "timeframe": "1m"},
        "modelos": [
            {"experiment_name": m["experiment_name"], "activo": m.get("activo", True), "peso": m.get("peso", 0.15)}
            for m in body.modelos
        ],
        "capital": body.capital or {"inicial": 100000, "posicion_max_pct": 10, "stop_loss_pct": 5, "take_profit_pct": 10, "cierre_fin_dia": True},
        "guardrails": body.guardrails or {"score_threshold": 50, "posicion_abierta": {"activo": True}},
    }
    with open(ensemble_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)
    return {"status": "written"}
