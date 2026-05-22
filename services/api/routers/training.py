"""
services/api/routers/training.py
────────────────────────────────
Endpoints de training — Fase 6.9 reescritura completa.

POST /train              — lanzar nuevo entrenamiento
GET  /training/jobs      — lista jobs del usuario
GET  /training/jobs/{id} — status de un job
GET  /training/usage     — uso este mes
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.api.auth.dependencies import get_active_user, get_current_user
from shared.db import get_conn, query
from shared.model_type_registry import get_model_type, validate_hyperparameters
from shared.plan_limits import get_plan_limits

log = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class TrainRequest(BaseModel):
    name: str
    ticker: str = "AAPL"
    model_type: str  # lightgbm, xgboost, etc.
    hyperparameters: dict = Field(default_factory=dict)
    train_from: str  # YYYY-MM-DD
    train_to: str
    test_from: str
    test_to: str
    context_tickers: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _count_trainings_this_month(user_id: str) -> int:
    rows = query(
        """SELECT COUNT(*) as cnt FROM training_jobs
           WHERE user_id = %s
           AND created_at >= date_trunc('month', CURRENT_TIMESTAMP)""",
        [user_id],
    )
    return rows[0]["cnt"] if rows else 0


def _count_custom_models(user_id: str) -> int:
    """Count distinct model names the user has created (sidebar entries)."""
    rows = query(
        """SELECT COUNT(*) as cnt FROM (
               SELECT DISTINCT model_name FROM training_jobs
               WHERE user_id = %s
           ) sub""",
        [user_id],
    )
    return rows[0]["cnt"] if rows else 0


def _model_exists(user_id: str, model_name: str) -> bool:
    """Check if a model with this name already exists for the user."""
    rows = query(
        """SELECT 1 FROM training_jobs
           WHERE user_id = %s AND model_name = %s LIMIT 1""",
        [user_id, model_name],
    )
    return bool(rows)


def _get_extra_trainings(user_id: str) -> int:
    rows = query(
        "SELECT extra_trainings FROM user_credits WHERE user_id = %s",
        [user_id],
    )
    return rows[0]["extra_trainings"] if rows else 0


def _validate_train(req: TrainRequest, user: dict, *, is_retrain: bool = False) -> list[str]:
    errors = []
    plan = user.get("plan", "trial")
    limits = get_plan_limits(plan)
    user_id = user["id"]

    # 1. Ticker existe
    t_rows = query(
        "SELECT ticker FROM ticker_universe WHERE ticker = %s AND is_active = true",
        [req.ticker],
    )
    if not t_rows:
        errors.append(f"Ticker '{req.ticker}' no existe o no está activo")

    # 2. Model type existe
    mt = get_model_type(req.model_type)
    if mt is None:
        errors.append(f"Tipo de modelo '{req.model_type}' no existe")

    # 3. Hyperparameters válidos
    if mt is not None:
        hp_errors = validate_hyperparameters(req.model_type, req.hyperparameters)
        errors.extend(hp_errors)

    # 4. Training days
    try:
        t_from = date.fromisoformat(req.train_from)
        t_to = date.fromisoformat(req.train_to)
        te_from = date.fromisoformat(req.test_from)
        te_to = date.fromisoformat(req.test_to)
        total_days = (t_to - t_from).days + (te_to - te_from).days
        if total_days <= 0:
            errors.append("Las fechas deben ser válidas y positivas")
        elif total_days > limits["max_training_days"]:
            errors.append(
                f"Total {total_days} días excede límite del plan "
                f"({limits['max_training_days']} días)"
            )
    except ValueError:
        errors.append("Formato de fecha inválido (usar YYYY-MM-DD)")

    # 5. Trainings/month (counts both train + retrain)
    used = _count_trainings_this_month(user_id)
    extra = _get_extra_trainings(user_id)
    limit_month = limits["max_trainings_month"] + extra
    if used >= limit_month:
        errors.append(f"Límite de trainings/mes alcanzado ({used}/{limit_month})")

    # 6. Custom models — skip if retraining an existing model
    if not is_retrain:
        current_models = _count_custom_models(user_id)
        if current_models >= limits["max_custom_models"]:
            errors.append(
                f"Límite de modelos custom alcanzado "
                f"({current_models}/{limits['max_custom_models']})"
            )

    return errors


def _run_training_sync(req: TrainRequest) -> dict:
    """Ejecuta training via subprocess (motor legacy)."""
    from shared.legacy_runners import generate_experiment_yaml, run_pipeline

    model_name_map = {
        "lightgbm": "lightgbm", "xgboost": "xgboost",
        "random_forest": "random_forest", "transformer": "transformer",
        "gru": "gru", "lstm": "lstm",
    }
    legacy_model = model_name_map.get(req.model_type, req.model_type)

    tmp, exp_name = generate_experiment_yaml(
        model=legacy_model,
        ticker=req.ticker,
        timeframe="1m",
        train_start=req.train_from,
        train_end=req.train_to,
        test_start=req.test_from,
        test_end=req.test_to,
        params=req.hyperparameters,
        experiment_name=req.name,
        context_tickers=req.context_tickers or None,
        columns=req.columns or None,
    )
    try:
        result = run_pipeline(
            [sys.executable, "-m", "apps.ml_sandbox.pipeline", "--config", str(tmp)],
            timeout=600,
        )
        return {"success": result.get("success", False), "experiment_name": exp_name, **result}
    finally:
        tmp.unlink(missing_ok=True)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/train")
async def train_model(req: TrainRequest, user: dict = Depends(get_active_user)):
    """Lanza un entrenamiento. Si el modelo ya existe, es un re-train."""
    user_id = user["id"]
    is_retrain = _model_exists(user_id, req.name)

    errors = _validate_train(req, user, is_retrain=is_retrain)
    if errors:
        raise HTTPException(422, detail={"errors": errors})

    start_time = time.time()

    # Always INSERT a new training_jobs row (counts toward monthly limit).
    # The listing endpoint deduplicates by returning only the latest per model_name.
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO training_jobs
                       (user_id, model_name, model_type, ticker, status,
                        train_from, train_to, test_from, test_to,
                        hyperparameters, columns, context_tickers,
                        started_at)
                       VALUES (%s,%s,%s,%s,'running',%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id""",
                    [
                        user_id, req.name, req.model_type, req.ticker,
                        req.train_from, req.train_to, req.test_from, req.test_to,
                        json.dumps(req.hyperparameters),
                        json.dumps(req.columns or []),
                        json.dumps(req.context_tickers or []),
                        datetime.now(UTC),
                    ],
                )
                job_id = str(cur.fetchone()[0])
    except Exception as e:
        raise HTTPException(500, f"Error creando job: {e}") from e

    # Ejecutar training síncrono
    result = _run_training_sync(req)
    duration = round(time.time() - start_time, 2)
    status = "completed" if result.get("success") else "failed"
    exp_name = result.get("experiment_name", req.name)

    # Leer métricas
    metrics = None
    if result.get("success"):
        m_rows = query(
            """SELECT metrics_summary, training_duration
               FROM silver_model_registry
               WHERE experiment_name = %s AND is_active = true LIMIT 1""",
            [exp_name],
        )
        if m_rows:
            metrics = m_rows[0].get("metrics_summary")

        # Actualizar silver_model_registry con user_id + hyperparameters
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE silver_model_registry
                           SET user_id = %s, hyperparameters = %s,
                               train_from = %s, train_to = %s,
                               test_from = %s, test_to = %s, updated_at = %s
                           WHERE experiment_name = %s AND is_active = true""",
                        [
                            user_id, json.dumps(req.hyperparameters),
                            req.train_from, req.train_to,
                            req.test_from, req.test_to,
                            datetime.now(UTC), exp_name,
                        ],
                    )
        except Exception as e:
            log.error(f"Error actualizando model_registry: {e}")

    # Actualizar training_job
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE training_jobs
                       SET status = %s, progress_pct = %s, metrics = %s,
                           error = %s, completed_at = %s
                       WHERE id = %s""",
                    [
                        status,
                        100 if status == "completed" else 0,
                        json.dumps(metrics) if metrics else None,
                        result.get("stderr", "")[:500] if status == "failed" else None,
                        datetime.now(UTC),
                        job_id,
                    ],
                )
    except Exception as e:
        log.error(f"Error actualizando job: {e}")

    return {
        "job_id": job_id,
        "experiment_name": exp_name,
        "status": status,
        "duration": duration,
        "metrics": metrics,
    }


@router.get("/training/jobs")
async def list_training_jobs(
    user: dict = Depends(get_current_user),
    limit: int = Query(20, le=50),
):
    """Lista jobs de training del usuario (solo el más reciente por modelo)."""
    # Cleanup: mark stale "running" jobs as failed (e.g. page refresh killed request)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE training_jobs
                       SET status = 'failed', error = 'Timeout — training interrumpido',
                           completed_at = NOW()
                       WHERE user_id = %s AND status = 'running'
                         AND started_at < NOW() - INTERVAL '15 minutes'""",
                    [user["id"]],
                )
    except Exception as e:
        log.warning("Error limpiando jobs stale: %s", e)

    rows = query(
        """SELECT DISTINCT ON (model_name)
                  id, model_name, model_type, ticker, status,
                  progress_pct, metrics, error,
                  hyperparameters, columns, context_tickers,
                  train_from, train_to, test_from, test_to,
                  started_at, completed_at, created_at
           FROM training_jobs WHERE user_id = %s
           ORDER BY model_name, created_at DESC""",
        [user["id"]],
    )
    # Re-sort by created_at DESC for display
    if rows:
        rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)
    return {"jobs": (rows or [])[:limit]}


@router.get("/training/jobs/{job_id}")
async def get_training_job(job_id: str, user: dict = Depends(get_current_user)):
    """Status de un job de training (polling)."""
    rows = query(
        """SELECT id, model_name, model_type, ticker, status,
                  progress_pct, metrics, error, hyperparameters,
                  columns, context_tickers,
                  train_from, train_to, test_from, test_to,
                  started_at, completed_at, created_at
           FROM training_jobs WHERE id = %s AND user_id = %s""",
        [job_id, user["id"]],
    )
    if not rows:
        raise HTTPException(404, "Job no encontrado")
    return {"job": rows[0]}


@router.get("/training/usage")
async def training_usage(user: dict = Depends(get_current_user)):
    """Uso de trainings este mes vs límite del plan."""
    user_id = user["id"]
    plan = user.get("plan", "trial")
    limits = get_plan_limits(plan)
    used = _count_trainings_this_month(user_id)
    extra = _get_extra_trainings(user_id)
    limit_total = limits["max_trainings_month"] + extra
    custom_count = _count_custom_models(user_id)
    return {
        "used_this_month": used,
        "limit_month": limit_total,
        "remaining_month": max(0, limit_total - used),
        "custom_models": custom_count,
        "limit_custom_models": limits["max_custom_models"],
    }
