"""
alpaca_news.py
──────────────
Descarga las últimas noticias desde Alpaca y las guarda en raw_news_rt.

Fase 6.13: batching de tickers (20 por request en vez de 1).
Alpaca acepta múltiples símbolos en un solo request → menos llamadas API.

Uso:
    from apps.ingestion_live.alpaca_news import fetch_news
    fetch_news(tickers=["AAPL", "MSFT", "GOOG"], hours=24)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pandas as pd
from alpaca.data.historical import NewsClient
from alpaca.data.requests import NewsRequest

from shared.config import cfg
from shared.db import upsert

log = logging.getLogger(__name__)

# Tamaño del batch (Alpaca soporta múltiples símbolos por request)
BATCH_SIZE = 20


def fetch_news(tickers: list[str], hours: int = 24) -> pd.DataFrame:
    """
    Descarga noticias RT de Alpaca y guarda en raw_news_rt.

    Agrupa tickers en batches de BATCH_SIZE para minimizar llamadas API.
    """
    client = NewsClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)

    end = datetime.now(UTC)
    start = end - timedelta(hours=hours)

    log.info(
        "Descargando noticias últimas %dh para %d tickers (batches de %d)",
        hours, len(tickers), BATCH_SIZE,
    )

    all_news: list[dict] = []
    tickers_upper = {t.upper() for t in tickers}

    # Agrupar tickers en batches
    batches = [tickers[i:i + BATCH_SIZE] for i in range(0, len(tickers), BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        try:
            request = NewsRequest(
                symbols=batch, start=start, end=end, limit=50 * len(batch),
            )
            response = client.get_news(request)

            raw = dict(response)
            articles = raw.get("data", {}).get("news", [])

            count = 0
            for article in articles:
                article_symbols = [s.upper() for s in (article.symbols or [])]

                # Una noticia puede aplicar a múltiples tickers del batch
                matching_tickers = [s for s in article_symbols if s in tickers_upper]

                created = article.created_at
                if hasattr(created, "isoformat"):
                    created = created.isoformat()

                for ticker in matching_tickers:
                    all_news.append({
                        "ticker": ticker,
                        "published_at": created,
                        "title": article.headline or "",
                        "summary": article.summary or "",
                        "url": article.url or "",
                        "source": article.source or "alpaca",
                        "fetched_at": datetime.now(UTC).isoformat(),
                    })
                    count += 1

            log.info(
                "  Batch %d/%d (%s): %d noticias",
                batch_idx + 1, len(batches),
                ",".join(batch[:3]) + ("..." if len(batch) > 3 else ""),
                count,
            )

        except Exception as e:
            log.error("  Error batch %d/%d: %s", batch_idx + 1, len(batches), e)

    if not all_news:
        log.warning("No se obtuvieron noticias")
        return pd.DataFrame()

    # Deduplicar por (ticker, url)
    seen: set[tuple[str, str]] = set()
    unique_news: list[dict] = []
    for n in all_news:
        key = (n["ticker"], n["url"])
        if key not in seen:
            seen.add(key)
            unique_news.append(n)

    try:
        upsert("raw_news_rt", unique_news, conflict="url")
        log.info("  %d noticias guardadas en raw_news_rt", len(unique_news))
    except Exception as e:
        log.error("  Error guardando noticias: %s", e)

    return pd.DataFrame(all_news)
