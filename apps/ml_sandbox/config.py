"""
config.py — ml_sandbox
───────────────────────
Configuración de experimentos de ML.
Carga el yaml del experimento y expone atributos con acceso por punto.

Credenciales (Supabase, Alpaca, HF) vienen de shared.config.cfg.
Paths (models_dir, tensors_dir) también.

Uso:
    from apps.ml_sandbox.config import load_config
    cfg = load_config("config/experiments/aapl_xgboost_1m.yaml")
    print(cfg.experiment.name, cfg.model.name)
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import yaml

from shared.config import cfg as app_cfg

log = logging.getLogger(__name__)

# Modelos que usan PyTorch (el resto son sklearn)
_PYTORCH_MODELS = {"lstm", "gru", "transformer"}


class ExperimentConfig:
    """Configuración de un experimento de ML, cargada desde un yaml."""

    def __init__(self, raw: dict):
        self._raw = raw

        # ── Credenciales (de shared.config) ────────────────────
        self.supabase_url = app_cfg.supabase_url
        self.supabase_key = app_cfg.supabase_key

        # ── Paths (de shared.config) ───────────────────────────
        self.models_dir = app_cfg.models_dir
        self.tensors_dir = app_cfg.tensors_dir

        # ── Experiment ─────────────────────────────────────────
        exp = raw.get("experiment", {})
        self.experiment = SimpleNamespace(
            name=exp.get("name", "unnamed"),
            task=exp.get("task", "classification"),
        )

        # ── Model ──────────────────────────────────────────────
        model = raw.get("model", {})
        self.model = SimpleNamespace(
            name=model.get("name", "xgboost"),
            params=model.get("params", {}),
            load_from=model.get("load_from"),
        )

        # ── Data ───────────────────────────────────────────────
        data = raw.get("data", {})
        self.data = SimpleNamespace(
            tickers=data.get("tickers", []),
            context_tickers=data.get("context_tickers", []),
            columns=data.get("columns", []),
            target=data.get("target", "target"),
            target_threshold=data.get("target_threshold", 0),
            train_start=data.get("train_start", ""),
            train_end=data.get("train_end", ""),
            test_start=data.get("test_start", ""),
            test_end=data.get("test_end", ""),
            tables=data.get("tables", []),
            dropna=data.get("dropna", True),
            normalize=data.get("normalize", True),
            tensor_interval=data.get("tensor_interval", "1m"),
            tensor_type=data.get("tensor_type", "features"),
            sequence_length=data.get("sequence_length", 10),
            source=data.get("source", "auto"),  # "silver", "tensor", or "auto"
        )

        # ── Output ─────────────────────────────────────────────
        output = raw.get("output", {})
        self.output = SimpleNamespace(
            save_model=output.get("save_model", True),
            save_predictions=output.get("save_predictions", True),
            save_metrics=output.get("save_metrics", True),
            metrics=output.get("metrics", ["accuracy", "f1", "precision", "recall", "roc_auc"]),
        )

        # ── PyTorch ────────────────────────────────────────────
        pytorch = raw.get("pytorch", {})
        self.pytorch = SimpleNamespace(
            epochs=pytorch.get("epochs", 50),
            batch_size=pytorch.get("batch_size", 16),
            learning_rate=pytorch.get("learning_rate", 0.0001),
        )

        # ── Computed ───────────────────────────────────────────
        self.is_pytorch = self.model.name in _PYTORCH_MODELS
        self.is_sklearn = not self.is_pytorch

    def __repr__(self) -> str:
        return (
            f"ExperimentConfig(name={self.experiment.name}, "
            f"model={self.model.name}, task={self.experiment.task})"
        )


def load_config(path: str | Path) -> ExperimentConfig:
    """Carga un yaml de experimento y devuelve ExperimentConfig."""
    path = Path(path)
    if not path.is_absolute():
        path = app_cfg.repo_root / path

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cfg = ExperimentConfig(raw)
    log.info(f"Config cargada: {cfg}")
    return cfg
