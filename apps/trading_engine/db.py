"""
db.py
─────
Funciones de escritura en PostgreSQL para el trading-engine.
Guarda señales, decisiones, logs y timings en las tablas gold_*.

Uso:
    from apps.trading_engine.db import save_signals, save_decision, save_log
"""

from __future__ import annotations

import json
import logging

from shared.db import execute, upsert
from shared.utils.time import utc_isoformat

log = logging.getLogger(__name__)


def save_signals(signals: list[dict]) -> None:
    """Guarda las señales de cada modelo en gold_signals."""
    if not signals:
        return
    try:
        upsert("gold_signals", signals, conflict="ts,ticker,experiment_name")
        log.info(f"  {len(signals)} señales guardadas en gold_signals")
    except Exception as e:
        log.error(f"Error guardando señales: {e}")


def save_decision(decision: dict, detalle: dict) -> None:
    """Guarda la decisión combinada en gold_decisions."""
    try:
        row = {
            "ts": decision["ts"],
            "ticker": decision["ticker"],
            "decision": decision["decision"],
            "score_final": decision["score_final"],
            "detalle_modelos": json.dumps(detalle),
            "ejecutada": decision.get("ejecutada", False),
            "motivo_rechazo": decision.get("motivo_rechazo", ""),
            "run_at": utc_isoformat(),
        }
        upsert("gold_decisions", [row], conflict="ts,ticker")
        log.info(
            f"  Decisión guardada: {decision['ticker']} -> "
            f"{decision['decision']} ({decision['score_final']:.1f})"
        )
    except Exception as e:
        log.error(f"Error guardando decisión: {e}")


def save_log(
    duration_s: float,
    tickers_procesados: list[str],
    senales_generadas: int,
    ordenes_ejecutadas: int,
    errores: list[str],
    status: str,
    run_id: str = "",
    max_retries: int = 3,
) -> None:
    """Guarda el log de auditoría de cada ejecución en gold_logs."""
    sql = """
        INSERT INTO gold_logs (run_at, run_id, duration_s, tickers_procesados,
                               senales_generadas, ordenes_ejecutadas, errores, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        utc_isoformat(),
        run_id,
        round(duration_s, 2),
        json.dumps(tickers_procesados),
        senales_generadas,
        ordenes_ejecutadas,
        json.dumps(errores),
        status,
    )

    for attempt in range(1, max_retries + 1):
        try:
            execute(sql, params)
            log.info(f"  Log guardado: {status} ({duration_s:.1f}s)")
            return
        except Exception as e:
            if attempt < max_retries:
                log.warning(f"  Retry save_log ({attempt}/{max_retries}): {e}")
                import time
                time.sleep(1)
            else:
                log.error(f"Error guardando log tras {max_retries} intentos: {e}")


def save_timing(
    fase: str,
    duration_s: float,
    run_id: str,
    ticker: str | None = None,
    status: str = "ok",
) -> None:
    """Guarda el timing de una fase del pipeline en gold_pipeline_timings."""
    try:
        execute(
            """INSERT INTO gold_pipeline_timings (run_at, run_id, fase, duration_s, ticker, status)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (utc_isoformat(), run_id, fase, round(duration_s, 3), ticker, status),
        )
    except Exception as e:
        log.error(f"Error guardando timing de {fase}: {e}")
