"""Endpoints de squawks (alertas).
TODO fase 3: implementar cuando el squawk engine esté listo.
"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/squawks")
async def get_squawks(limit: int = 50):
    """Feed de squawks paginado.
    TODO: leer de gold_squawks con user_id.
    """
    return {"squawks": [], "message": "Squawk service not yet implemented"}

@router.get("/squawks/stats")
async def squawk_stats():
    """Resumen del día."""
    return {"total": 0, "by_priority": {}, "message": "Not yet implemented"}
