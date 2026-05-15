"""
services/decision/main.py
─────────────────────────
Decision Engine — aplica guardrails por usuario (carril 1).

En producción: escucha 'signals_ready', aplica guardrails de cada usuario,
publica 'decision_made'.

La separación inference/decision es lo que habilita el cacheo inteligente
de backtests: las predicciones del modelo se cachean, las decisiones se
recalculan instantáneamente cuando el usuario cambia un guardrail.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.guardrails import decide

log = logging.getLogger("decision")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def run_for_user(ticker: str, score: float, row, user_guardrails: dict, estado: dict) -> dict:
    """Aplica los guardrails de un usuario específico.

    Args:
        ticker:          ticker evaluado
        score:           score del ensemble (0-100)
        row:             última vela con features
        user_guardrails: config de guardrails del usuario
        estado:          estado del portfolio del usuario

    Returns:
        dict con decision, score_final, motivo_rechazo
    """
    return decide(ticker, score, row, user_guardrails, estado)


# TODO fase 3: listener de signals_ready
# TODO fase 3: publicar decision_made

if __name__ == "__main__":
    log.info("Decision engine — standalone mode")
