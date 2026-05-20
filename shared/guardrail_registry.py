"""
shared/guardrail_registry.py
─────────────────────────────
Metadatos de guardrails. Lee de guardrail_registry (DB).
Filtra por plan usando plan_limits.

Separado de shared/guardrails.py que contiene la lógica de evaluación.
Este módulo solo gestiona metadata + disponibilidad por plan.

Uso:
    from shared.guardrail_registry import get_all_guardrails, get_available_for_plan

    all_gds = get_all_guardrails()
    available = get_available_for_plan("pro")
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────────────────────────────────

_cache: list[dict] | None = None
_cache_ts: float = 0.0
_CACHE_TTL = 3600  # 1h


def get_all_guardrails() -> list[dict]:
    """Devuelve todos los guardrails activos con metadatos y params_schema."""
    global _cache, _cache_ts

    if _cache is not None and (time.time() - _cache_ts) < _CACHE_TTL:
        return _cache

    try:
        import json

        from shared.db import query

        rows = query(
            "SELECT name, label, category, phase, description, params_schema, is_active "
            "FROM guardrail_registry WHERE is_active = true "
            "ORDER BY category, phase, name"
        )
        result = []
        for r in rows:
            ps = r.get("params_schema")
            if isinstance(ps, str):
                ps = json.loads(ps)
            result.append({
                "name": r["name"],
                "label": r["label"],
                "category": r["category"],
                "phase": r["phase"],
                "description": r.get("description"),
                "params_schema": ps or [],
            })
        _cache = result
        _cache_ts = time.time()
        return result
    except Exception as e:
        log.warning("guardrail_registry no accesible: %s", e)
        return _cache or []


def get_available_for_plan(plan: str) -> list[dict]:
    """Devuelve solo los guardrails disponibles para un plan."""
    from shared.plan_limits import get_plan_limits

    limits = get_plan_limits(plan)
    available = limits.get("guardrails_available", [])

    all_gds = get_all_guardrails()

    if available == "*":
        return all_gds

    return [g for g in all_gds if g["name"] in available]


def get_guardrail(name: str) -> dict | None:
    """Devuelve un guardrail por nombre."""
    for g in get_all_guardrails():
        if g["name"] == name:
            return g
    return None


def get_pre_guardrails() -> list[dict]:
    """Devuelve guardrails de fase 'pre'."""
    return [g for g in get_all_guardrails() if g["phase"] == "pre"]


def get_post_guardrails() -> list[dict]:
    """Devuelve guardrails de fase 'post'."""
    return [g for g in get_all_guardrails() if g["phase"] == "post"]


def validate_guardrails_config(
    config: dict, plan: str
) -> list[str]:
    """
    Valida que los guardrails en la config están disponibles para el plan.

    Args:
        config: dict de guardrails del usuario, ej. {"rsi": {"activo": true, "compra_max": 70}}
        plan: nombre del plan

    Returns:
        Lista de errores. Vacía si todo OK.
    """
    available = get_available_for_plan(plan)
    available_names = {g["name"] for g in available}

    errors = []
    for gd_name, gd_config in config.items():
        if not isinstance(gd_config, dict):
            continue
        if gd_config.get("activo", True) and gd_name not in available_names:
            errors.append(
                f"Guardrail '{gd_name}' no disponible en plan '{plan}'"
            )

    return errors


def invalidate_cache() -> None:
    """Fuerza recarga desde DB."""
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0.0
