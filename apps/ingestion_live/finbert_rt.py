"""
finbert_rt.py
─────────────
Analiza sentiment de noticias RT con FinBERT.
Lee de raw_news_rt y devuelve sentiment agregado por ticker.

Uso:
    from apps.ingestion_live.finbert_rt import get_sentiment
    sentiment = get_sentiment(tickers=["AAPL"], hours=24)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from shared.config import cfg
from shared.db import sb

log = logging.getLogger(__name__)

# Cache del pipeline FinBERT (se carga una sola vez por proceso)
_finbert_pipeline = None

if cfg.huggingface_token:
    os.environ["HF_TOKEN"] = cfg.huggingface_token


def _get_finbert():
    global _finbert_pipeline
    if _finbert_pipeline is None:
        log.info("Cargando modelo FinBERT...")
        from transformers import pipeline as hf_pipeline

        _finbert_pipeline = hf_pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            truncation=True,
            max_length=512,
        )
        log.info("FinBERT cargado")
    return _finbert_pipeline


def _encode_label(label: str) -> int:
    return {"positive": 1, "neutral": 0, "negative": -1}.get(label, 0)


def get_sentiment(tickers: list[str], hours: int = 24) -> dict[str, dict]:
    """
    Lee noticias de raw_news_rt y calcula sentiment por ticker.

    Returns:
        {"AAPL": {"label": "positive", "score": 0.82, "encoded": 1}, ...}
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result: dict[str, dict] = {}

    try:
        finbert = _get_finbert()
    except Exception as e:
        log.error(f"Error cargando FinBERT: {e}")
        return {t: {"label": "neutral", "score": 0.0, "encoded": 0} for t in tickers}

    for ticker in tickers:
        try:
            resp = (
                sb.table("raw_news_rt")
                .select("title, published_at")
                .eq("ticker", ticker)
                .gte("published_at", cutoff)
                .order("published_at", desc=True)
                .limit(20)
                .execute()
            )

            noticias = resp.data or []

            if not noticias:
                log.info(f"  {ticker}: sin noticias — neutral")
                result[ticker] = {"label": "neutral", "score": 0.0, "encoded": 0}
                continue

            titulares = [n["title"] for n in noticias if n.get("title")]
            if not titulares:
                result[ticker] = {"label": "neutral", "score": 0.0, "encoded": 0}
                continue

            log.info(f"  {ticker}: analizando {len(titulares)} titulares...")

            puntuaciones: list[float] = []
            for titular in titulares:
                try:
                    res = finbert(titular)[0]
                    label = res["label"].lower()
                    score = res["score"]
                    if label == "positive":
                        puntuaciones.append(score)
                    elif label == "negative":
                        puntuaciones.append(-score)
                    else:
                        puntuaciones.append(0.0)
                except Exception:
                    continue

            if not puntuaciones:
                result[ticker] = {"label": "neutral", "score": 0.0, "encoded": 0}
                continue

            promedio = round(sum(puntuaciones) / len(puntuaciones), 3)
            label = "positive" if promedio > 0.1 else "negative" if promedio < -0.1 else "neutral"

            result[ticker] = {
                "label": label,
                "score": promedio,
                "encoded": _encode_label(label),
            }
            log.info(f"  {ticker}: {label} ({promedio})")

        except Exception as e:
            log.error(f"  Error sentiment {ticker}: {e}")
            result[ticker] = {"label": "neutral", "score": 0.0, "encoded": 0}

    return result
