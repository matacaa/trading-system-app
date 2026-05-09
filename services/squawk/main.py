"""
services/squawk/main.py
───────────────────────
Squawk Service — genera alertas con audio y las entrega (carril 1).

En producción: escucha 'decision_made', genera texto del squawk,
llama a Azure Speech TTS, sube audio a Blob Storage,
envía por SignalR (feed) y Notification Hubs (push).

TODO fase 3: implementar completamente.
"""

from __future__ import annotations

import logging

log = logging.getLogger("squawk")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def generate_squawk_text(signal: dict) -> str:
    """Genera el texto del squawk a partir de una señal.

    Args:
        signal: dict con ticker, decision, score, sentiment, etc.

    Returns:
        Texto legible para TTS
    """
    ticker = signal.get("ticker", "???")
    score = signal.get("score", 0)
    decision = signal.get("decision", "HOLD")

    if decision == "BUY":
        return f"{ticker}: señal alcista, score {score:.0f} por ciento"
    else:
        return f"{ticker}: sin señal, score {score:.0f} por ciento"


def determine_priority(signal: dict) -> str:
    """Determina la prioridad del squawk.

    Returns: "urgent", "normal", "low"
    """
    score = signal.get("score", 0)
    if score >= 90:
        return "urgent"
    elif score >= 70:
        return "normal"
    return "low"


# TODO fase 3: integrar Azure Speech TTS
# TODO fase 3: integrar Blob Storage para audios
# TODO fase 3: integrar SignalR para feed en tiempo real
# TODO fase 3: integrar Notification Hubs para push

if __name__ == "__main__":
    log.info("Squawk service — not yet implemented")
    log.info("This service will be built in phase 3")
