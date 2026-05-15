"""
services/features/main.py
─────────────────────────
Feature Engine — calcula indicadores técnicos y sentimiento.
Compartido para todos los usuarios.

En producción: escucha evento 'ingestion_complete', calcula, publica 'features_ready'.
Por ahora: ejecuta como scheduler independiente tras la ingesta.

Uso:
    python -m services.features.main
    python -m services.features.main --once
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from apps.ingestion_live.finbert_rt import get_sentiment
from apps.ingestion_live.silver_rt import compute_silver_rt
from shared.symbols import ALL_SYMBOLS

log = logging.getLogger("features")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def run(tickers: list[str] | None = None, timeframe: str = "1m"):
    """Calcula features silver + sentimiento."""
    tickers = tickers or list(ALL_SYMBOLS.keys())
    start = time.time()

    log.info(f"Features: {len(tickers)} tickers...")

    try:
        sentiment = get_sentiment(tickers=tickers, hours=24)
        log.info(f"  Sentiment OK ({time.time()-start:.1f}s)")
    except Exception as e:
        log.error(f"  Error sentiment: {e}")

    try:
        df = compute_silver_rt(tickers=tickers, timeframe=timeframe)
        log.info(f"  Silver RT: {len(df)} filas ({time.time()-start:.1f}s)")
    except Exception as e:
        log.error(f"  Error silver: {e}")

    # TODO fase 3: publicar evento features_ready
    log.info(f"Features completado en {time.time()-start:.1f}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=1)
    args = parser.parse_args()

    if args.once:
        run()
        return

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run, trigger="interval", minutes=args.interval,
        next_run_time=datetime.now(UTC), max_instances=1, coalesce=True,
    )
    log.info(f"Feature engine — cada {args.interval} min")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Feature engine detenido")


if __name__ == "__main__":
    main()
