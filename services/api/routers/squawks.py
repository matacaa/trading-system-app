"""Endpoints de squawks (alertas personalizadas)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from services.api.auth.dependencies import get_current_user
from shared.db import execute, query, query_one

router = APIRouter()


@router.get("/squawks")
async def get_squawks(
    limit: int = 50,
    ticker: str = "",
    priority: str = "",
    unread_only: bool = False,
    user: dict = Depends(get_current_user),
):
    """Feed de squawks paginado, más recientes primero."""
    conditions = ["user_id = %s", "expires_at > %s"]
    params: list = [user["id"], datetime.now(UTC).isoformat()]

    if ticker:
        conditions.append("ticker = %s")
        params.append(ticker)
    if priority:
        conditions.append("priority = %s")
        params.append(priority)
    if unread_only:
        conditions.append("is_read = false")
        conditions.append("is_dismissed = false")

    where = " AND ".join(conditions)
    params.append(limit)

    rows = query(
        f"""SELECT id, ticker, squawk_type, priority, score, decision,
                   motivo, motivo_rechazo, guardrails_passed, market_data,
                   model_scores, audio_url, is_read, is_starred,
                   created_at, expires_at
            FROM gold_squawks
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT %s""",
        params,
    )
    return {"squawks": rows, "count": len(rows)}


@router.get("/squawks/stats")
async def squawk_stats(user: dict = Depends(get_current_user)):
    """Resumen de squawks del usuario."""
    now = datetime.now(UTC).isoformat()
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    row = query_one(
        """SELECT
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE is_read = false AND is_dismissed = false) AS unread,
               COUNT(*) FILTER (WHERE priority = 'high') AS high_priority,
               COUNT(*) FILTER (WHERE squawk_type = 'BUY') AS buys,
               COUNT(*) FILTER (WHERE squawk_type = 'HOLD') AS holds,
               COUNT(*) FILTER (WHERE squawk_type = 'INFO') AS infos
           FROM gold_squawks
           WHERE user_id = %s AND created_at >= %s AND expires_at > %s""",
        [user["id"], today, now],
    )
    return {"stats": row}


@router.post("/squawks/{squawk_id}/read")
async def mark_read(squawk_id: str, user: dict = Depends(get_current_user)):
    """Marcar un squawk como leído."""
    execute(
        """UPDATE gold_squawks
           SET is_read = true, read_at = %s
           WHERE id = %s AND user_id = %s""",
        [datetime.now(UTC).isoformat(), squawk_id, user["id"]],
    )
    return {"status": "ok"}


@router.post("/squawks/{squawk_id}/dismiss")
async def dismiss_squawk(squawk_id: str, user: dict = Depends(get_current_user)):
    """Descartar un squawk."""
    execute(
        """UPDATE gold_squawks
           SET is_dismissed = true, dismissed_at = %s
           WHERE id = %s AND user_id = %s""",
        [datetime.now(UTC).isoformat(), squawk_id, user["id"]],
    )
    return {"status": "ok"}


@router.post("/squawks/{squawk_id}/star")
async def toggle_star(squawk_id: str, user: dict = Depends(get_current_user)):
    """Marcar/desmarcar como favorito."""
    row = query_one(
        "SELECT is_starred FROM gold_squawks WHERE id = %s AND user_id = %s",
        [squawk_id, user["id"]],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Squawk no encontrado")

    new_val = not row["is_starred"]
    execute(
        "UPDATE gold_squawks SET is_starred = %s WHERE id = %s AND user_id = %s",
        [new_val, squawk_id, user["id"]],
    )
    return {"is_starred": new_val}


@router.get("/squawks/{squawk_id}")
async def get_squawk_detail(squawk_id: str, user: dict = Depends(get_current_user)):
    """Detalle completo de un squawk."""
    row = query_one(
        """SELECT id, ticker, squawk_type, priority, score, decision,
                  motivo, motivo_rechazo, guardrails_passed, guardrails_config,
                  market_data, model_scores, audio_url, audio_duration,
                  is_read, is_starred, is_dismissed,
                  created_at, expires_at, read_at, run_id
           FROM gold_squawks
           WHERE id = %s AND user_id = %s""",
        [squawk_id, user["id"]],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Squawk no encontrado")

    # Marcar como leído automáticamente
    if not row["is_read"]:
        execute(
            "UPDATE gold_squawks SET is_read = true, read_at = %s WHERE id = %s",
            [datetime.now(UTC).isoformat(), squawk_id],
        )

    return {"squawk": row}
