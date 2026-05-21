"""
services/api/routers/model_types.py
───────────────────────────────────
GET /api/model-types — 6 tipos con params_schema para formulario dinámico
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from services.api.auth.dependencies import get_current_user
from shared.model_type_registry import get_model_types

router = APIRouter()


@router.get("/model-types")
async def list_model_types(user: dict = Depends(get_current_user)):
    """Tipos de modelo disponibles con hiperparámetros."""
    return {"model_types": get_model_types()}
