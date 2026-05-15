"""
evaluate.py
───────────
Evalúa el modelo entrenado sobre el conjunto de test.
Calcula métricas, genera predicciones con intervalos de
confianza y guarda los resultados en Supabase.

Uso:
    from apps.ml_sandbox.evaluate import run_evaluate
    run_evaluate(cfg, model, X_test, y_test, df_test)
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from apps.ml_sandbox.config import ExperimentConfig
from shared.db import sb
from shared.models.base import BaseModel

log = logging.getLogger(__name__)


def calc_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: np.ndarray,
    task: str,
    metric_names: list[str],
) -> dict[str, float]:
    """Calcula las métricas configuradas en el yaml."""
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        mean_absolute_error,
        mean_squared_error,
        precision_score,
        r2_score,
        recall_score,
        roc_auc_score,
    )

    metrics = {}

    if task == "classification":
        if "accuracy" in metric_names:
            metrics["accuracy"] = float(accuracy_score(y_true, y_pred))
        if "f1" in metric_names:
            metrics["f1"] = float(f1_score(y_true, y_pred, zero_division=0))
        if "precision" in metric_names:
            metrics["precision"] = float(precision_score(y_true, y_pred, zero_division=0))
        if "recall" in metric_names:
            metrics["recall"] = float(recall_score(y_true, y_pred, zero_division=0))
        if "roc_auc" in metric_names:
            try:
                metrics["roc_auc"] = float(roc_auc_score(y_true, y_prob))
            except Exception:
                metrics["roc_auc"] = 0.0
    else:
        if "rmse" in metric_names:
            metrics["rmse"] = float(np.sqrt(mean_squared_error(y_true, y_pred)))
        if "mae" in metric_names:
            metrics["mae"] = float(mean_absolute_error(y_true, y_pred))
        if "r2" in metric_names:
            metrics["r2"] = float(r2_score(y_true, y_pred))

    return metrics


def save_predictions(
    cfg: ExperimentConfig,
    df_test: pd.DataFrame,
    y_pred: np.ndarray,
    y_prob: np.ndarray,
    conf_low: np.ndarray,
    conf_high: np.ndarray,
) -> int:
    """Guarda predicciones en silver_predictions."""
    rows = []

    ts_values = df_test["ts"].values if "ts" in df_test.columns else df_test.index
    tickers = (
        df_test["ticker"].values
        if "ticker" in df_test.columns
        else ["unknown"] * len(df_test)
    )

    n = min(len(y_pred), len(ts_values))
    for i in range(n):
        rows.append({
            "experiment_name": cfg.experiment.name,
            "model_name": cfg.model.name,
            "ticker": str(tickers[i]),
            "ts": pd.Timestamp(ts_values[i]).isoformat(),
            "y_true": (
                float(df_test[cfg.data.target].values[i])
                if cfg.data.target in df_test.columns
                    and df_test[cfg.data.target].values[i] is not None
                    and not (isinstance(df_test[cfg.data.target].values[i], float)
                             and np.isnan(df_test[cfg.data.target].values[i]))
                else None
            ),
            "y_pred": float(y_pred[i]),
            "y_prob": float(y_prob[i]),
            "confidence_low": float(conf_low[i]),
            "confidence_high": float(conf_high[i]),
        })

    if not rows:
        return 0

    inserted = 0
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            sb.table("silver_predictions").upsert(
                batch, on_conflict="experiment_name,ticker,ts"
            ).execute()
            inserted += len(batch)
        except Exception as e:
            log.error(f"Error guardando predicciones batch {i}: {e}")

    log.info(f"Predicciones guardadas: {inserted}")
    return inserted


def save_metrics(
    cfg: ExperimentConfig,
    metrics: dict[str, float],
    ticker: str = "all",
) -> None:
    """Guarda métricas en silver_metrics."""
    rows = [
        {
            "experiment_name": cfg.experiment.name,
            "model_name": cfg.model.name,
            "ticker": ticker,
            "metric_name": name,
            "metric_value": value,
        }
        for name, value in metrics.items()
    ]
    try:
        # F-60: on_conflict incluye model_name para evitar sobrescrituras incorrectas
        sb.table("silver_metrics").upsert(
            rows, on_conflict="experiment_name,ticker,metric_name"
        ).execute()
        log.info(f"Métricas guardadas: {list(metrics.keys())}")
    except Exception as e:
        log.error(f"Error guardando métricas: {e}")


def run_evaluate(
    cfg: ExperimentConfig,
    model: BaseModel,
    X_test: np.ndarray,
    y_test: np.ndarray,
    df_test: pd.DataFrame,
) -> dict[str, float]:
    """
    Evalúa el modelo y guarda resultados en Supabase.

    Returns:
        dict con las métricas calculadas
    """
    log.info(f"Evaluando {cfg.experiment.name}...")
    log.info(f"X_test: {X_test.shape}")

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)

    log.info("Calculando intervalos de confianza...")
    conf_low, conf_high = model.confidence_interval(X_test)

    # Ajustar longitud si PyTorch recorta por sequence_length (F-61)
    n = min(len(y_pred), len(y_test), len(df_test))
    if n < len(y_pred):
        log.info(f"  Ajustando longitud: {len(y_pred)} → {n} (por sequence_length)")
    y_pred = y_pred[-n:]
    y_prob = y_prob[-n:]
    y_test_n = y_test[-n:]
    conf_low = conf_low[-n:]
    conf_high = conf_high[-n:]
    df_test_n = df_test.iloc[-n:].reset_index(drop=True)

    # Métricas
    metrics = calc_metrics(
        y_test_n, y_pred, y_prob,
        cfg.experiment.task,
        cfg.output.metrics,
    )

    log.info("Métricas:")
    for name, value in metrics.items():
        log.info(f"  {name}: {value:.4f}")

    # Guardar en Supabase
    if cfg.output.save_predictions:
        save_predictions(cfg, df_test_n, y_pred, y_prob, conf_low, conf_high)

    if cfg.output.save_metrics:
        save_metrics(cfg, metrics)

    # F-57: merge con metrics_summary existente (no sobrescribir training_duration_s)
    try:
        existing_resp = (
            sb.table("silver_model_registry")
            .select("metrics_summary")
            .eq("experiment_name", cfg.experiment.name)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        existing_metrics = {}
        if existing_resp.data and existing_resp.data[0].get("metrics_summary"):
            existing_metrics = json.loads(existing_resp.data[0]["metrics_summary"])

        merged_metrics = {**existing_metrics, **metrics}

        sb.table("silver_model_registry").update(
            {"metrics_summary": json.dumps(merged_metrics), "status": "complete"}
        ).eq("experiment_name", cfg.experiment.name).eq("is_active", True).execute()
        log.info("  Registry actualizado: status=complete, metrics guardadas")
    except Exception as e:
        log.warning(f"No se pudo actualizar metrics_summary/status: {e}")

    return metrics
