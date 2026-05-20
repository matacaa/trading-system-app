"""
services/api/routers/tickers.py
───────────────────────────────
Endpoints de tickers — Fase 6.5 reescritura.

GET /tickers/universe           — catálogo desde DB con search/filter/pagination
GET /tickers/{ticker}/indicators — serie temporal indicadores
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from services.api.auth.dependencies import get_current_user
from shared.db import query

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/tickers/universe")
async def ticker_universe(
    search: str | None = Query(None, description="Buscar por ticker o nombre"),
    sector: str | None = Query(None),
    exchange: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Catálogo de tickers disponibles con búsqueda y filtros."""
    conditions = ["is_active = true"]
    params: list[Any] = []

    if search:
        conditions.append("(ticker ILIKE %s OR name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    if sector:
        conditions.append("sector = %s")
        params.append(sector)

    if exchange:
        conditions.append("exchange = %s")
        params.append(exchange)

    where = " AND ".join(conditions)
    offset = (page - 1) * limit

    # Count
    count_rows = query(f"SELECT COUNT(*) as total FROM ticker_universe WHERE {where}", params)
    total = count_rows[0]["total"] if count_rows else 0

    # Fetch page
    rows = query(
        f"""SELECT ticker, name, sector, exchange, model_coverage
            FROM ticker_universe WHERE {where}
            ORDER BY ticker LIMIT %s OFFSET %s""",
        [*params, limit, offset],
    )

    # Sectores para filtro
    sector_rows = query(
        "SELECT DISTINCT sector FROM ticker_universe WHERE is_active = true ORDER BY sector"
    )
    sectors = [r["sector"] for r in (sector_rows or [])]

    return {
        "tickers": rows or [],
        "total": total,
        "page": page,
        "limit": limit,
        "sectors": sectors,
    }


@router.get("/tickers/{ticker}/indicators")
async def ticker_indicators(
    ticker: str,
    indicators: str = Query("rsi_14,macd_line,ema_9,ema_21"),
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(get_current_user),
):
    """Serie temporal de indicadores para chart."""
    t_rows = query("SELECT ticker FROM ticker_universe WHERE ticker = %s", [ticker])
    if not t_rows:
        raise HTTPException(404, f"Ticker '{ticker}' no encontrado")

    allowed = {
        "rsi_14", "macd_line", "macd_signal", "ema_9", "ema_12", "ema_21",
        "bb_pct", "bb_width", "bb_upper", "bb_lower", "bb_middle",
        "vwap", "atr_14", "volume_norm", "returns_5",
        "open", "high", "low", "close", "volume",
    }
    requested = [i.strip() for i in indicators.split(",")]
    valid = [i for i in requested if i in allowed]
    if not valid:
        raise HTTPException(
            400,
            f"No hay indicadores válidos. Permitidos: {', '.join(sorted(allowed))}",
        )

    cols = ", ".join(valid)
    rows = query(
        f"SELECT ts, {cols} FROM silver_features_rt WHERE ticker = %s ORDER BY ts DESC LIMIT %s",
        [ticker, limit],
    )
    return {
        "ticker": ticker,
        "indicators": valid,
        "data": list(reversed(rows or [])),
        "count": len(rows or []),
    }
