"""
services/api/routers/models.py
──────────────────────────────
Endpoints de modelos — Fase 6.8 modificación.

GET    /models              — lista con campos nuevos
GET    /models/custom       — modelos custom del usuario
GET    /models/{name}       — detalle
GET    /models/{name}/predictions — señales del test period
DELETE /models/{name}       — eliminar modelo + Blob Storage
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from services.api.auth.dependencies import get_current_user
from shared.db import get_conn, query

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/models")
async def list_models(
    user: dict = Depends(get_current_user),
    ticker: str | None = Query(None),
    user_id_filter: str | None = Query(None, alias="user_id"),
):
    """Lista modelos activos con campos extendidos."""
    conditions = ["is_active = true", "status = 'complete'"]
    params: list = []

    if ticker:
        conditions.append("ticker = %s")
        params.append(ticker)
    if user_id_filter:
        conditions.append("user_id = %s")
        params.append(user_id_filter)

    where = " AND ".join(conditions)
    rows = query(
        f"""SELECT experiment_name, model_name, version, is_active,
                   status, metrics_summary, training_duration, created_at,
                   feature_columns, ticker, timeframe,
                   user_id, hyperparameters, train_from, train_to,
                   test_from, test_to, blob_path, updated_at
            FROM silver_model_registry WHERE {where}
            ORDER BY created_at DESC""",
        params,
    )
    return {"models": rows or []}


@router.get("/models/custom")
async def list_custom_models(user: dict = Depends(get_current_user)):
    """Modelos custom del usuario."""
    rows = query(
        """SELECT experiment_name, model_name, version, ticker,
                  metrics_summary, hyperparameters, training_duration,
                  train_from, train_to, test_from, test_to,
                  blob_path, created_at, updated_at
           FROM silver_model_registry
           WHERE user_id = %s AND is_active = true
           ORDER BY created_at DESC""",
        [user["id"]],
    )
    return {"models": rows or []}


@router.get("/models/{name}")
async def get_model(name: str, user: dict = Depends(get_current_user)):
    """Detalle completo de un modelo."""
    rows = query(
        """SELECT experiment_name, model_name, version, is_active, status,
                  metrics_summary, training_duration, created_at,
                  feature_columns, ticker, timeframe,
                  user_id, hyperparameters, train_from, train_to,
                  test_from, test_to, predictions, blob_path,
                  training_duration_s, updated_at
           FROM silver_model_registry
           WHERE experiment_name = %s AND is_active = true""",
        [name],
    )
    if not rows:
        raise HTTPException(404, f"Modelo '{name}' no encontrado")
    return {"model": rows[0]}


@router.get("/models/{name}/predictions")
async def get_model_predictions(name: str, user: dict = Depends(get_current_user)):
    """Señales Long/Short del test period para chart."""
    rows = query(
        """SELECT predictions, test_from, test_to, ticker
           FROM silver_model_registry
           WHERE experiment_name = %s AND is_active = true""",
        [name],
    )
    if not rows:
        raise HTTPException(404, f"Modelo '{name}' no encontrado")
    return {
        "model": name,
        "ticker": rows[0].get("ticker"),
        "test_from": rows[0].get("test_from"),
        "test_to": rows[0].get("test_to"),
        "predictions": rows[0].get("predictions") or [],
    }


@router.delete("/models/{name}")
async def delete_model(name: str, user: dict = Depends(get_current_user)):
    """Elimina un modelo custom: registry + Blob Storage."""
    rows = query(
        """SELECT experiment_name, blob_path, user_id
           FROM silver_model_registry
           WHERE experiment_name = %s AND user_id = %s AND is_active = true""",
        [name, user["id"]],
    )
    if not rows:
        raise HTTPException(404, "Modelo no encontrado o no tienes permiso")

    blob_path = rows[0].get("blob_path")
    if blob_path:
        try:
            from shared.blob_storage import delete_model as blob_delete

            blob_delete(blob_path)
        except Exception as e:
            log.warning(f"Error eliminando blob {blob_path}: {e}")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE silver_model_registry
                   SET is_active = false, updated_at = NOW()
                   WHERE experiment_name = %s AND user_id = %s""",
                [name, user["id"]],
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error eliminando modelo: {e}") from e
    finally:
        conn.close()
    return {"deleted": True, "model": name}
