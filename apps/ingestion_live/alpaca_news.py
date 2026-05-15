"""
alpaca_news.py
──────────────
Descarga las últimas noticias desde Alpaca y las guarda en raw_news_rt.

Uso:
    from apps.ingestion_live.alpaca_news import fetch_news
    fetch_news(tickers=["AAPL"], hours=24)
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


def fetch_news(tickers: list[str], hours: int = 24) -> pd.DataFrame:
    """Descarga noticias RT de Alpaca y guarda en raw_news_rt."""
    client = NewsClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)

    end = datetime.now(UTC)
    start = end - timedelta(hours=hours)

    log.info(f"Descargando noticias últimas {hours}h para {tickers}")

    all_news: list[dict] = []

    for ticker in tickers:
        try:
            request = NewsRequest(symbols=ticker, start=start, end=end, limit=50)
            response = client.get_news(request)

            raw = dict(response)
            articles = raw.get("data", {}).get("news", [])

            count = 0
            for article in articles:
                article_symbols = [s.upper() for s in (article.symbols or [])]
                if ticker.upper() not in article_symbols:
                    continue

                created = article.created_at
                if hasattr(created, "isoformat"):
                    created = created.isoformat()

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

            log.info(f"  {ticker}: {count} noticias")

        except Exception as e:
            log.error(f"  Error descargando noticias de {ticker}: {e}")

    if not all_news:
        log.warning("No se obtuvieron noticias")
        return pd.DataFrame()

    try:
        seen_urls = set()
        unique_news = []
        for n in all_news:
            if n["url"] not in seen_urls:
                seen_urls.add(n["url"])
                unique_news.append(n)
        upsert("raw_news_rt", unique_news, conflict="url")
        log.info(f"  {len(unique_news)} noticias guardadas en raw_news_rt")
    except Exception as e:
        log.error(f"  Error guardando noticias: {e}")

    return pd.DataFrame(all_news)
