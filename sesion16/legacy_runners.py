"""
shared/legacy_runners.py
────────────────────────
Funciones extraídas de apps/api/main.py (legacy).

Estas funciones generan YAMLs temporales y ejecutan pipelines
via subprocess. Se mantienen para compatibilidad hasta que los
routers de backtest y training se reescriban completamente
(pasos 6.4 y 6.9).

NO usar para código nuevo — usar los routers reescritos.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def run_pipeline(cmd: list[str], timeout: int = 300) -> dict:
    """Ejecuta un subprocess con timeout y captura stdout/stderr."""
    log.info("Ejecutando: %s", " ".join(cmd))
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        duration = time.time() - start
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration": round(duration, 2),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout después de {timeout}s", "duration": timeout}
    except Exception as e:
        return {"success": False, "error": str(e), "duration": time.time() - start}


def generate_experiment_yaml(
    model: str,
    ticker: str = "AAPL",
    timeframe: str = "1m",
    train_start: str = "",
    train_end: str = "",
    test_start: str = "",
    test_end: str = "",
    context_tickers: list[str] | None = None,
    columns: list[str] | None = None,
    params: dict[str, Any] | None = None,
    experiment_name: str = "",
) -> tuple[Path, str]:
    """Genera un YAML temporal para entrenar un modelo."""
    ticker_lower = ticker.lower()
    exp_name = (
        experiment_name.strip()
        if experiment_name.strip()
        else f"{ticker_lower}_{model}_{timeframe}_v1"
    )

    default_columns = [
        "ema_9", "ema_12", "ema_21", "ema_50", "rsi_14",
        "macd_line", "macd_signal", "macd_hist",
        "bb_pct", "bb_width", "atr_14", "range_pct",
        "vwap", "volume_norm",
        "returns_5", "returns_15",
        "hour", "dayofweek", "is_market_open",
        "news_count_1h", "news_count_24h",
        "sentiment_score", "sentiment_label_encoded",
    ]

    config = {
        "experiment": {"name": exp_name, "task": "classification"},
        "model": {"name": model, "params": params or {}},
        "data": {
            "tickers": [ticker],
            "context_tickers": context_tickers or [],
            "tables": [f"silver_features_{timeframe}"],
            "columns": columns or default_columns,
            "target": "returns",
            "train_start": train_start,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
            "dropna": True,
        },
        "output": {"save_model": True, "save_predictions": True, "save_metrics": True},
    }

    tmp = Path(tempfile.mktemp(suffix=".yaml", prefix="train_"))
    with open(tmp, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    return tmp, exp_name


def generate_backtest_yaml(
    name: str = "",
    tickers: list[str] | None = None,
    context_tickers: list[str] | None = None,
    test_start: str = "",
    test_end: str = "",
    timeframe: str = "1m",
    modelos: list[dict[str, Any]] | None = None,
    guardrails: dict[str, Any] | None = None,
    capital: dict[str, Any] | None = None,
) -> tuple[Path, str]:
    """Genera un YAML temporal para un backtest dual-dirección.

    Sesión 16: guardrails se pasan directamente como dict estructurado
    desde el frontend. Cada guardrail tiene 'on'/'activo' + params
    direccionales (long_max, short_min, etc.).
    """
    tickers = tickers or ["AAPL"]
    modelos = modelos or []
    g = guardrails or {}

    bt_name = (
        name.strip()
        if name.strip()
        else f"bt_{'_'.join(tickers).lower()}_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}"
    )

    # Normalizar guardrails: convertir 'on' a 'activo' para backward compat
    guardrails_normalized = {}
    for gd_name, gd_cfg in g.items():
        if isinstance(gd_cfg, dict):
            normalized = dict(gd_cfg)
            if "on" in normalized and "activo" not in normalized:
                normalized["activo"] = normalized.pop("on")
            guardrails_normalized[gd_name] = normalized
        elif isinstance(gd_cfg, bool):
            guardrails_normalized[gd_name] = {"activo": gd_cfg}

    config = {
        "backtest": {"name": bt_name, "description": f"Backtest UI — {test_start} a {test_end}"},
        "data": {
            "tickers": tickers,
            "context_tickers": context_tickers or [],
            "test_start": test_start,
            "test_end": test_end,
            "timeframe": timeframe,
        },
        "modelos": [
            {
                "experiment_name": m["experiment_name"],
                "activo": m.get("activo", True),
                "peso": m.get("peso", 0.15),
            }
            for m in modelos
        ],
        "capital": capital or {
            "inicial": 100000,
            "posicion_max_pct": g.get("posicion_max_pct", 10),
            "stop_loss_pct": g.get("stop_loss_pct", g.get("stop_loss", 5)),
            "take_profit_pct": g.get("take_profit_pct", g.get("take_profit", 10)),
            "cierre_fin_dia": g.get("cierre_fin_dia", True),
        },
        "guardrails": guardrails_normalized,
    }

    tmp = Path(tempfile.mktemp(suffix=".yaml", prefix="backtest_"))
    with open(tmp, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    return tmp, bt_name
