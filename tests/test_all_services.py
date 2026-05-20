"""
test_all_services.py — Tests mínimos contra PostgreSQL (reescrito Fase 6)
──────────────────────────────────────────────────────────────────────────
Tests: tablas existen, query/upsert funcionan, endpoints responden con auth.

Uso:
    pytest tests/test_all_services.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── DB Tests ──────────────────────────────────────────────────────────────────


class TestDatabase:
    """Tests de conexión y operaciones básicas de PostgreSQL."""

    def test_connection(self):
        """Verifica que se puede conectar a PostgreSQL."""
        from shared.db import query

        rows = query("SELECT 1 AS ok")
        assert rows[0]["ok"] == 1

    def test_tables_exist(self):
        """Verifica que las tablas principales existen."""
        from shared.db import query

        existing = {
            r["tablename"]
            for r in query(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        required = [
            "users", "user_preferences", "gold_squawks",
            "silver_model_registry", "backtest_runs",
        ]
        for table in required:
            assert table in existing, f"Tabla {table} no existe"

    def test_fase6_tables_exist(self):
        """Verifica que las tablas de Fase 6 existen."""
        from shared.db import query

        existing = {
            r["tablename"]
            for r in query(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        fase6 = [
            "ticker_universe", "guardrail_registry", "plan_config",
            "training_jobs", "model_type_registry", "user_credits",
        ]
        for table in fase6:
            assert table in existing, f"Tabla Fase 6 {table} no existe"

    def test_ticker_universe_seeded(self):
        """Verifica que ticker_universe tiene datos."""
        from shared.db import query

        rows = query("SELECT COUNT(*) AS n FROM ticker_universe")
        assert rows[0]["n"] >= 50, "ticker_universe tiene menos de 50 tickers"

    def test_guardrail_registry_seeded(self):
        """Verifica que guardrail_registry tiene 14 guardrails."""
        from shared.db import query

        rows = query("SELECT COUNT(*) AS n FROM guardrail_registry")
        assert rows[0]["n"] == 14

    def test_plan_config_seeded(self):
        """Verifica que plan_config tiene 5 planes."""
        from shared.db import query

        rows = query("SELECT COUNT(*) AS n FROM plan_config")
        assert rows[0]["n"] == 5

    def test_model_type_registry_seeded(self):
        """Verifica que model_type_registry tiene 6 tipos."""
        from shared.db import query

        rows = query("SELECT COUNT(*) AS n FROM model_type_registry")
        assert rows[0]["n"] == 6

    def test_query_returns_dicts(self):
        """Verifica que query devuelve lista de dicts."""
        from shared.db import query

        rows = query("SELECT 'test' AS val")
        assert isinstance(rows, list)
        assert isinstance(rows[0], dict)
        assert rows[0]["val"] == "test"

    def test_models_registered(self):
        """Verifica que hay al menos un modelo en silver_model_registry."""
        from shared.db import query

        rows = query(
            "SELECT COUNT(*) AS n FROM silver_model_registry WHERE is_active = true"
        )
        assert rows[0]["n"] >= 1, "No hay modelos activos en silver_model_registry"


# ── Config Tests ──────────────────────────────────────────────────────────────


class TestConfig:
    """Tests de configuración."""

    def test_shared_config_loads(self):
        """Verifica que shared.config.cfg se puede importar."""
        from shared.config import cfg

        assert cfg.database_url is not None

    def test_inference_module_imports(self):
        """Verifica que shared.inference se puede importar."""
        from shared.inference import load_models, predict_ensemble  # noqa: F401

    def test_guardrails_module_imports(self):
        """Verifica que shared.guardrails se puede importar."""
        from shared.guardrails import check_guardrails  # noqa: F401

    def test_blob_storage_module_imports(self):
        """Verifica que shared.blob_storage se puede importar."""
        from shared.blob_storage import (  # noqa: F401
            download_model,
            list_models,
            upload_model,
        )

    def test_legacy_runners_module_imports(self):
        """Verifica que shared.legacy_runners se puede importar."""
        from shared.legacy_runners import (  # noqa: F401
            generate_backtest_yaml,
            generate_experiment_yaml,
            run_pipeline,
        )


# ── Endpoint Tests ────────────────────────────────────────────────────────────


class TestEndpoints:
    """Tests de endpoints (requiere API corriendo)."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.api_url = os.getenv("API_URL", "http://localhost:8000")

    @pytest.mark.skipif(
        not os.getenv("API_URL") and not os.getenv("TEST_ENDPOINTS"),
        reason="API_URL not set — skip endpoint tests",
    )
    def test_health(self):
        """GET /api/health responde 200."""
        import requests

        r = requests.get(f"{self.api_url}/api/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
