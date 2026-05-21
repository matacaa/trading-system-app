"""
finbert_rt.py
─────────────
Analiza sentiment de noticias RT con FinBERT.
Lee de raw_news_rt y devuelve sentiment agregado por ticker.

Fase 6.13: batch inference — pasa todos los titulares de todos los tickers
de una sola vez al pipeline en vez de uno a uno.

Uso:
    from apps.ingestion_live.finbert_rt import get_sentiment
    sentiment = get_sentiment(tickers=["AAPL", "MSFT"], hours=24)
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from shared.config import cfg
from shared.db import query

log = logging.getLogger(__name__)

# Cache del pipeline FinBERT (se carga una sola vez por proceso)
_finbert_pipeline = None

if cfg.huggingface_token:
    os.environ["HF_TOKEN"] = cfg.huggingface_token

# Batch size para FinBERT (ajustar según GPU/RAM disponible)
FINBERT_BATCH_SIZE = 32


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

    Usa batch inference: recopila TODOS los titulares, los pasa al modelo
    en un solo batch, y luego agrupa resultados por ticker.

    Returns:
        {"AAPL": {"label": "positive", "score": 0.82, "encoded": 1}, ...}
    """
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    result: dict[str, dict] = {}
    default = {"label": "neutral", "score": 0.0, "encoded": 0}

    try:
        finbert = _get_finbert()
    except Exception as e:
        log.error("Error cargando FinBERT: %s", e)
        return {t: {**default} for t in tickers}

    # 1. Recopilar todos los titulares de todos los tickers en una sola query
    all_headlines: list[str] = []
    headline_ticker_map: list[str] = []  # índice paralelo: a qué ticker pertenece

    try:
        noticias = query(
            """SELECT ticker, title FROM raw_news_rt
               WHERE ticker = ANY(%s) AND published_at >= %s
               ORDER BY published_at DESC""",
            [tickers, cutoff],
        )
    except Exception as e:
        log.error("Error consultando noticias: %s", e)
        return {t: {**default} for t in tickers}

    # Agrupar por ticker y limitar a 20 por ticker
    ticker_counts: dict[str, int] = {}
    for n in noticias:
        t = n["ticker"]
        title = n.get("title", "").strip()
        if not title:
            continue
        count = ticker_counts.get(t, 0)
        if count >= 20:
            continue
        ticker_counts[t] = count + 1
        all_headlines.append(title)
        headline_ticker_map.append(t)

    if not all_headlines:
        log.info("Sin titulares para analizar — todos neutral")
        return {t: {**default} for t in tickers}

    log.info("Analizando %d titulares en batch para %d tickers...", len(all_headlines), len(tickers))

    # 2. Batch inference — pasar TODOS los titulares de una vez
    try:
        predictions = finbert(all_headlines, batch_size=FINBERT_BATCH_SIZE)
    except Exception as e:
        log.error("Error en batch inference FinBERT: %s", e)
        return {t: {**default} for t in tickers}

    # 3. Agrupar puntuaciones por ticker
    ticker_scores: dict[str, list[float]] = {t: [] for t in tickers}

    for pred, ticker in zip(predictions, headline_ticker_map, strict=True):
        label = pred["label"].lower()
        score = pred["score"]
        if label == "positive":
            ticker_scores[ticker].append(score)
        elif label == "negative":
            ticker_scores[ticker].append(-score)
        else:
            ticker_scores[ticker].append(0.0)

    # 4. Calcular promedio por ticker
    for ticker in tickers:
        scores = ticker_scores.get(ticker, [])
        if not scores:
            result[ticker] = {**default}
            continue

        promedio = round(sum(scores) / len(scores), 3)
        label = "positive" if promedio > 0.1 else "negative" if promedio < -0.1 else "neutral"

        result[ticker] = {
            "label": label,
            "score": promedio,
            "encoded": _encode_label(label),
        }
        log.info("  %s: %s (%.3f) — %d titulares", ticker, label, promedio, len(scores))

    return result
