"""
finbert.py
──────────
Analiza sentiment de noticias en raw_news_alpaca con FinBERT
y guarda resultados en silver_news_alpaca.

Modelo: ProsusAI/finbert
Output: positive / negative / neutral + score de confianza

Uso:
    from apps.ingestion_historical.finbert import run_finbert
    run_finbert()
"""

from __future__ import annotations

import logging
import os

from shared.config import cfg
from shared.db import query, upsert

log = logging.getLogger(__name__)

# Configurar token HuggingFace para descargar modelo
if cfg.huggingface_token:
    os.environ["HF_TOKEN"] = cfg.huggingface_token


def load_finbert():
    """Carga el modelo FinBERT (~500MB primera vez)."""
    from transformers import pipeline as hf_pipeline

    log.info("Cargando modelo FinBERT...")
    return hf_pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        truncation=True,
        max_length=512,
    )


def analyze_sentiment(texts: list[str], model) -> list[dict]:
    """Analiza sentiment de una lista de textos."""
    results = []
    for text in texts:
        try:
            if not text or not text.strip():
                results.append({"label": "neutral", "score": 0.0})
                continue
            result = model(text[:512])
            results.append({
                "label": result[0]["label"],
                "score": round(result[0]["score"], 4),
            })
        except Exception as e:
            log.warning(f"  Error analizando texto: {e}")
            results.append({"label": "neutral", "score": 0.0})
    return results


def load_raw_news() -> list[dict]:
    """Carga noticias de raw_news_alpaca aún no procesadas."""
    # URLs ya procesadas
    processed_rows = query("SELECT url, ticker FROM silver_news_alpaca")
    processed = {(r["url"], r["ticker"]) for r in processed_rows}

    log.info(f"  Ya procesadas: {len(processed)}")

    # Noticias pendientes
    all_rows = query("SELECT * FROM raw_news_alpaca ORDER BY published_at")
    pending = [r for r in all_rows if (r["url"], r["ticker"]) not in processed]

    log.info(f"  Pendientes: {len(pending)}")
    return pending


def save_to_silver(rows: list[dict]) -> int:
    """Guarda noticias con sentiment en silver_news_alpaca."""
    if not rows:
        return 0

    inserted = 0
    for i in range(0, len(rows), 100):
        batch = rows[i : i + 100]
        try:
            upsert("silver_news_alpaca", batch, conflict="url,ticker")
            inserted += len(batch)
        except Exception as e:
            log.error(f"  Error batch {i // 100 + 1}: {e}")
    return inserted


def run_finbert() -> int:
    """Pipeline: raw_news_alpaca → FinBERT → silver_news_alpaca."""
    log.info("Iniciando pipeline FinBERT...")

    raw_news = load_raw_news()
    if not raw_news:
        log.info("No hay noticias pendientes")
        return 0

    model = load_finbert()

    log.info(f"Analizando sentiment de {len(raw_news)} noticias...")
    texts = [r.get("title", "") for r in raw_news]
    sentiments = analyze_sentiment(texts, model)

    rows = []
    for r, s in zip(raw_news, sentiments, strict=False):
        rows.append({
            "published_at": r["published_at"],
            "title": r["title"],
            "summary": r.get("summary", ""),
            "url": r["url"],
            "source": r.get("source", "alpaca"),
            "ticker": r["ticker"],
            "category": r.get("category", "general"),
            "sentiment_label": s["label"],
            "sentiment_score": s["score"],
        })

    total = save_to_silver(rows)
    log.info(f"Total guardadas: {total}")
    return total
