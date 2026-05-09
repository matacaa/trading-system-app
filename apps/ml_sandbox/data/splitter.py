"""
splitter.py
───────────
Divide el DataFrame en train y test según las fechas del yaml.
Genera X_train, X_test, y_train, y_test listos para ML.

Para clasificación convierte el target en binario: 1 si sube, 0 si baja.
Para regresión deja el target como valor continuo.

Devuelve también scaler_params para reproducir la normalización en producción.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from shared.db import sb
from apps.ml_sandbox.config import ExperimentConfig

log = logging.getLogger(__name__)


def split_data(
    df: pd.DataFrame,
    cfg: ExperimentConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str], dict | None]:
    """
    Divide el DataFrame en train y test.

    Returns:
        X_train, X_test, y_train, y_test, feature_names, scaler_params
    """
    train_mask = (
        (df["ts"] >= pd.Timestamp(cfg.data.train_start, tz="UTC"))
        & (df["ts"] < pd.Timestamp(cfg.data.test_start, tz="UTC"))
    )
    test_mask = (
        (df["ts"] >= pd.Timestamp(cfg.data.test_start, tz="UTC"))
        & (df["ts"] < pd.Timestamp(cfg.data.test_end, tz="UTC") + pd.Timedelta(days=1))
    )

    train_df = df[train_mask].copy()
    test_df = df[test_mask].copy()

    if train_df.empty:
        raise ValueError(
            f"No hay datos de train entre {cfg.data.train_start} y {cfg.data.test_start}"
        )
    if test_df.empty:
        raise ValueError(
            f"No hay datos de test entre {cfg.data.test_start} y {cfg.data.test_end}"
        )

    log.info(f"Train: {len(train_df)} filas ({cfg.data.train_start} -> {cfg.data.test_start})")
    log.info(f"Test:  {len(test_df)} filas ({cfg.data.test_start} -> {cfg.data.test_end})")

    # Features — usar columns del yaml si están especificadas
    if cfg.data.columns:
        feature_cols = list(cfg.data.columns)
    else:
        exclude = {"ts", "ticker", cfg.data.target}
        feature_cols = [c for c in df.columns if c not in exclude]

    # Auto-incluir columnas de context_tickers (prefijadas con {ticker}_)
    context_tickers = getattr(cfg.data, "context_tickers", [])
    if context_tickers:
        ctx_cols = [
            c for c in df.columns
            if any(c.startswith(f"{t}_") for t in context_tickers)
            and c not in feature_cols
        ]
        if ctx_cols:
            feature_cols.extend(ctx_cols)
            log.info(f"Context features añadidas: {len(ctx_cols)} columnas de {context_tickers}")

    # N-19: detectar data leak (target en features)
    if cfg.data.target in feature_cols:
        log.warning(
            f"⚠️  DATA LEAK DETECTADO: '{cfg.data.target}' está en las features "
            f"Y es el target. Eliminándolo de features para evitar leak."
        )
        feature_cols = [c for c in feature_cols if c != cfg.data.target]

    # N-20: advertir si no hay gap entre train y test
    train_end_ts = pd.Timestamp(cfg.data.train_end, tz="UTC") if cfg.data.train_end else None
    test_start_ts = pd.Timestamp(cfg.data.test_start, tz="UTC")
    if train_end_ts and (test_start_ts - train_end_ts) < pd.Timedelta(days=1):
        log.warning(
            f"Sin gap entre train_end ({cfg.data.train_end}) y test_start ({cfg.data.test_start}). "
            f"Posible leak de 1 barra en el target."
        )

    X_train = train_df[feature_cols].values.astype(np.float32)
    X_test = test_df[feature_cols].values.astype(np.float32)

    # Target — si cargamos desde silver, target ya está en el df
    if cfg.is_pytorch and cfg.data.source != "silver":
        table = cfg.data.tables[0] if cfg.data.tables else "silver_features_1m"
        # F-100: cargar target para TODOS los tickers, no solo el primero
        all_target_dfs = []
        for ticker in cfg.data.tickers:
            resp = (
                sb.table(table)
                .select(f"ts,ticker,{cfg.data.target}")
                .eq("ticker", ticker)
                .gte("ts", cfg.data.train_start)
                .lte("ts", cfg.data.test_end)
                .order("ts")
                .execute()
            )
            if resp.data:
                all_target_dfs.append(pd.DataFrame(resp.data))

        if not all_target_dfs:
            raise ValueError(f"No se encontraron targets para {cfg.data.tickers}")

        target_df = pd.concat(all_target_dfs)
        target_df["ts"] = pd.to_datetime(target_df["ts"], utc=True)
        train_target = target_df[target_df["ts"].isin(train_df["ts"])]
        test_target = target_df[target_df["ts"].isin(test_df["ts"])]
        y_train_raw = train_target[cfg.data.target].values
        y_test_raw = test_target[cfg.data.target].values
    else:
        y_train_raw = train_df[cfg.data.target].values
        y_test_raw = test_df[cfg.data.target].values

    if cfg.experiment.task == "classification":
        # F-107: target_threshold define el umbral para convertir el target continuo
        # en binario. Si target='returns' y threshold=0, entonces:
        #   returns > 0 → clase 1 (sube)
        #   returns <= 0 → clase 0 (baja)
        y_train = (y_train_raw > cfg.data.target_threshold).astype(np.int32)
        y_test = (y_test_raw > cfg.data.target_threshold).astype(np.int32)
        log.info(f"Train — sube: {y_train.sum()} / baja: {(y_train == 0).sum()}")
        log.info(f"Test  — sube: {y_test.sum()}  / baja: {(y_test == 0).sum()}")
    else:
        y_train = y_train_raw.astype(np.float32)
        y_test = y_test_raw.astype(np.float32)

    # Normalización
    scaler_params = None
    if cfg.data.normalize:
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test = scaler.transform(X_test)
        scaler_params = {
            "mean": scaler.mean_.tolist(),
            "std": scaler.scale_.tolist(),
        }
        log.info(f"Features normalizadas — scaler_params para {len(feature_cols)} features")

    log.info(f"X_train shape: {X_train.shape}")
    log.info(f"X_test shape:  {X_test.shape}")

    return X_train, X_test, y_train, y_test, feature_cols, scaler_params
