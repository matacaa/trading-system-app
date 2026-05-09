"""Endpoints de modelos ML."""
from fastapi import APIRouter
from shared.db import sb
from shared.models.registry import list_models as registry_list_models

router = APIRouter()

@router.get("/models")
async def get_models(ticker: str = ""):
    """Modelos entrenados registrados en Supabase."""
    q = sb.table("silver_model_registry").select(
        "experiment_name,model_name,ticker,timeframe,accuracy,f1_score,auc,version,status,is_active,created_at"
    )
    if ticker:
        q = q.eq("ticker", ticker)
    resp = q.order("created_at", desc=True).execute()
    return {"models": resp.data or []}

@router.get("/models/available")
async def available_models():
    """Modelos disponibles en el código (auto-descubiertos por el registry)."""
    return {"models": registry_list_models()}
