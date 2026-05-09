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
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.historical import NewsClient
from alpaca.data.requests import NewsRequest

from shared.config import cfg
from shared.db import sb

log = logging.getLogger(__name__)


def fetch_news(tickers: list[str], hours: int = 24) -> pd.DataFrame:
    """Descarga noticias RT de Alpaca y guarda en raw_news_rt."""
    client = NewsClient(cfg.alpaca_api_key, cfg.alpaca_secret_key)

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    log.info(f"Descargando noticias últimas {hours}h para {tickers}")

    all_news: list[dict] = []

    for ticker in tickers:
        try:
            request = NewsRequest(symbols=ticker, start=start, end=end, limit=50)
            response = client.get_news(request)

            # N-02: alpaca-py devuelve .news como lista plana, no indexada por ticker
            articles = response.news if hasattr(response, "news") else []

            for article in articles:
                # Filtrar solo artículos que mencionan este ticker
                article_symbols = [s.upper() for s in (article.symbols or [])]
                if ticker.upper() not in article_symbols:
                    continue

                all_news.append({
                    "ticker": ticker,
                    "published_at": article.created_at.isoformat() if article.created_at else None,
                    "title": article.headline,
                    "summary": article.summary or "",
                    "url": article.url or "",
                    "source": article.source or "alpaca",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })

            log.info(f"  {ticker}: {len([a for a in articles if ticker.upper() in [s.upper() for s in (a.symbols or [])]])} noticias")

        except Exception as e:
            log.error(f"  Error descargando noticias de {ticker}: {e}")

    if not all_news:
        log.warning("No se obtuvieron noticias")
        return pd.DataFrame()

    try:
        sb.table("raw_news_rt").upsert(all_news, on_conflict="url").execute()
        log.info(f"  {len(all_news)} noticias guardadas en raw_news_rt")
    except Exception as e:
        log.error(f"  Error guardando noticias: {e}")

    return pd.DataFrame(all_news)
