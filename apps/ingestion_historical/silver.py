"""
silver.py — ingestion_historical
─────────────────────────────────
Pipeline RAW → SILVER para datos históricos.

Genera silver_features_{1m,5m,15m} con indicadores técnicos
calculados con shared.indicators (fuente canónica compartida con live).

Indicadores: EMA 9/12/21/50, RSI 14 (Wilder), MACD (12,26,9),
             Bollinger (20,2), VWAP (reset diario), ATR 14 (Wilder),
             Log returns, sentiment por ventana 15min.

Uso:
    from apps.ingestion_historical.silver import run_silver
    run_silver(["AAPL"], intervals=["1m"])
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from shared.config import cfg
from shared.db import sb
from shared.indicators import (
    atr,
    bollinger,
    ema,
    enrich_sentiment,
    is_market_open,
    log_returns,
    macd,
    rsi,
    vwap,
)

log = logging.getLogger(__name__)

RAW_TABLES = {"1m": "raw_ohlcv_1m", "5m": "raw_ohlcv_5m", "15m": "raw_ohlcv_15m"}
SILVER_TABLES = {"1m": "silver_features_1m", "5m": "silver_features_5m", "15m": "silver_features_15m"}

WARMUP_DAYS = 2
USEFUL_DAYS = 5


# ── Carga RAW ─────────────────────────────────────────────────────────────────

def load_raw(ticker: str, interval: str) -> pd.DataFrame:
    """Carga 7 días de RAW para un ticker e intervalo."""
    table = RAW_TABLES[interval]
    since = (datetime.now(tz=UTC) - timedelta(days=WARMUP_DAYS + USEFUL_DAYS)).isoformat()

    all_rows: list[dict] = []
    offset = 0
    while True:
        resp = (
            sb.table(table)
            .select("ts,open,high,low,close,volume")
            .eq("ticker", ticker)
            .gte("ts", since)
            .order("ts")
            .range(offset, offset + 999)
            .execute()
        )
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df


# ── Indicadores (via shared.indicators — fuente canónica) ─────────────────────

def calc_features(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Calcula indicadores técnicos usando shared.indicators."""
    out = df.copy()
    close = out["close"]

    # EMAs
    out["ema_9"] = ema(close, 9)
    out["ema_12"] = ema(close, 12)
    out["ema_21"] = ema(close, 21)
    out["ema_50"] = ema(close, 50)

    # RSI Wilder
    out["rsi_14"] = rsi(close, 14)

    # MACD
    out["macd_line"], out["macd_signal"], out["macd_hist"] = macd(close)

    # Bollinger
    out["bb_upper"], out["bb_middle"], out["bb_lower"], out["bb_width"], out["bb_pct"] = (
        bollinger(close, 20)
    )

    # VWAP con reset diario
    # shared.indicators.vwap espera columna "ts" o índice datetime
    df_for_vwap = out[["high", "low", "close", "volume"]].copy()
    df_for_vwap["ts"] = df_for_vwap.index
    out["vwap"] = vwap(df_for_vwap).values

    # ATR Wilder
    out["atr_14"] = atr(out, 14)

    # Log returns (canónico)
    out["returns"] = log_returns(close, 1)
    out["returns_5"] = log_returns(close, 5)
    out["returns_15"] = log_returns(close, 15)
    out["range_pct"] = (out["high"] - out["low"]) / close.replace(0, np.nan)

    # Volume norm
    vol_ma = out["volume"].rolling(20).mean().replace(0, np.nan)
    out["volume_norm"] = out["volume"] / vol_ma

    # Time features
    out["hour"] = out.index.hour
    out["dayofweek"] = out.index.dayofweek

    # Market open (F-76: DST, F-77: festivos via exchange_calendars)
    out["is_market_open"] = is_market_open(pd.Series(out.index, index=out.index))

    # I-01: category del ticker (antes nunca se escribía)
    from shared.symbols import SYMBOL_CATEGORY
    out["category"] = SYMBOL_CATEGORY.get(ticker, "unknown")

    # Sentiment (por defecto None, se enriquece después)
    out["sentiment_label"] = None
    out["sentiment_score"] = None
    # N-05: calcular sentiment_label_encoded (paridad con silver_rt)
    out["sentiment_label_encoded"] = 0

    # D-08/N-22: news_count features (antes solo en schema, nunca calculados)
    out["news_count_1h"] = 0
    out["news_count_24h"] = 0
    out["has_news"] = 0

    return out


# ── Enriquecimiento con sentiment ─────────────────────────────────────────────


def _compute_news_counts(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """D-08/N-22: Calcula news_count_1h, news_count_24h, has_news por barra."""
    try:
        ts_min = df.index.min() - pd.Timedelta(hours=24)
        ts_max = df.index.max()
        resp = (
            sb.table("silver_news_alpaca")
            .select("published_at")
            .eq("ticker", ticker)
            .gte("published_at", ts_min.isoformat())
            .lte("published_at", ts_max.isoformat())
            .order("published_at")
            .execute()
        )
        news_data = resp.data or []
    except Exception:
        return df

    if not news_data:
        return df

    news_ts = pd.to_datetime(
        [n["published_at"] for n in news_data], utc=True
    ).sort_values()

    counts_1h = []
    counts_24h = []
    for ts in df.index:
        c1 = ((news_ts >= ts - pd.Timedelta(hours=1)) & (news_ts <= ts)).sum()
        c24 = ((news_ts >= ts - pd.Timedelta(hours=24)) & (news_ts <= ts)).sum()
        counts_1h.append(int(c1))
        counts_24h.append(int(c24))

    df["news_count_1h"] = counts_1h
    df["news_count_24h"] = counts_24h
    df["has_news"] = (df["news_count_1h"] > 0).astype(int)
    return df


# ── Guardado en silver ────────────────────────────────────────────────────────

def save_silver(df: pd.DataFrame, ticker: str, interval: str) -> int:
    """Guarda el DataFrame en la tabla silver correspondiente."""
    if df.empty:
        return 0

    table = SILVER_TABLES[interval]

    cols = [
        "category",
        "open", "high", "low", "close", "volume",
        "ema_9", "ema_12", "ema_21", "ema_50",
        "rsi_14", "macd_line", "macd_signal", "macd_hist",
        "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pct",
        "vwap", "atr_14",
        "returns", "returns_5", "returns_15", "range_pct", "volume_norm",
        "hour", "dayofweek", "is_market_open",
        "sentiment_label", "sentiment_score", "sentiment_label_encoded",
        "news_count_1h", "news_count_24h", "has_news",
    ]

    rows = []
    for ts, row in df.iterrows():
        r = {"ts": ts.isoformat(), "ticker": ticker}
        for c in cols:
            val = row.get(c)
            if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
                val = None
            r[c] = val
        rows.append(r)

    inserted = 0
    batch_size = cfg.batch_insert

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            sb.table(table).upsert(batch, on_conflict="ticker,ts").execute()
            inserted += len(batch)
        except Exception as e:
            log.error(f"  {ticker} [{interval}] error guardando batch: {e}")

    return inserted


# ── Orquestador ───────────────────────────────────────────────────────────────

def run_silver(
    tickers: list[str],
    intervals: list[str] | None = None,
    enrich_news: bool = True,
) -> dict:
    """Pipeline RAW → SILVER para los tickers e intervalos dados."""
    intervals = intervals or ["1m", "5m", "15m"]
    results: dict[str, dict] = {}
    cutoff = datetime.now(tz=UTC) - timedelta(days=USEFUL_DAYS)

    for idx, ticker in enumerate(tickers, 1):
        log.info(f"[{idx}/{len(tickers)}] {ticker}")
        results[ticker] = {}

        for interval in intervals:
            log.info(f"  [{interval}] Cargando RAW...")
            df = load_raw(ticker, interval)

            if df.empty:
                log.warning(f"  [{interval}] Sin datos RAW para {ticker}")
                results[ticker][interval] = 0
                continue

            log.info(f"  [{interval}] {len(df)} velas → calculando indicadores...")
            df = calc_features(df, ticker)

            if enrich_news:
                log.info(f"  [{interval}] Enriqueciendo con sentiment...")
                df = enrich_sentiment(df, ticker)
                # N-05: calcular sentiment_label_encoded
                label_map = {"positive": 1, "neutral": 0, "negative": -1}
                df["sentiment_label_encoded"] = (
                    df["sentiment_label"].map(label_map).fillna(0).astype(int)
                )
                # D-08/N-22: calcular news_count_1h, news_count_24h, has_news
                df = _compute_news_counts(df, ticker)

            # Solo guardar los USEFUL_DAYS más recientes (descartar warm-up)
            df = df[df.index >= cutoff]

            log.info(f"  [{interval}] Guardando {len(df)} velas en silver...")
            saved = save_silver(df, ticker, interval)
            results[ticker][interval] = saved
            log.info(f"  [{interval}] {saved} filas guardadas")

    total = sum(v for r in results.values() for v in r.values())
    log.info(f"Total filas silver guardadas: {total:,}")
    return results
