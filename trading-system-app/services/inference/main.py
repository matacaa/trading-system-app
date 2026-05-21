"""
services/inference/main.py
──────────────────────────
Inference Service — ejecuta los modelos ML por usuario (carril 1).

En producción: escucha 'features_ready', itera usuarios activos,
ejecuta predicciones con batching por modelo+ticker.

Uso:
    python -m services.inference.main --once
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from shared.inference import predict_ensemble

log = logging.getLogger("inference")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def run_for_user(user_config: dict, df_silver, modelos: list):
    """Ejecuta inference para un usuario con su config.

    Args:
        user_config: configuración del usuario (tickers, ensemble weights)
        df_silver:   DataFrame con features compartidos
        modelos:     modelos cargados
    """
    tickers = user_config.get("tickers", [])
    signals_all = []

    for ticker in tickers:
        df_ticker = df_silver[df_silver["ticker"] == ticker]
        if df_ticker.empty:
            continue

        row = df_ticker.iloc[-1]
        score, detalle, signals = predict_ensemble(row, modelos, df_hist=df_ticker)
        signals_all.extend(signals)

        log.info(f"  {ticker}: score={score:.1f} ({len(signals)} señales)")

    return signals_all


# TODO fase 3: convertir en listener de eventos features_ready
# TODO fase 3: iterar sobre usuarios activos
# TODO fase 3: batching por modelo+ticker

if __name__ == "__main__":
    log.info("Inference service — standalone mode")
    log.info("Use trading_engine/main.py for the full pipeline until migration is complete")
