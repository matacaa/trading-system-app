"""
shared/plan_limits.py
─────────────────────
Límites por plan. Lee de plan_config (DB) con fallback a dict hardcodeado.
Cacheable en memoria con TTL 5 min.

Uso:
    from shared.plan_limits import get_plan_limits, check_limit, enforce_limit

    limits = get_plan_limits("pro")
    check_limit("pro", "max_backtests_month", current_count=12)  # → True/False
    enforce_limit("pro", "max_backtests_month", 12)  # → raises 403 if exceeded
"""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException

log = logging.getLogger(__name__)

# ── Fallback hardcodeado (se usa si plan_config no existe en DB) ──────────────

_DEFAULTS: dict[str, dict] = {
    "trial": {
        "guardrails_available": [
            "horario_mercado", "posicion_abierta", "rsi", "macd",
            "bollinger", "volumen", "ema_tendencia", "score_minimo",
        ],
        "max_models": 1, "max_hist_days": 14,
        "max_backtests_month": 5, "max_backtests_saved": 5,
        "max_trainings_month": 0, "max_training_days": 0,
        "max_custom_models": 0, "max_tickers": 1,
    },
    "starter": {
        "guardrails_available": [
            "horario_mercado", "posicion_abierta", "rsi", "macd",
            "bollinger", "volumen", "ema_tendencia", "score_minimo",
            "atr_volatilidad", "vwap_spread", "sentiment", "max_posiciones",
        ],
        "max_models": 3, "max_hist_days": 90,
        "max_backtests_month": 20, "max_backtests_saved": 10,
        "max_trainings_month": 5, "max_training_days": 7,
        "max_custom_models": 3, "max_tickers": 3,
    },
    "pro": {
        "guardrails_available": "*",
        "max_models": 6, "max_hist_days": 365,
        "max_backtests_month": 50, "max_backtests_saved": 30,
        "max_trainings_month": 20, "max_training_days": 90,
        "max_custom_models": 12, "max_tickers": 10,
    },
    "elite": {
        "guardrails_available": "*",
        "max_models": 6, "max_hist_days": 1095,
        "max_backtests_month": 150, "max_backtests_saved": 100,
        "max_trainings_month": 50, "max_training_days": 730,
        "max_custom_models": 30, "max_tickers": 50,
    },
    "enterprise": {
        "guardrails_available": "*",
        "max_models": 6, "max_hist_days": 9999,
        "max_backtests_month": 400, "max_backtests_saved": 500,
        "max_trainings_month": 150, "max_training_days": 9999,
        "max_custom_models": 999, "max_tickers": 999,
    },
}

# ── Cache en memoria (TTL 5 min) ─────────────────────────────────────────────

_cache: dict[str, dict] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 300  # 5 min


def _load_from_db() -> dict[str, dict]:
    """Carga plan_config desde PostgreSQL."""
    global _cache, _cache_ts

    if _cache and (time.time() - _cache_ts) < _CACHE_TTL:
        return _cache

    try:
        from shared.db import query

        rows = query("SELECT * FROM plan_config")
        if rows:
            result = {}
            for r in rows:
                plan = r["plan"]
                ga = r.get("guardrails_available")
                # JSONB puede venir como str o list
                if isinstance(ga, str) and ga != "*":
                    import json
                    ga = json.loads(ga)
                result[plan] = {
                    "guardrails_available": ga,
                    "max_models": r["max_models"],
                    "max_hist_days": r["max_hist_days"],
                    "max_backtests_month": r["max_backtests_month"],
                    "max_backtests_saved": r["max_backtests_saved"],
                    "max_trainings_month": r["max_trainings_month"],
                    "max_training_days": r["max_training_days"],
                    "max_custom_models": r["max_custom_models"],
                    "max_tickers": r["max_tickers"],
                }
            _cache = result
            _cache_ts = time.time()
            return result
    except Exception as e:
        log.warning("plan_config no accesible, usando fallback: %s", e)

    return _DEFAULTS


# ── API pública ───────────────────────────────────────────────────────────────


def get_plan_limits(plan: str) -> dict:
    """Devuelve los límites para un plan. Fallback a trial si no existe."""
    plans = _load_from_db()
    return plans.get(plan, plans.get("trial", _DEFAULTS["trial"]))


def check_limit(plan: str, resource: str, current_count: int) -> bool:
    """True si current_count < límite del recurso para el plan."""
    limits = get_plan_limits(plan)
    max_val = limits.get(resource, 0)
    return current_count < max_val


def enforce_limit(
    plan: str,
    resource: str,
    current_count: int,
    extra: int = 0,
) -> None:
    """Raise HTTP 403 si el límite se ha alcanzado.

    Args:
        plan: nombre del plan del usuario
        resource: nombre del recurso (ej. "max_backtests_month")
        current_count: uso actual del usuario
        extra: créditos extra del usuario (de user_credits)
    """
    limits = get_plan_limits(plan)
    max_val = limits.get(resource, 0) + extra
    if current_count >= max_val:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "plan_limit_exceeded",
                "resource": resource,
                "current": current_count,
                "limit": max_val,
                "plan": plan,
            },
        )


def is_guardrail_available(plan: str, guardrail_name: str) -> bool:
    """True si el guardrail está disponible para el plan."""
    limits = get_plan_limits(plan)
    available = limits.get("guardrails_available", [])
    if available == "*":
        return True
    return guardrail_name in available


def invalidate_cache() -> None:
    """Fuerza recarga desde DB en la próxima llamada."""
    global _cache, _cache_ts
    _cache = {}
    _cache_ts = 0.0
