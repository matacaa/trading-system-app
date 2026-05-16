"""Endpoints de squawks (alertas).
TODO fase 5: implementar cuando el squawk engine esté listo.
"""

from fastapi import APIRouter, Depends

from services.api.auth.dependencies import get_current_user

router = APIRouter()


@router.get("/squawks")
async def get_squawks(limit: int = 50, user: dict = Depends(get_current_user)):
    """Feed de squawks paginado.
    TODO fase 5: leer de gold_squawks con user_id.
    """
    return {"squawks": [], "user_id": user["id"], "message": "Squawk service not yet implemented"}


@router.get("/squawks/stats")
async def squawk_stats(_user: dict = Depends(get_current_user)):
    """Resumen del día."""
    return {"total": 0, "by_priority": {}, "message": "Not yet implemented"}
