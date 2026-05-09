"""
workers/backtest/main.py
────────────────────────
Backtest Worker — ejecuta backtests bajo demanda (carril 2).

En producción: Container Apps Job que lee de backtest-queue (Service Bus).
Escala de 0 a N según la cola.

Optimización clave: cacheo inteligente.
Si el usuario solo cambió guardrails, reutiliza predicciones cacheadas
y recalcula solo la capa de decisión (~200ms vs ~30s).

TODO fase 4: integrar Service Bus + Redis cache
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger("backtest-worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def run_backtest(job: dict) -> dict:
    """Ejecuta un backtest completo.

    Args:
        job: dict con user_id, config (tickers, modelos, guardrails), ventana temporal

    Returns:
        dict con resultados (trades, métricas, etc.)

    TODO:
        1. Check cache: ¿existen predicciones para este modelo+ticker+ventana?
        2. Si cache hit + solo cambiaron guardrails → replay rápido (~200ms)
        3. Si cache miss → inference completa sobre velas históricas
        4. Aplicar guardrails del usuario
        5. Simular trades
        6. Calcular métricas
        7. Guardar en PostgreSQL
        8. Notificar al usuario (push)
    """
    user_id = job.get("user_id")
    config = job.get("config", {})

    log.info(f"Backtest para user={user_id}: {config.get('tickers', [])}")

    # Por ahora delega al backtest existente
    # TODO fase 4: implementar cacheo + Service Bus
    return {"status": "not_yet_migrated", "message": "Use apps/ml_sandbox/backtest.py"}


def main():
    """Worker principal — en producción lee de Service Bus."""
    log.info("Backtest worker arrancado")
    log.info("TODO: implementar listener de backtest-queue")
    # TODO fase 4:
    # while True:
    #     job = service_bus.receive("backtest-queue")
    #     result = run_backtest(job)
    #     notify_user(job["user_id"], result)


if __name__ == "__main__":
    main()
