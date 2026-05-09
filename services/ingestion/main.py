"""
services/ingestion/main.py
──────────────────────────
Servicio de ingesta — compartido para todos los usuarios.
Descarga precios y noticias cada minuto.

En producción: Container App always-on.
Comunicación: publica evento 'ingestion_complete' al terminar.

Uso:
    python -m services.ingestion.main
    python -m services.ingestion.main --once
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from apps.ingestion_live.alpaca_prices import fetch_prices
from apps.ingestion_live.alpaca_news import fetch_news
from shared.symbols import ALL_SYMBOLS

log = logging.getLogger("ingestion")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def run(tickers: list[str] | None = None, timeframe: str = "1m"):
    """Ejecuta una iteración de ingesta."""
    tickers = tickers or list(ALL_SYMBOLS.keys())
    start = time.time()

    log.info(f"Ingesta: {len(tickers)} tickers...")
    try:
        fetch_prices(tickers=tickers, timeframe=timeframe, bars=100)
        log.info(f"  Precios OK ({time.time()-start:.1f}s)")
    except Exception as e:
        log.error(f"  Error precios: {e}")

    try:
        fetch_news(tickers=tickers, hours=24)
        log.info(f"  Noticias OK ({time.time()-start:.1f}s)")
    except Exception as e:
        log.error(f"  Error noticias: {e}")

    # TODO fase 3: publicar evento ingestion_complete en Redis/Service Bus
    log.info(f"Ingesta completada en {time.time()-start:.1f}s")


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
        next_run_time=datetime.now(timezone.utc), max_instances=1, coalesce=True,
    )
    log.info(f"Ingestion service — cada {args.interval} min")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Ingestion service detenido")


if __name__ == "__main__":
    main()
