"""
train.py
────────
Orquesta el entrenamiento completo:
    1. Instancia el modelo desde shared.models.registry
    2. Entrena con X_train, y_train
    3. Guarda el nuevo modelo en disco
    4. Registra en silver_model_registry con metadatos completos
    5. Elimina modelo anterior DESPUÉS del upsert (F-50: antes se borraba antes)

Uso:
    from apps.ml_sandbox.train import run_train
    model = run_train(cfg, X_train, y_train, feature_names, scaler_params)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from shared.db import sb
from shared.models.base import BaseModel
from shared.models.registry import get_model
from apps.ml_sandbox.config import ExperimentConfig

log = logging.getLogger(__name__)


def run_train(
    cfg: ExperimentConfig,
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: list[str],
    scaler_params: dict | None = None,
) -> BaseModel:
    """
    Entrena el modelo y lo registra en Supabase.

    Returns:
        modelo entrenado listo para evaluate.py
    """
    log.info(f"Iniciando entrenamiento — {cfg.experiment.name}")
    log.info(f"Modelo: {cfg.model.name} | Task: {cfg.experiment.task}")
    log.info(f"X_train: {X_train.shape} | y_train: {y_train.shape}")
    log.info(f"Features: {feature_names}")

    # Instanciar modelo desde registry (usa shared.models)
    model = get_model(
        model_name=cfg.model.name,
        task=cfg.experiment.task,
        params=cfg.model.params,
    )

    # Si load_from está especificado, cargar modelo existente
    if cfg.model.load_from:
        log.info(f"Cargando modelo desde: {cfg.model.load_from}")
        model = model.__class__.load(cfg.model.load_from, task=cfg.experiment.task)
        # F-53: registrar en registry aunque sea cargado (antes se saltaba)
        _register_model(
            cfg=cfg,
            feature_names=feature_names,
            file_path=Path(cfg.model.load_from),
            duration_s=0,
            feature_source="loaded",
            timeframe="unknown",
            scaler_params=scaler_params,
        )
        return model

    # Entrenar
    log.info("Entrenando...")
    t0 = datetime.now()
    model.fit(X_train, y_train)
    elapsed = round((datetime.now() - t0).total_seconds(), 1)
    log.info(f"Entrenamiento completado en {elapsed}s")

    # Feature source y timeframe
    if cfg.is_pytorch:
        feature_source = "tensor"
        timeframe = cfg.data.tensor_interval
    else:
        feature_source = "silver"
        table = cfg.data.tables[0] if cfg.data.tables else "silver_features_1m"
        timeframe = table.replace("silver_features_", "")

    # Guardar modelo en disco
    file_path: Path | None = None
    if cfg.output.save_model:
        ext = ".pt" if cfg.is_pytorch else ".pkl"
        # F-56: usar UTC para consistencia en nombres de fichero
        date = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        file_path = cfg.models_dir / f"{cfg.experiment.name}_{date}{ext}"
        model.save(file_path)
        log.info(f"Modelo guardado en: {file_path}")

    # Registrar en silver_model_registry
    _register_model(
        cfg=cfg,
        feature_names=feature_names,
        file_path=file_path,
        duration_s=elapsed,
        feature_source=feature_source,
        timeframe=timeframe,
        scaler_params=scaler_params,
    )

    return model


def _register_model(
    cfg: ExperimentConfig,
    feature_names: list[str],
    file_path: Path | None,
    duration_s: float,
    feature_source: str,
    timeframe: str,
    scaler_params: dict | None,
) -> None:
    """Registra nueva versión del modelo en silver_model_registry (D-16).

    Cada re-entrenamiento crea una versión nueva. La anterior se
    desactiva pero NO se borra (permite rollback y A/B testing).
    """
    exp_name = cfg.experiment.name

    # 1. Obtener versión actual más alta
    try:
        resp = (
            sb.table("silver_model_registry")
            .select("version")
            .eq("experiment_name", exp_name)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        current_max = resp.data[0]["version"] if resp.data else 0
    except Exception:
        current_max = 0

    new_version = current_max + 1

    # 2. Desactivar versiones anteriores
    try:
        sb.table("silver_model_registry").update(
            {"is_active": False}
        ).eq("experiment_name", exp_name).execute()
    except Exception as e:
        log.warning(f"Error desactivando versiones anteriores: {e}")

    # 3. Insertar nueva versión como activa, status='training' hasta que evaluate complete
    try:
        # A-02: guardar solo el filename, no el path absoluto
        relative_path = file_path.name if file_path else None

        # N-06: incluir ticker(s) en el registro
        tickers_str = ",".join(cfg.data.tickers) if hasattr(cfg.data, "tickers") else None

        sb.table("silver_model_registry").insert({
            "experiment_name": exp_name,
            "version": new_version,
            "is_active": True,
            "status": "training",
            "model_name": cfg.model.name,
            "ticker": tickers_str,
            "task": cfg.experiment.task,
            "interval": timeframe,
            "train_start": cfg.data.train_start,
            "train_end": cfg.data.train_end,
            "test_start": cfg.data.test_start,
            "test_end": cfg.data.test_end,
            "file_path": relative_path,
            "feature_columns": json.dumps(feature_names),
            "feature_source": feature_source,
            "timeframe": timeframe,
            "scaler_params": json.dumps(scaler_params) if scaler_params else None,
            # F-51: initial metrics incluye training_duration
            "metrics_summary": json.dumps({"training_duration_s": duration_s}),
        }).execute()

        log.info(
            f"Registrado en silver_model_registry: {exp_name} v{new_version} "
            f"(v{current_max} desactivada)"
        )
        log.info(f"  feature_source: {feature_source} | timeframe: {timeframe}")

    except Exception as e:
        log.error(f"Error registrando en silver_model_registry: {e}")
