"""
workers/training/main.py
────────────────────────
Training Worker — entrena modelos ML bajo demanda (carril 3).

En producción: Azure ML Compute Job que lee de training-queue (Service Bus).
Escala GPU cluster de 0 a N según la cola.

Flujo:
    1. Recibir job de la cola (user_id, ticker, timeframe, model_names)
    2. Descargar datos del ticker/timeframe
    3. Generar tensores
    4. Entrenar modelos seleccionados
    5. Guardar modelos en Blob Storage
    6. Registrar en silver_model_registry con user_id
    7. Invalidar cache de predicciones en Redis
    8. Notificar al usuario (push)

TODO fase 4: implementar completamente
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger("training-worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def run_training(job: dict) -> dict:
    """Ejecuta un job de training.

    Args:
        job: dict con user_id, ticker, timeframe, model_names, params

    Returns:
        dict con resultados (métricas por modelo)
    """
    user_id = job.get("user_id")
    ticker = job.get("ticker", "AAPL")
    model_names = job.get("model_names", [])

    log.info(f"Training para user={user_id}: {ticker} — modelos: {model_names}")

    # Por ahora delega al pipeline existente
    # TODO fase 4: implementar Service Bus + GPU + Blob Storage
    return {"status": "not_yet_migrated", "message": "Use apps/ml_sandbox/pipeline.py"}


def main():
    log.info("Training worker arrancado")
    log.info("TODO: implementar listener de training-queue")


if __name__ == "__main__":
    main()
