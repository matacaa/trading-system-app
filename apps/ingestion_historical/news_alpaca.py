"""
news_alpaca.py
──────────────
Descarga noticias financieras de Alpaca Markets API
y las guarda en raw_news_alpaca con un registro por ticker.

Uso:
    from apps.ingestion_historical.news_alpaca import download_all
    download_all(symbols=["AAPL"], days=7)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from shared.config import cfg
from shared.db import sb
from shared.symbols import ALL_SYMBOLS

log = logging.getLogger(__name__)

BASE_URL = "https://data.alpaca.markets/v1beta1/news"


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID": cfg.alpaca_api_key,
        "APCA-API-SECRET-KEY": cfg.alpaca_secret_key,
    }


def fetch_news(symbols: list[str], days: int = 7, limit: int = 50) -> list[dict]:
    """Descarga noticias de Alpaca, paginando automáticamente."""
    start = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_news: list[dict] = []
    page_token = None

    while True:
        params: dict = {
            "start": start, "end": end, "limit": limit,
            "sort": "DESC", "include_content": False,
            "symbols": ",".join(symbols),
        }
        if page_token:
            params["page_token"] = page_token

        try:
            resp = requests.get(BASE_URL, headers=_headers(), params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error(f"Error Alpaca API: {e}")
            break

        batch = data.get("news", [])
        all_news.extend(batch)
        log.info(f"  Página: {len(batch)} noticias (total: {len(all_news)})")

        page_token = data.get("next_page_token")
        if not page_token or not batch:
            break
        time.sleep(0.3)

    return all_news


def parse_news(raw: list[dict], universe: set[str]) -> list[dict]:
    """Convierte cada noticia en filas — una por ticker mencionado del universo."""
    rows = []
    for item in raw:
        mentioned = [t for t in item.get("symbols", []) if t in universe]
        if not mentioned:
            continue

        published = item.get("created_at", "")
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(tz=timezone.utc)

        for ticker in mentioned:
            rows.append({
                "published_at": dt.isoformat(),
                "title": item.get("headline", "")[:500],
                "summary": item.get("summary", "")[:2000],
                "url": item.get("url", "")[:1000],
                "source": item.get("source", "alpaca")[:100],
                "ticker": ticker,
                "category": "general",
            })
    return rows


def save_to_supabase(rows: list[dict]) -> int:
    """Guarda noticias en raw_news_alpaca en batches."""
    if not rows:
        return 0

    inserted = 0
    for i in range(0, len(rows), 100):
        batch = rows[i : i + 100]
        try:
            sb.table("raw_news_alpaca").upsert(batch, on_conflict="url,ticker").execute()
            inserted += len(batch)
        except Exception as e:
            log.error(f"  Error batch {i // 100 + 1}: {e}")
    return inserted


def download_all(symbols: list[str] | None = None, days: int = 7) -> int:
    """Orquesta descarga completa de noticias Alpaca."""
    tickers = symbols or list(ALL_SYMBOLS.keys())
    universe = set(tickers)

    log.info(f"Descargando noticias Alpaca — {len(tickers)} tickers — {days} días...")
    raw = fetch_news(symbols=tickers, days=days)
    log.info(f"Total noticias descargadas: {len(raw)}")

    rows = parse_news(raw, universe)
    log.info(f"Total filas parseadas: {len(rows)}")

    total = save_to_supabase(rows)
    log.info(f"Total guardadas en raw_news_alpaca: {total}")
    return total
