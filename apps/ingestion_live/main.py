"""
main.py — ingestion_live
────────────────────────
Entry point para la ingesta en tiempo real.

Flujo:
    1. Descargar precios RT desde Alpaca → raw_ohlcv_rt
    2. Descargar noticias RT desde Alpaca → raw_news_rt
    3. Calcular sentiment con FinBERT
    4. Calcular indicadores → silver_features_rt

Uso:
    python -m apps.ingestion_live.main --tickers AAPL
"""

from __future__ import annotations

import argparse
import logging
import time

from apps.ingestion_live.alpaca_news import fetch_news
from apps.ingestion_live.alpaca_prices import fetch_prices
from apps.ingestion_live.finbert_rt import get_sentiment
from apps.ingestion_live.silver_rt import compute_silver_rt
from shared.symbols import ALL_SYMBOLS
from shared.utils.logging import setup_logging

log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Live Ingestion Pipeline")
    parser.add_argument("--tickers", nargs="+", default=list(ALL_SYMBOLS.keys()), help="Tickers")
    parser.add_argument("--timeframe", default="1m", help="Timeframe")
    parser.add_argument("--skip-news", action="store_true", help="Omitir noticias y sentiment")
    args = parser.parse_args()

    setup_logging(app_name="ingestion-live")

    log.info(f"Ingesta live: {args.tickers} @ {args.timeframe}")

    # 1. Precios
    log.info("Descargando precios RT...")
    t0 = time.time()
    fetch_prices(tickers=args.tickers, timeframe=args.timeframe, bars=100)
    log.info(f"  Precios: {time.time() - t0:.1f}s")

    # 2-3. Noticias + Sentiment
    if not args.skip_news:
        log.info("Descargando noticias RT...")
        t0 = time.time()
        fetch_news(tickers=args.tickers, hours=24)
        log.info(f"  Noticias: {time.time() - t0:.1f}s")

        log.info("Calculando sentiment...")
        t0 = time.time()
        get_sentiment(tickers=args.tickers, hours=24)
        log.info(f"  Sentiment: {time.time() - t0:.1f}s")

    # 4. Silver (N-10: sentiment se consulta internamente via enrich_sentiment)
    log.info("Calculando indicadores silver RT...")
    t0 = time.time()
    df = compute_silver_rt(tickers=args.tickers, timeframe=args.timeframe)
    log.info(f"  Silver: {time.time() - t0:.1f}s")

    if df.empty:
        log.warning("Sin datos procesados")
    else:
        log.info(f"Procesadas {len(df)} filas totales")


if __name__ == "__main__":
    main()
