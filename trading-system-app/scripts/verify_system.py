"""
verify_system.py — Health check del sistema (reescrito Fase 6)
──────────────────────────────────────────────────────────────
Verifica: DB conecta, tablas existen y tienen datos,
modelos en Blob Storage accesibles, endpoints responden.

Uso:
    python scripts/verify_system.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("verify")

REQUIRED_TABLES = [
    "users", "user_preferences", "gold_squawks", "gold_signals",
    "gold_decisions", "gold_trades", "gold_logs",
    "silver_model_registry", "silver_features_rt", "raw_ohlcv_rt",
    "backtest_runs", "backtest_trades", "backtest_metrics",
    # Fase 6 nuevas
    "ticker_universe", "guardrail_registry", "plan_config",
    "training_jobs", "model_type_registry", "user_credits",
]

TABLES_WITH_DATA = [
    ("ticker_universe", 50),
    ("guardrail_registry", 14),
    ("plan_config", 5),
    ("model_type_registry", 6),
    ("silver_model_registry", 1),
]


def check_db() -> bool:
    """Verifica conexión a PostgreSQL y tablas."""
    try:
        from shared.db import query

        # Conexión
        rows = query("SELECT 1 AS ok")
        assert rows[0]["ok"] == 1
        log.info("✅ PostgreSQL: conexión OK")

        # Tablas
        existing = {
            r["tablename"]
            for r in query(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        missing = [t for t in REQUIRED_TABLES if t not in existing]
        if missing:
            log.warning("⚠️  Tablas faltantes: %s", missing)
        else:
            log.info("✅ PostgreSQL: %d tablas requeridas presentes", len(REQUIRED_TABLES))

        # Datos mínimos
        for table, min_rows in TABLES_WITH_DATA:
            if table not in existing:
                continue
            count = query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
            if count < min_rows:
                log.warning("⚠️  %s: %d filas (esperadas >= %d)", table, count, min_rows)
            else:
                log.info("✅ %s: %d filas", table, count)

        return not missing

    except Exception as e:
        log.error("❌ PostgreSQL: %s", e)
        return False


def check_blob_storage() -> bool:
    """Verifica acceso a Blob Storage y modelos."""
    conn_str = os.getenv("AZURE_STORAGE_CONN_STR", "")
    if not conn_str:
        log.warning("⚠️  AZURE_STORAGE_CONN_STR no configurado — Blob Storage no verificado")
        return True

    try:
        from shared.blob_storage import list_models

        models = list_models("system/")
        if models:
            log.info("✅ Blob Storage: %d modelos sistema encontrados", len(models))
            for m in models[:6]:
                log.info("   %s", m)
        else:
            log.warning("⚠️  Blob Storage: sin modelos sistema (subir con paso 6.2)")
        return True

    except Exception as e:
        log.error("❌ Blob Storage: %s", e)
        return False


def check_endpoints() -> bool:
    """Verifica que los endpoints responden."""
    import requests

    api_url = os.getenv("API_URL", "http://localhost:8000")
    endpoints = ["/api/health"]

    all_ok = True
    for ep in endpoints:
        try:
            r = requests.get(f"{api_url}{ep}", timeout=5)
            if r.status_code == 200:
                log.info("✅ %s: 200 OK", ep)
            else:
                log.warning("⚠️  %s: HTTP %d", ep, r.status_code)
                all_ok = False
        except Exception as e:
            log.warning("⚠️  %s: no accesible (%s)", ep, e)
            all_ok = False

    return all_ok


def main():
    log.info("=" * 60)
    log.info("Verificación del sistema Squawks ML")
    log.info("=" * 60)

    results = {
        "PostgreSQL": check_db(),
        "Blob Storage": check_blob_storage(),
    }

    # Endpoints solo si hay API_URL o estamos en local
    if os.getenv("API_URL") or os.getenv("CHECK_ENDPOINTS"):
        results["Endpoints"] = check_endpoints()

    log.info("=" * 60)
    all_ok = all(results.values())
    for name, ok in results.items():
        log.info("%s %s", "✅" if ok else "❌", name)
    log.info("=" * 60)
    log.info("Estado global: %s", "OK ✅" if all_ok else "PROBLEMAS ⚠️")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
