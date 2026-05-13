"""
inference.py
────────────
Lógica de predicción unificada — usada por backtest y por el live.

Unifica predict_row (backtest.py) y predict_ticker (predictor.py)
en una sola función predict_ensemble().

Cambios respecto a los originales:
    - F-64: código triplicado → una sola implementación
    - F-66: usa model.predict_proba() (API pública) en vez de model._net
    - F-65: seq_len se lee del modelo (model.seq_len) en vez de hardcoded=10
    - F-70: log warning cuando se rellenan features faltantes con 0
    - F-12: log warning cuando pesos se re-normalizan por modelos fallidos
    - F-73/F-74: sin sys.path hacks ni ml_sandbox_path
    - F-43: load_models usa shared.db.sb (singleton)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from shared.config import cfg as app_cfg
from shared.db import query
from shared.models.registry import load_model_from_path

log = logging.getLogger(__name__)

# Nombres de modelos pytorch (para decidir flujo secuencial vs tabular)
_PYTORCH_MODELS = {"lstm", "gru", "transformer"}


def load_models(modelos_cfg: list[dict]) -> list[dict]:
    """
    Carga los modelos activos desde silver_model_registry.

    Args:
        modelos_cfg: lista de dicts del yaml con experiment_name, activo, peso

    Returns:
        lista de dicts con modelo cargado, feature_columns, scaler_params, peso
    """
    modelos_activos = [m for m in modelos_cfg if m.get("activo", True)]
    modelos = []

    for m_cfg in modelos_activos:
        exp_name = m_cfg["experiment_name"]
        log.info(f"Cargando modelo: {exp_name}")

        try:
            rows = query(
                """SELECT model_name, file_path, feature_columns,
                          scaler_params, feature_source, timeframe, version
                   FROM silver_model_registry
                   WHERE experiment_name = %s AND is_active = true AND status = 'complete'
                   LIMIT 1""",
                [exp_name],
            )

            if not rows:
                log.warning(f"  {exp_name} no encontrado (o sin versión activa/complete) — omitiendo")
                continue

            meta = rows[0]
            model_name = meta["model_name"]
            feature_cols = json.loads(meta["feature_columns"])
            scaler_params = (
                json.loads(meta["scaler_params"]) if meta.get("scaler_params") else None
            )

            # ── Resolver file_path ──────────────────────────────────
            file_path = Path(meta["file_path"])

            # Si es un path absoluto Windows (A-02), buscar solo el filename en models_dir
            if not file_path.exists():
                alt_path = app_cfg.models_dir / file_path.name
                if alt_path.exists():
                    log.info(f"  A-02: path original no existe, usando {alt_path}")
                    file_path = alt_path
                else:
                    log.warning(
                        f"  Fichero no encontrado: {file_path} "
                        f"(ni en {app_cfg.models_dir}) — omitiendo"
                    )
                    continue

            # ── Cargar modelo con el registry (auto-descubre la clase) ──
            model = load_model_from_path(model_name, file_path)
            if model is None:
                continue

            modelos.append({
                "experiment_name": exp_name,
                "model": model,
                "peso": m_cfg["peso"],
                "feature_cols": feature_cols,
                "scaler_params": scaler_params,
                "feature_source": meta.get("feature_source", "silver"),
                "model_name": model_name,
            })
            log.info(f"  OK: {exp_name} v{meta.get('version', '?')} (peso: {m_cfg['peso']})")

        except Exception as e:
            log.error(f"  Error cargando {exp_name}: {e}")

    return modelos


def predict_ensemble(
    row: pd.Series,
    modelos: list[dict],
    df_hist: pd.DataFrame | None = None,
) -> tuple[float, dict, list[dict]]:
    """
    Genera predicción ponderada para una vela usando el ensemble.

    Unifica predict_row (backtest) y predict_ticker (predictor).

    Args:
        row:     última vela (pd.Series con features)
        modelos: lista de modelos cargados (de load_models)
        df_hist: historial de velas anteriores (necesario para modelos pytorch)

    Returns:
        (score_final, detalle_por_modelo, signals_para_supabase)
    """
    ts = row.get("ts", datetime.now(timezone.utc).isoformat())
    ticker = row.get("ticker", "")

    scores: list[tuple[float, float]] = []  # (score, peso)
    detalle: dict[str, float] = {}
    signals: list[dict] = []

    for m in modelos:
        try:
            y_prob = _predict_single(
                row=row,
                df_hist=df_hist,
                model=m["model"],
                model_name=m["model_name"],
                feature_cols=m["feature_cols"],
                scaler_params=m["scaler_params"],
                experiment_name=m["experiment_name"],
            )

            if y_prob is None:
                continue

            score = y_prob * 100
            scores.append((score, m["peso"]))
            detalle[m["experiment_name"]] = round(score, 2)

            signals.append({
                "ts": str(ts),
                "ticker": ticker,
                "experiment_name": m["experiment_name"],
                "model_name": m["model_name"],
                "y_pred": 1 if y_prob >= 0.5 else 0,
                "y_prob": round(y_prob, 4),
                "score": round(score, 2),
                "run_at": datetime.now(timezone.utc).isoformat(),
            })

        except Exception as e:
            log.warning(f"  Error prediciendo con {m['experiment_name']}: {e}")

    if not scores:
        log.warning(
            f"  [{ticker}] NINGÚN modelo respondió. "
            f"Score por defecto 50.0 (neutral). Decisión no fiable."
        )
        return 50.0, detalle, signals

    # F-12: avisar si algunos modelos fallaron y los pesos se re-normalizan
    n_ok = len(scores)
    n_total = len(modelos)
    if n_ok < n_total:
        modelos_fallidos = [
            m["experiment_name"]
            for m in modelos
            if m["experiment_name"] not in detalle
        ]
        log.warning(
            f"  {n_ok}/{n_total} modelos respondieron. "
            f"Pesos re-normalizados. Modelos fallidos: {modelos_fallidos}"
        )
        # Si menos de la mitad responden, marcar como no fiable
        if n_ok < n_total / 2:
            log.warning(
                f"  ATENCIÓN: menos de la mitad de modelos respondieron "
                f"({n_ok}/{n_total}). Predicción poco fiable."
            )

    total_peso = sum(p for _, p in scores)
    score_final = sum(s * p for s, p in scores) / total_peso if total_peso > 0 else 50.0

    return round(score_final, 2), detalle, signals


def _predict_single(
    row: pd.Series,
    df_hist: pd.DataFrame | None,
    model,
    model_name: str,
    feature_cols: list[str],
    scaler_params: dict | None,
    experiment_name: str,
) -> float | None:
    """Predice con un solo modelo. Retorna probabilidad [0, 1] o None si falla."""
    is_pytorch = model_name in _PYTORCH_MODELS

    if is_pytorch:
        return _predict_pytorch(
            df_hist, model, feature_cols, scaler_params, experiment_name
        )
    else:
        return _predict_sklearn(row, model, feature_cols, scaler_params)


def _predict_sklearn(
    row: pd.Series,
    model,
    feature_cols: list[str],
    scaler_params: dict | None,
) -> float:
    """Predicción sklearn: una sola fila."""
    X = np.array([[row.get(c, 0.0) for c in feature_cols]], dtype=np.float32)

    if scaler_params:
        mean = np.array(scaler_params["mean"], dtype=np.float32)
        std = np.array(scaler_params["std"], dtype=np.float32)
        std = np.where(std == 0, 1, std)
        X = (X - mean) / std

    # predict_proba de nuestro wrapper ya devuelve P(clase=1)
    return float(model.predict_proba(X)[0])


def _predict_pytorch(
    df_hist: pd.DataFrame | None,
    model,
    feature_cols: list[str],
    scaler_params: dict | None,
    experiment_name: str,
) -> float | None:
    """Predicción pytorch: secuencia de velas."""
    if df_hist is None or df_hist.empty:
        log.warning(f"  [{experiment_name}] sin historial para modelo pytorch")
        return None

    # F-65: leer seq_len del modelo (antes hardcoded=10)
    seq_len = getattr(model, "seq_len", 10)
    hist = df_hist.tail(seq_len).copy()

    # Mapear sentiment_label → sentiment_label_encoded si falta
    if (
        "sentiment_label_encoded" in feature_cols
        and "sentiment_label_encoded" not in hist.columns
    ):
        if "sentiment_label" in hist.columns:
            label_map = {"positive": 1, "neutral": 0, "negative": -1}
            hist["sentiment_label_encoded"] = (
                hist["sentiment_label"].map(label_map).fillna(0)
            )
        else:
            hist["sentiment_label_encoded"] = 0

    # F-70: log features faltantes (antes silencioso)
    missing = [c for c in feature_cols if c not in hist.columns]
    if missing:
        log.warning(
            f"  [{experiment_name}] {len(missing)} features faltantes "
            f"rellenadas con 0: {missing}. "
            f"Predicción puede estar sesgada."
        )
        for col in missing:
            hist[col] = 0.0

    X = hist[feature_cols].values.astype(np.float32)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Normalizar con scaler_params (z-score)
    if scaler_params:
        mean = np.array(scaler_params["mean"], dtype=np.float32)
        std = np.array(scaler_params["std"], dtype=np.float32)
        std = np.where(std == 0, 1, std)
        X = (X - mean) / std

    X = np.clip(X, -10, 10)

    # F-66: usar API pública predict_proba() en vez de model._net
    proba = model.predict_proba(X)
    return float(proba[0]) if len(proba) > 0 else None
