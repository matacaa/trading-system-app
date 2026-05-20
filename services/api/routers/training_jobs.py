"""
services/api/routers/training_jobs.py
─────────────────────────────────────
GET /api/training/jobs          — jobs del usuario ordenados DESC
GET /api/training/jobs/{id}     — status + progress_pct (polling)
GET /api/training/usage         — {used, limit, remaining} este mes
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from services.api.auth.dependencies import get_current_user
from shared.db import query, query_one
from shared.plan_limits import get_plan_limits

router = APIRouter()


@router.get("/training/jobs")
async def list_training_jobs(
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    """Jobs de entrenamiento del usuario, ordenados DESC."""
    rows = query(
        """SELECT id, model_name, model_type, ticker, status, progress_pct,
                  train_from, train_to, test_from, test_to,
                  hyperparameters, metrics, error,
                  started_at, completed_at, created_at
           FROM training_jobs
           WHERE user_id = %s
           ORDER BY created_at DESC
           LIMIT %s""",
        [user["id"], limit],
    )
    return {"jobs": rows}


@router.get("/training/jobs/{job_id}")
async def get_training_job(job_id: str, user: dict = Depends(get_current_user)):
    """Detalle de un job de entrenamiento (polling de progreso)."""
    row = query_one(
        """SELECT id, model_name, model_type, ticker, status, progress_pct,
                  train_from, train_to, test_from, test_to,
                  hyperparameters, metrics, error,
                  started_at, completed_at, created_at
           FROM training_jobs
           WHERE id = %s AND user_id = %s""",
        [job_id, user["id"]],
    )
    if not row:
        raise HTTPException(404, "Training job no encontrado")
    return row


@router.get("/training/usage")
async def training_usage(user: dict = Depends(get_current_user)):
    """Uso de trainings este mes vs límite del plan."""
    plan = user.get("plan", "trial")
    limits = get_plan_limits(plan)
    max_trainings = limits.get("max_trainings_month", 0)

    # Contar trainings este mes
    row = query_one(
        """SELECT COUNT(*) AS used FROM training_jobs
           WHERE user_id = %s
             AND created_at >= date_trunc('month', CURRENT_TIMESTAMP)""",
        [user["id"]],
    )
    used = row["used"] if row else 0

    # Créditos extra
    credit_row = query_one(
        "SELECT extra_trainings FROM user_credits WHERE user_id = %s",
        [user["id"]],
    )
    extra = credit_row["extra_trainings"] if credit_row else 0

    total_limit = max_trainings + extra
    return {
        "used": used,
        "limit": total_limit,
        "remaining": max(0, total_limit - used),
        "plan": plan,
    }
