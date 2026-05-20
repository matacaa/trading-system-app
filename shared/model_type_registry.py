"""
shared/model_type_registry.py
─────────────────────────────
Catálogo de tipos de modelo con hiperparámetros.
Lee de model_type_registry (DB). Valida hyperparameters contra params_schema.

Uso:
    from shared.model_type_registry import get_model_types, validate_hyperparameters

    types = get_model_types()
    errors = validate_hyperparameters("lightgbm", {"n_estimators": 200, "max_depth": 6})
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────────────────────────────────

_cache: list[dict] | None = None
_cache_ts: float = 0.0
_CACHE_TTL = 3600  # 1h — raramente cambia


def get_model_types() -> list[dict]:
    """Devuelve todos los tipos de modelo disponibles."""
    global _cache, _cache_ts

    if _cache is not None and (time.time() - _cache_ts) < _CACHE_TTL:
        return _cache

    try:
        import json

        from shared.db import query

        rows = query(
            "SELECT type_id, label, category, params_schema, is_available "
            "FROM model_type_registry WHERE is_available = true "
            "ORDER BY category, label"
        )
        result = []
        for r in rows:
            ps = r.get("params_schema")
            if isinstance(ps, str):
                ps = json.loads(ps)
            result.append({
                "type_id": r["type_id"],
                "label": r["label"],
                "category": r["category"],
                "params_schema": ps or [],
            })
        _cache = result
        _cache_ts = time.time()
        return result
    except Exception as e:
        log.warning("model_type_registry no accesible: %s", e)
        return _cache or []


def get_model_type(type_id: str) -> dict | None:
    """Devuelve un tipo de modelo por su ID."""
    types = get_model_types()
    for t in types:
        if t["type_id"] == type_id:
            return t
    return None


def validate_hyperparameters(type_id: str, params: dict) -> list[str]:
    """
    Valida hyperparameters contra el params_schema del tipo.

    Returns:
        Lista de errores. Vacía si todo OK.
    """
    model_type = get_model_type(type_id)
    if model_type is None:
        return [f"Tipo de modelo '{type_id}' no existe"]

    schema = model_type.get("params_schema", [])
    if not schema:
        return []  # No schema = no validation

    errors = []
    for param_def in schema:
        key = param_def["key"]
        if key not in params:
            continue  # Parámetro no proporcionado → usa default

        value = params[key]
        param_type = param_def.get("type", "number")

        # Validar tipo
        if param_type == "integer":
            if not isinstance(value, int):
                errors.append(f"{key}: debe ser entero, recibido {type(value).__name__}")
                continue
        elif param_type == "number":
            if not isinstance(value, (int, float)):
                errors.append(f"{key}: debe ser numérico, recibido {type(value).__name__}")
                continue

        # Validar rango
        min_val = param_def.get("min")
        max_val = param_def.get("max")
        if min_val is not None and value < min_val:
            errors.append(f"{key}: valor {value} menor que mínimo {min_val}")
        if max_val is not None and value > max_val:
            errors.append(f"{key}: valor {value} mayor que máximo {max_val}")

    # Advertir sobre parámetros no reconocidos
    known_keys = {p["key"] for p in schema}
    unknown = set(params.keys()) - known_keys
    if unknown:
        errors.append(f"Parámetros no reconocidos: {', '.join(unknown)}")

    return errors


def invalidate_cache() -> None:
    """Fuerza recarga desde DB."""
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0.0
