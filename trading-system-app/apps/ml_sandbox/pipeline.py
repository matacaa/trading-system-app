"""
pipeline.py — ml_sandbox
────────────────────────
Orquestador de training + evaluate.

Flujo: load_config → load_data → split_data → run_train → run_evaluate

Uso:
    python -m apps.ml_sandbox.pipeline --config config/experiments/aapl_xgboost_1m.yaml
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from apps.ml_sandbox.config import load_config
from apps.ml_sandbox.data.loader import load_data
from apps.ml_sandbox.data.splitter import split_data
from apps.ml_sandbox.evaluate import run_evaluate
from apps.ml_sandbox.train import run_train
from shared.utils.logging import setup_logging

log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="ML Sandbox Pipeline")
    parser.add_argument("--config", required=True, help="Ruta al yaml del experimento")
    parser.add_argument(
        "--only-test", action="store_true",
        help="Solo evaluar (asume modelo ya entrenado con load_from)",
    )
    args = parser.parse_args()

    setup_logging(app_name="ml-sandbox")

    cfg = load_config(args.config)

    log.info(f"Pipeline ML: {cfg.experiment.name}")
    log.info(f"Modelo: {cfg.model.name} | Task: {cfg.experiment.task}")
    log.info(f"Tickers: {cfg.data.tickers}")

    # F-102: cargar datos (necesario tanto para train como para test)
    log.info("Cargando datos...")
    df = load_data(cfg)

    # Separar train/test
    log.info("Separando train/test...")
    X_train, X_test, y_train, y_test, features, scaler_params = split_data(df, cfg)

    # Entrenar
    log.info("Entrenando modelo...")
    model = run_train(cfg, X_train, y_train, features, scaler_params)

    # Construir df_test para evaluate (necesita ts y ticker)
    test_mask = (
        (df["ts"] >= pd.Timestamp(cfg.data.test_start, tz="UTC"))
        & (df["ts"] < pd.Timestamp(cfg.data.test_end, tz="UTC") + pd.Timedelta(days=1))
    )
    df_test = df[test_mask].reset_index(drop=True)

    # Evaluar
    log.info("Evaluando modelo...")
    metrics = run_evaluate(cfg, model, X_test, y_test, df_test)

    log.info(f"Pipeline completado — métricas: {metrics}")


if __name__ == "__main__":
    main()
