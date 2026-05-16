"""Endpoints de modelos ML."""

from fastapi import APIRouter, Depends

from services.api.auth.dependencies import get_current_user
from shared.db import query
from shared.models.registry import list_models as registry_list_models

router = APIRouter()


@router.get("/models")
async def get_models(ticker: str = "", _user: dict = Depends(get_current_user)):
    """Modelos entrenados registrados en PostgreSQL."""
    if ticker:
        rows = query(
            """SELECT experiment_name, model_name, ticker, timeframe, accuracy, f1_score,
                      auc, version, status, is_active, created_at
               FROM silver_model_registry WHERE ticker = %s ORDER BY created_at DESC""",
            [ticker],
        )
    else:
        rows = query(
            """SELECT experiment_name, model_name, ticker, timeframe, accuracy, f1_score,
                      auc, version, status, is_active, created_at
               FROM silver_model_registry ORDER BY created_at DESC"""
        )
    return {"models": rows}


@router.get("/models/available")
async def available_models(_user: dict = Depends(get_current_user)):
    """Modelos disponibles en el código (auto-descubiertos por el registry)."""
    return {"models": registry_list_models()}
