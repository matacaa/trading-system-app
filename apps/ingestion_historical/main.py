"""
main.py — ingestion_historical
──────────────────────────────
Pipeline batch semanal:
    1. Descarga RAW (OHLCV yfinance + noticias Alpaca)
    2. FinBERT → silver_news_alpaca
    3. Genera capa SILVER (indicadores via shared.indicators)
    4. Genera tensores locales (.npy)

Uso:
    python -m apps.ingestion_historical.main
    python -m apps.ingestion_historical.main --only-silver --tickers AAPL
    python -m apps.ingestion_historical.main --skip-tensors
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime

from shared.symbols import ALL_SYMBOLS
from shared.utils.logging import setup_logging
from apps.ingestion_historical.ingestion import run_update
from apps.ingestion_historical.news_alpaca import download_all as download_news
from apps.ingestion_historical.finbert import run_finbert
from apps.ingestion_historical.silver import run_silver
from apps.ingestion_historical.tensor import run_tensor

log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Pipeline semanal ingestion_historical")
    parser.add_argument("--tickers", nargs="+", help="Tickers concretos")
    parser.add_argument("--skip-raw", action="store_true")
    parser.add_argument("--skip-finbert", action="store_true")
    parser.add_argument("--skip-silver", action="store_true")
    parser.add_argument("--skip-tensors", action="store_true")
    parser.add_argument("--only-silver", action="store_true")
    parser.add_argument("--only-tensors", action="store_true")
    parser.add_argument("--only-finbert", action="store_true")
    args = parser.parse_args()

    setup_logging(app_name="ingestion-historical")

    tickers = args.tickers or list(ALL_SYMBOLS.keys())

    if args.only_silver:
        args.skip_raw = args.skip_finbert = args.skip_tensors = True
    if args.only_tensors:
        args.skip_raw = args.skip_finbert = args.skip_silver = True
    if args.only_finbert:
        args.skip_raw = args.skip_silver = args.skip_tensors = True

    start = datetime.now()
    log.info(f"Pipeline histórico — {len(tickers)} tickers")

    # Paso 1: RAW (OHLCV + noticias)
    if not args.skip_raw:
        log.info("Paso 1 — Descarga RAW...")
        t0 = time.time()
        run_update(tickers, intervals=["1m", "5m", "15m"])
        log.info(f"  OHLCV completado en {time.time() - t0:.1f}s")

        t0 = time.time()
        download_news(symbols=tickers, days=7)
        log.info(f"  Noticias completadas en {time.time() - t0:.1f}s")

    # Paso 2: FinBERT
    if not args.skip_finbert:
        log.info("Paso 2 — FinBERT Sentiment...")
        t0 = time.time()
        total = run_finbert()
        log.info(f"  FinBERT: {total} noticias procesadas en {time.time() - t0:.1f}s")

    # Paso 3: SILVER
    if not args.skip_silver:
        log.info("Paso 3 — Capa SILVER...")
        t0 = time.time()
        run_silver(tickers, intervals=["1m", "5m", "15m"], enrich_news=True)
        log.info(f"  Silver completado en {time.time() - t0:.1f}s")

    # Paso 4: Tensores
    if not args.skip_tensors:
        log.info("Paso 4 — Tensores...")
        t0 = time.time()
        run_tensor(intervals=["1m", "5m", "15m"], normalize=True)
        log.info(f"  Tensores completados en {time.time() - t0:.1f}s")

    elapsed = round((datetime.now() - start).total_seconds(), 1)
    log.info(f"Pipeline completado en {elapsed}s")


if __name__ == "__main__":
    main()
