"""
shared/signals/evaluator.py
────────────────────────────
Evalúa las 25 señales rule-based registradas y devuelve un score compuesto.

Usado en Paso 2 del pipeline (compartido por todos los usuarios de un ticker).

Uso:
    from shared.signals.evaluator import evaluate_signals

    triggered, score, texts = evaluate_signals(row, df_hist, active_signals=None)
"""

from __future__ import annotations

import logging

import pandas as pd

from shared.signals.base import Signal, get_signal, list_signals

log = logging.getLogger(__name__)


def evaluate_signals(
    row: pd.Series,
    df_hist: pd.DataFrame | None = None,
    active_signals: list[str] | None = None,
    signal_config: dict | None = None,
) -> tuple[list[Signal], float, list[str]]:
    """
    Evalúa señales rule-based para una vela.

    Args:
        row:            última vela con indicadores técnicos (pd.Series)
        df_hist:        historial de velas anteriores
        active_signals: lista de nombres de señales a evaluar (None = todas)
        signal_config:  config por señal, e.g. {"rsi_oversold": {"rsi_threshold": 25}}

    Returns:
        (triggered_signals, score_compuesto_0_100, textos_para_squawk)
    """
    signal_config = signal_config or {}

    # Obtener señales disponibles
    available = {s["name"]: s for s in list_signals()}

    # Filtrar a las activas (si se especifican)
    if active_signals is not None:
        names_to_eval = [n for n in active_signals if n in available]
    else:
        names_to_eval = list(available.keys())

    if not names_to_eval:
        return [], 0.0, []

    triggered: list[Signal] = []
    all_scores: list[float] = []
    texts: list[str] = []

    for name in names_to_eval:
        try:
            signal_source = get_signal(name)
            cfg = signal_config.get(name, {})
            result = signal_source.evaluate(row, config=cfg, df_hist=df_hist)

            if result.triggered:
                triggered.append(result)
                all_scores.append(result.score)
                texts.append(result.text)

        except Exception as e:
            log.warning("Error evaluando señal '%s': %s", name, e)

    # Score compuesto: promedio de scores de señales disparadas, escalado a 0-100
    if all_scores:
        avg_score = sum(all_scores) / len(all_scores)
        score_0_100 = round(avg_score * 100, 2)
    else:
        score_0_100 = 0.0

    if triggered:
        log.info(
            "  Señales disparadas: %d/%d — score señales: %.1f",
            len(triggered), len(names_to_eval), score_0_100,
        )
        for sig in triggered:
            log.debug("    %s (%.2f): %s", sig.source_name, sig.score, sig.text)

    return triggered, score_0_100, texts


def combine_scores(
    score_ml: float,
    score_signals: float,
    signal_weight: float = 0.2,
) -> float:
    """
    Combina score ML (0-100) con score de señales rule-based (0-100).

    Args:
        score_ml:       score del ensemble ML (0-100)
        score_signals:  score de señales rule-based (0-100)
        signal_weight:  peso de las señales (0.0-1.0, default 0.2 = 20%)

    Returns:
        score combinado (0-100)
    """
    if score_signals <= 0:
        return score_ml

    weight = max(0.0, min(1.0, signal_weight))
    combined = score_ml * (1 - weight) + score_signals * weight
    return round(combined, 2)
