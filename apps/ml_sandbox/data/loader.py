"""
loader.py
─────────
Carga datos para entrenamiento y test según la configuración del yaml.

Si el modelo es sklearn → carga desde silver_features (Supabase)
Si el modelo es pytorch → carga desde tensores locales (.npy)

Cambios: usa shared.db.sb (singleton) en vez de create_client.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from apps.ml_sandbox.config import ExperimentConfig
from shared.db import sb

log = logging.getLogger(__name__)


def load_data(cfg: ExperimentConfig) -> pd.DataFrame:
    """Carga datos según el tipo de modelo y data.source del yaml."""
    use_silver = cfg.data.source == "silver" or cfg.is_sklearn
    if not use_silver and cfg.is_pytorch:
        # Auto: intentar tensores, fallback a silver
        tensor_path = cfg.tensors_dir / cfg.data.tensor_interval / f"tensor_{cfg.data.tensor_type}.npy"
        use_silver = not tensor_path.exists()
        if use_silver:
            log.info("Tensores no encontrados, cargando desde silver tables")

    if use_silver:
        return _load_from_silver(cfg)
    else:
        return _load_from_tensor(cfg)


def _load_from_silver(cfg: ExperimentConfig) -> pd.DataFrame:
    """Carga datos desde silver_features en Supabase.

    Si cfg.data.context_tickers está definido, carga también las features
    de esos tickers y las une por timestamp con prefijo {ticker}_.
    El modelo puede así usar contexto de mercado (ej: GLD_rsi_14, MSFT_returns_5).
    """
    all_dfs = []

    select_cols = ["ts", "ticker"] + cfg.data.columns + [cfg.data.target]
    select_cols = list(dict.fromkeys(select_cols))

    for table in cfg.data.tables:
        log.info(f"Cargando {table}...")
        for ticker in cfg.data.tickers:
            rows: list[dict] = []
            offset = 0

            while True:
                try:
                    resp = (
                        sb.table(table)
                        .select(",".join(select_cols))
                        .eq("ticker", ticker)
                        .gte("ts", cfg.data.train_start)
                        .lte("ts", cfg.data.test_end)
                        .order("ts")
                        .range(offset, offset + 999)
                        .execute()
                    )
                    batch = resp.data or []
                    rows.extend(batch)
                    if len(batch) < 1000:
                        break
                    offset += 1000
                except Exception as e:
                    log.error(f"Error cargando {ticker} de {table}: {e}")
                    break

            if rows:
                df = pd.DataFrame(rows)
                df["ts"] = pd.to_datetime(df["ts"], utc=True)
                all_dfs.append(df)
                log.info(f"  {ticker}: {len(df)} filas")

    if not all_dfs:
        raise ValueError("No se encontraron datos en Supabase para los parámetros dados")

    result = pd.concat(all_dfs).sort_values(["ts", "ticker"])

    # ── Context tickers: cargar features de otros tickers como columnas extra ──
    context_tickers = getattr(cfg.data, "context_tickers", [])
    if context_tickers:
        log.info(f"Cargando context_tickers: {context_tickers}")
        # Solo columnas de features (sin target ni ts/ticker)
        ctx_cols = [c for c in cfg.data.columns if c != cfg.data.target]
        ctx_select = ["ts", "ticker"] + ctx_cols
        ctx_select = list(dict.fromkeys(ctx_select))

        for table in cfg.data.tables:
            for ctx_ticker in context_tickers:
                rows: list[dict] = []
                offset = 0
                while True:
                    try:
                        resp = (
                            sb.table(table)
                            .select(",".join(ctx_select))
                            .eq("ticker", ctx_ticker)
                            .gte("ts", cfg.data.train_start)
                            .lte("ts", cfg.data.test_end)
                            .order("ts")
                            .range(offset, offset + 999)
                            .execute()
                        )
                        batch = resp.data or []
                        rows.extend(batch)
                        if len(batch) < 1000:
                            break
                        offset += 1000
                    except Exception as e:
                        log.error(f"Error cargando context {ctx_ticker}: {e}")
                        break

                if not rows:
                    log.warning(f"  context {ctx_ticker}: sin datos — omitiendo")
                    continue

                ctx_df = pd.DataFrame(rows)
                ctx_df["ts"] = pd.to_datetime(ctx_df["ts"], utc=True)
                log.info(f"  context {ctx_ticker}: {len(ctx_df)} filas")

                # Renombrar columnas con prefijo {ticker}_
                rename_map = {
                    c: f"{ctx_ticker}_{c}"
                    for c in ctx_cols
                    if c in ctx_df.columns
                }
                ctx_df = ctx_df.rename(columns=rename_map)
                ctx_df = ctx_df.drop(columns=["ticker"], errors="ignore")

                # Merge por timestamp
                result = result.merge(ctx_df, on="ts", how="left")
                log.info(f"  → {len(rename_map)} features añadidas con prefijo {ctx_ticker}_")

    if cfg.data.dropna:
        before = len(result)
        # Solo dropna en columnas principales (no context, que pueden tener gaps)
        main_cols = cfg.data.columns + [cfg.data.target]
        existing = [c for c in main_cols if c in result.columns]
        result = result.dropna(subset=existing)
        log.info(f"Filas eliminadas por NaN: {before - len(result)}")

    # Rellenar NaN de context tickers con 0 (gaps de mercado entre tickers)
    if context_tickers:
        ctx_feature_cols = [c for c in result.columns if any(c.startswith(f"{t}_") for t in context_tickers)]
        result[ctx_feature_cols] = result[ctx_feature_cols].fillna(0)
        log.info(f"Context features ({len(ctx_feature_cols)} cols) — NaN rellenados con 0")

    log.info(f"Total filas cargadas: {len(result)} — {len(result.columns)} columnas")
    return result


def _load_from_tensor(cfg: ExperimentConfig) -> pd.DataFrame:
    """Carga datos desde tensores locales .npy."""
    tensor_path = (
        cfg.tensors_dir / cfg.data.tensor_interval
        / f"tensor_{cfg.data.tensor_type}.npy"
    )
    meta_path = (
        cfg.tensors_dir / cfg.data.tensor_interval
        / f"tensor_{cfg.data.tensor_type}_meta.npz"
    )

    if not tensor_path.exists():
        raise FileNotFoundError(f"Tensor no encontrado: {tensor_path}")

    log.info(f"Cargando tensor: {tensor_path}")
    tensor = np.load(tensor_path)
    meta = np.load(meta_path, allow_pickle=True)

    timestamps = pd.to_datetime(meta["timestamps"])
    tickers = list(meta["tickers"])
    column_names = (
        [str(c) for c in meta["columns"]]
        if "columns" in meta
        else [f"feature_{i}" for i in range(tensor.shape[2])]
    )

    ticker_indices = [tickers.index(t) for t in cfg.data.tickers if t in tickers]
    if not ticker_indices:
        raise ValueError(
            f"Ningún ticker del yaml encontrado en el tensor: {cfg.data.tickers}"
        )

    ts_mask = (
        (timestamps >= pd.Timestamp(cfg.data.train_start, tz="UTC"))
        & (timestamps <= pd.Timestamp(cfg.data.test_end, tz="UTC"))
    )
    tensor_filtered = tensor[ts_mask]
    ts_filtered = timestamps[ts_mask]

    # F-101: vectorizado con numpy en vez de triple loop Python
    rows = []
    for t_idx, ticker in zip(ticker_indices, cfg.data.tickers, strict=False):
        ticker_data = tensor_filtered[:, t_idx, :]  # (n_timestamps, n_features)
        ticker_df = pd.DataFrame(ticker_data, columns=column_names)
        ticker_df["ts"] = ts_filtered
        ticker_df["ticker"] = ticker
        rows.append(ticker_df)

    result = pd.concat(rows, ignore_index=True)
    log.info(f"Tensor cargado: {result.shape} — columnas: {column_names[:5]}...")
    return result
