"""
ingestion.py
────────────
Descarga OHLCV de yfinance y escribe en Supabase (raw_ohlcv_*).

Uso:
    from apps.ingestion_historical.ingestion import run_update
    run_update(["AAPL"], intervals=["1m", "5m", "15m"])
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from shared.config import cfg
from shared.db import sb
from shared.symbols import ALL_SYMBOLS
from shared.utils.time import utc_isoformat
from apps.ingestion_historical.downloader import get_date_blocks, download_block

log = logging.getLogger(__name__)

RAW_TABLES = {"1m": "raw_ohlcv_1m", "5m": "raw_ohlcv_5m", "15m": "raw_ohlcv_15m"}
INTERVALS = ["1m", "5m", "15m"]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_symbol_id(ticker: str) -> int | None:
    """Busca el ID del ticker en la tabla symbols."""
    try:
        resp = sb.table("symbols").select("id").eq("ticker", ticker).single().execute()
        return resp.data["id"] if resp.data else None
    except Exception:
        return None


def _get_last_ts(ticker: str, interval: str) -> datetime | None:
    """Obtiene el último timestamp para un ticker/intervalo."""
    table = RAW_TABLES[interval]
    try:
        resp = (
            sb.table(table).select("ts")
            .eq("ticker", ticker).order("ts", desc=True).limit(1).execute()
        )
        if resp.data:
            return pd.to_datetime(resp.data[0]["ts"], utc=True)
    except Exception:
        pass
    return None


def _upsert_ohlcv(df: pd.DataFrame, symbol_id: int, interval: str) -> tuple[int, int]:
    """Escribe OHLCV en Supabase. Retorna (inserted, skipped)."""
    if df.empty:
        return 0, 0

    table = RAW_TABLES[interval]
    rows = []
    for _, row in df.iterrows():
        rows.append({
            "ts": row["ts"].isoformat(),
            "ticker": row["ticker"],
            "symbol_id": symbol_id,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
        })

    inserted = 0
    batch_size = cfg.batch_insert
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            sb.table(table).upsert(batch, on_conflict="ticker,ts").execute()
            inserted += len(batch)
        except Exception as e:
            log.error(f"  Error upsert batch: {e}")

    return inserted, len(rows) - inserted


def _log_ingestion(
    ticker: str, interval: str, start: datetime, end: datetime,
    inserted: int, skipped: int, status: str, error: str | None, duration_s: float,
) -> None:
    """Registra la ingesta en la tabla de logs."""
    try:
        # N-07: nombre de tabla alineado con schema Supabase
        sb.table("ingestion_log").insert({
            "run_at": utc_isoformat(),
            "ticker": ticker,
            "interval": interval,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "inserted": inserted,
            "skipped": skipped,
            "status": status,
            "error": error,
            "duration_s": round(duration_s, 2),
        }).execute()
    except Exception as e:
        log.warning(
            f"  Error logging ingestion: {e}. "
            f"Verifica que la tabla 'ingestion_log' existe en Supabase "
            f"(puede llamarse 'ingestion_logs' — ver scripts/schema_fixes.sql)."
        )


# ── Ingesta de un bloque ──────────────────────────────────────────────────────

def _ingest_block(
    ticker: str, symbol_id: int, interval: str,
    start: datetime, end: datetime,
) -> tuple[int, int, str]:
    """Descarga un bloque y lo sube a Supabase."""
    t0 = time.time()
    df = download_block(ticker, start, end, interval)

    if df.empty:
        _log_ingestion(ticker, interval, start, end, 0, 0, "empty", None, time.time() - t0)
        return 0, 0, "empty"

    try:
        inserted, skipped = _upsert_ohlcv(df, symbol_id, interval)
        status, error = "success", None
    except Exception as e:
        inserted, skipped = 0, len(df)
        status, error = "error", str(e)
        log.error(f"  {ticker} [{interval}]: error al subir bloque: {e}")

    _log_ingestion(ticker, interval, start, end, inserted, skipped, status, error, time.time() - t0)
    return inserted, skipped, status


# ── Actualización incremental ─────────────────────────────────────────────────

def run_update(
    tickers: list[str],
    intervals: list[str] | None = None,
) -> dict[str, int]:
    """Descarga solo datos nuevos desde la última fecha disponible."""
    intervals = intervals or INTERVALS
    results: dict[str, int] = {}
    now = datetime.now(tz=timezone.utc)

    for ticker in tickers:
        sym_id = _get_symbol_id(ticker)
        if sym_id is None:
            log.warning(f"{ticker}: no está en symbols, omitiendo")
            continue

        total_ins = 0
        for interval in intervals:
            last = _get_last_ts(ticker, interval)

            if last is None:
                log.info(f"  {ticker} [{interval}]: sin datos previos, descarga bulk 7 días")
                blocks = get_date_blocks(interval, days=7)
            else:
                start = (last + timedelta(minutes=1))
                if start >= now:
                    log.info(f"  {ticker} [{interval}]: actualizado (último: {last})")
                    continue
                blocks = [(start, now)]

            for blk_start, blk_end in blocks:
                ins, _, _ = _ingest_block(ticker, sym_id, interval, blk_start, blk_end)
                total_ins += ins
                time.sleep(0.3)

        results[ticker] = total_ins
        if total_ins:
            log.info(f"  {ticker}: +{total_ins} velas")

    total = sum(results.values())
    log.info(f"Actualización completada: +{total:,} velas")
    return results
