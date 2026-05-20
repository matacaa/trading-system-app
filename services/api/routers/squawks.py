"""
services/api/routers/squawks.py
───────────────────────────────
Endpoints de squawks — Fase 6.8 modificación.

GET /squawks            — lista con filtros (?ticker, ?since, ?count_only)
GET /squawks/{id}       — detalle
GET /squawks/audio/{id} — URL del audio
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from services.api.auth.dependencies import get_current_user
from shared.db import query

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/squawks")
async def list_squawks(
    user: dict = Depends(get_current_user),
    ticker: str | None = Query(None, description="Filtrar por ticker"),
    since: str | None = Query(None, description="Timestamp ISO para polling incremental"),
    count_only: bool = Query(False, description="Solo devolver count (para badges)"),
    priority: str | None = Query(None, description="Filtrar: high/medium/low"),
    limit: int = Query(50, ge=1, le=200),
):
    """Lista squawks con filtros para sidebar y polling."""
    conditions = ["1=1"]
    params: list[Any] = []

    if ticker:
        conditions.append("ticker = %s")
        params.append(ticker)

    if since:
        conditions.append("created_at > %s")
        params.append(since)

    if priority:
        conditions.append("priority = %s")
        params.append(priority)

    where = " AND ".join(conditions)

    if count_only:
        rows = query(
            f"SELECT COUNT(*) as count FROM gold_squawks WHERE {where}",
            params,
        )
        count = rows[0]["count"] if rows else 0

        ticker_counts = query(
            f"""SELECT ticker, COUNT(*) as count
                FROM gold_squawks WHERE {where}
                GROUP BY ticker ORDER BY ticker""",
            params,
        )
        return {
            "count": count,
            "by_ticker": {r["ticker"]: r["count"] for r in (ticker_counts or [])},
        }

    rows = query(
        f"""SELECT id, ticker, squawk_type, title, body, audio_url,
                   audio_duration, priority, score, direction,
                   market_data, model_scores, guardrails_result,
                   is_read, is_favorite, created_at
            FROM gold_squawks
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT %s""",
        [*params, limit],
    )
    return {"squawks": rows or []}


@router.get("/squawks/{squawk_id}")
async def get_squawk(squawk_id: str, user: dict = Depends(get_current_user)):
    """Detalle de un squawk."""
    rows = query("SELECT * FROM gold_squawks WHERE id = %s", [squawk_id])
    if not rows:
        raise HTTPException(404, "Squawk no encontrado")
    return {"squawk": rows[0]}


@router.get("/squawks/audio/{squawk_id}")
async def get_squawk_audio(squawk_id: str, user: dict = Depends(get_current_user)):
    """URL del audio de un squawk."""
    rows = query(
        "SELECT audio_url, audio_duration FROM gold_squawks WHERE id = %s",
        [squawk_id],
    )
    if not rows:
        raise HTTPException(404, "Squawk no encontrado")
    return {
        "audio_url": rows[0].get("audio_url"),
        "audio_duration": rows[0].get("audio_duration"),
    }
