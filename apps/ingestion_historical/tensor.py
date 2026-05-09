"""
tensor.py
─────────
Genera tensores 3D desde las tablas silver de Supabase
y los guarda como ficheros .npy.

Shape: (n_timestamps, n_tickers, n_features)

Tensores por granularidad (1m, 5m, 15m):
    tensor_ohlcv.npy     — solo OHLCV normalizado
    tensor_features.npy  — indicadores técnicos
    tensor_full.npy      — OHLCV + indicadores

Uso:
    from apps.ingestion_historical.tensor import run_tensor
    run_tensor(intervals=["1m"])
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from shared.config import cfg
from shared.db import sb
from shared.symbols import ALL_SYMBOLS

log = logging.getLogger(__name__)

SILVER_TABLES = {"1m": "silver_features_1m", "5m": "silver_features_5m", "15m": "silver_features_15m"}

SENTIMENT_MAP = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

COLS_OHLCV = ["open", "high", "low", "close", "volume"]

COLS_FEATURES = [
    "ema_9", "ema_12", "ema_21", "ema_50", "rsi_14",
    "macd_line", "macd_signal", "macd_hist",
    "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pct",
    "vwap", "atr_14",
    "returns", "returns_5", "returns_15", "range_pct", "volume_norm",
    "hour", "dayofweek", "is_market_open",
    "sentiment_label_encoded", "sentiment_score",
]

COLS_FULL = COLS_OHLCV + COLS_FEATURES


def load_silver(interval: str) -> pd.DataFrame:
    """Carga datos silver ticker a ticker."""
    table = SILVER_TABLES[interval]
    tickers = list(ALL_SYMBOLS.keys())
    all_dfs = []

    for i, ticker in enumerate(tickers, 1):
        log.info(f"  [{i}/{len(tickers)}] Cargando {ticker}...")
        rows: list[dict] = []
        offset = 0

        while True:
            try:
                resp = (
                    sb.table(table).select("*")
                    .eq("ticker", ticker).order("ts")
                    .range(offset, offset + 999).execute()
                )
                batch = resp.data or []
                rows.extend(batch)
                if len(batch) < 1000:
                    break
                offset += 1000
            except Exception as e:
                log.error(f"  Error cargando {ticker}: {e}")
                break

        if rows:
            df = pd.DataFrame(rows)
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame()

    result = pd.concat(all_dfs).sort_values(["ts", "ticker"])
    result["sentiment_label_encoded"] = result["sentiment_label"].map(SENTIMENT_MAP)

    log.info(f"  Total: {len(result):,} filas — {result['ticker'].nunique()} tickers")
    return result


def build_tensor(df: pd.DataFrame, columns: list[str]) -> tuple[np.ndarray, list, list]:
    """Construye tensor 3D (timestamps × tickers × features)."""
    timestamps = sorted(df["ts"].unique())
    tickers = sorted(df["ticker"].unique())
    n_ts, n_tkr, n_feat = len(timestamps), len(tickers), len(columns)

    log.info(f"  Shape: ({n_ts}, {n_tkr}, {n_feat})")

    ts_idx = {ts: i for i, ts in enumerate(timestamps)}
    tkr_idx = {t: i for i, t in enumerate(tickers)}
    tensor = np.full((n_ts, n_tkr, n_feat), np.nan, dtype=np.float32)

    for _, row in df.iterrows():
        i, j = ts_idx[row["ts"]], tkr_idx[row["ticker"]]
        for k, col in enumerate(columns):
            val = row.get(col)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                tensor[i, j, k] = float(val)

    return tensor, timestamps, tickers


def normalize_tensor(tensor: np.ndarray) -> np.ndarray:
    """Z-score por feature. NaN se mantienen."""
    normalized = tensor.copy()
    for k in range(tensor.shape[2]):
        feature = tensor[:, :, k]
        mean, std = np.nanmean(feature), np.nanstd(feature)
        if std > 0:
            normalized[:, :, k] = (feature - mean) / std
    return normalized


def save_tensor(
    tensor: np.ndarray, timestamps: list, tickers: list,
    interval: str, tensor_type: str, columns: list,
):
    """Guarda tensor y metadatos en disco."""
    folder = cfg.tensors_dir / interval
    folder.mkdir(parents=True, exist_ok=True)

    tensor_path = folder / f"tensor_{tensor_type}.npy"
    np.save(tensor_path, tensor)

    meta_path = folder / f"tensor_{tensor_type}_meta.npz"
    np.savez(
        meta_path,
        timestamps=np.array([str(ts) for ts in timestamps]),
        tickers=np.array(tickers),
        columns=np.array(columns),
    )

    size_mb = tensor_path.stat().st_size / 1e6
    log.info(f"  Guardado: {tensor_path} ({tensor.shape}, {size_mb:.1f} MB)")


def run_tensor(intervals: list[str] | None = None, normalize: bool = True) -> dict:
    """Pipeline SILVER → TENSOR para todos los intervalos."""
    intervals = intervals or ["1m", "5m", "15m"]
    results: dict = {}

    for interval in intervals:
        log.info(f"Generando tensores [{interval}]...")
        df = load_silver(interval)
        if df.empty:
            log.warning(f"Sin datos silver para {interval}")
            continue

        results[interval] = {}

        for tensor_type, columns in [("ohlcv", COLS_OHLCV), ("features", COLS_FEATURES), ("full", COLS_FULL)]:
            available = [c for c in columns if c in df.columns]
            if not available:
                continue

            tensor, timestamps, tickers = build_tensor(df, available)
            if normalize:
                tensor = normalize_tensor(tensor)

            save_tensor(tensor, timestamps, tickers, interval, tensor_type, available)
            results[interval][tensor_type] = {"shape": tensor.shape}

    return results
