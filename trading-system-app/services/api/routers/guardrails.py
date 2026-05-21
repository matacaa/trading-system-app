"""
services/api/routers/guardrails.py
──────────────────────────────────
GET /api/guardrails/registry    — 14 guardrails con metadatos + params_schema
GET /api/guardrails/available   — guardrails disponibles para el plan del usuario
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from services.api.auth.dependencies import get_current_user
from shared.guardrail_registry import get_all_guardrails, get_available_for_plan

router = APIRouter()


@router.get("/guardrails/registry")
async def guardrail_registry(user: dict = Depends(get_current_user)):
    """Todos los guardrails activos con metadatos y params_schema."""
    return {"guardrails": get_all_guardrails()}


@router.get("/guardrails/available")
async def guardrails_available(user: dict = Depends(get_current_user)):
    """Guardrails disponibles para el plan del usuario."""
    plan = user.get("plan", "trial")
    available = get_available_for_plan(plan)
    return {"guardrails": available, "plan": plan, "total": len(available)}
