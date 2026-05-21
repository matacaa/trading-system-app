"""
services/api/routers/preferences.py
───────────────────────────────────
PUT  /api/preferences/tickers                       — añadir/quitar ticker seguido
POST /api/preferences/tickers/{ticker}/activate      — activar squawks con config de backtest
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.api.auth.dependencies import get_active_user
from shared.db import execute, query_one
from shared.plan_limits import get_plan_limits

log = logging.getLogger(__name__)

router = APIRouter()


class TickerAction(BaseModel):
    action: str  # "add" | "remove" | "toggle"
    ticker: str


class ActivateRequest(BaseModel):
    backtest_id: str


@router.put("/preferences/tickers")
async def update_tickers(body: TickerAction, user: dict = Depends(get_active_user)):
    """Añadir o quitar un ticker de los seguidos."""
    plan = user.get("plan", "trial")
    limits = get_plan_limits(plan)
    max_tickers = limits.get("max_tickers", 1)

    # Leer tickers actuales
    prefs = query_one(
        "SELECT tickers FROM user_preferences WHERE user_id = %s",
        [user["id"]],
    )
    if not prefs:
        raise HTTPException(404, "user_preferences no encontrado")

    tickers = prefs.get("tickers") or []
    if isinstance(tickers, str):
        tickers = json.loads(tickers)

    ticker = body.ticker.upper()

    if body.action == "add":
        if ticker in tickers:
            return {"tickers": tickers, "message": "Ticker ya seguido"}
        if len(tickers) >= max_tickers:
            raise HTTPException(
                403,
                detail={
                    "error": "plan_limit_exceeded",
                    "resource": "max_tickers",
                    "current": len(tickers),
                    "limit": max_tickers,
                    "plan": plan,
                },
            )
        # Verificar que existe en ticker_universe
        tu = query_one(
            "SELECT ticker FROM ticker_universe WHERE ticker = %s AND is_active = true",
            [ticker],
        )
        if not tu:
            raise HTTPException(400, f"Ticker '{ticker}' no existe en el universo")
        tickers.append(ticker)

    elif body.action == "remove":
        if ticker not in tickers:
            return {"tickers": tickers, "message": "Ticker no estaba seguido"}
        tickers.remove(ticker)

    elif body.action == "toggle":
        if ticker in tickers:
            tickers.remove(ticker)
        else:
            if len(tickers) >= max_tickers:
                raise HTTPException(403, "Límite de tickers alcanzado")
            tickers.append(ticker)

    else:
        raise HTTPException(400, f"Acción '{body.action}' no válida. Usa add/remove/toggle.")

    execute(
        "UPDATE user_preferences SET tickers = %s, updated_at = NOW() WHERE user_id = %s",
        [json.dumps(tickers), user["id"]],
    )

    return {"tickers": tickers, "action": body.action, "ticker": ticker}


@router.post("/preferences/tickers/{ticker}/activate")
async def activate_ticker(
    ticker: str,
    body: ActivateRequest,
    user: dict = Depends(get_active_user),
):
    """
    Activa squawks para un ticker copiando config de un backtest.

    Copia: guardrails_config → guardrail_overrides[ticker]
           models_config → models_config[ticker]
           direction → ticker_direction[ticker]
           _source_backtest_id como referencia
    """
    ticker = ticker.upper()

    # Leer backtest
    bt = query_one(
        """SELECT id, ticker, direction, guardrails_config, models_config
           FROM backtest_runs
           WHERE id = %s AND user_id = %s""",
        [body.backtest_id, user["id"]],
    )
    if not bt:
        raise HTTPException(404, "Backtest no encontrado")

    # Leer preferencias actuales
    prefs = query_one(
        """SELECT tickers, guardrail_overrides, models_config, ticker_direction
           FROM user_preferences WHERE user_id = %s""",
        [user["id"]],
    )
    if not prefs:
        raise HTTPException(404, "user_preferences no encontrado")

    # Parse JSONB fields
    tickers = prefs.get("tickers") or []
    if isinstance(tickers, str):
        tickers = json.loads(tickers)
    guardrail_overrides = prefs.get("guardrail_overrides") or {}
    if isinstance(guardrail_overrides, str):
        guardrail_overrides = json.loads(guardrail_overrides)
    models_config = prefs.get("models_config") or {}
    if isinstance(models_config, str):
        models_config = json.loads(models_config)
    ticker_direction = prefs.get("ticker_direction") or {}
    if isinstance(ticker_direction, str):
        ticker_direction = json.loads(ticker_direction)

    # Copiar config del backtest al ticker
    bt_guardrails = bt.get("guardrails_config") or {}
    if isinstance(bt_guardrails, str):
        bt_guardrails = json.loads(bt_guardrails)
    bt_guardrails["_source_backtest_id"] = body.backtest_id

    bt_models = bt.get("models_config") or {}
    if isinstance(bt_models, str):
        bt_models = json.loads(bt_models)

    direction = bt.get("direction", "long")

    guardrail_overrides[ticker] = bt_guardrails
    models_config[ticker] = bt_models
    ticker_direction[ticker] = direction

    # Añadir ticker si no está
    if ticker not in tickers:
        tickers.append(ticker)

    # Guardar todo
    execute(
        """UPDATE user_preferences
           SET tickers = %s,
               guardrail_overrides = %s,
               models_config = %s,
               ticker_direction = %s,
               updated_at = NOW()
           WHERE user_id = %s""",
        [
            json.dumps(tickers),
            json.dumps(guardrail_overrides),
            json.dumps(models_config),
            json.dumps(ticker_direction),
            user["id"],
        ],
    )

    log.info(
        "Ticker %s activado para user %s (backtest %s, direction=%s)",
        ticker, user["id"], body.backtest_id, direction,
    )

    return {
        "ticker": ticker,
        "direction": direction,
        "backtest_id": body.backtest_id,
        "guardrails_config": bt_guardrails,
        "models_config": bt_models,
    }
