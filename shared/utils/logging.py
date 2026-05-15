"""
logging.py
──────────
Setup común de logging. Formato consistente en todo el monorepo.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
    app_name: str = "trading-system",
) -> None:
    """Configura logging con formato común.
    
    Args:
        level: nivel mínimo (DEBUG, INFO, WARNING, ERROR)
        log_file: ruta opcional a fichero de log
        app_name: nombre de la app para el prefijo
    """
    fmt = f"%(asctime)s [%(levelname)s] [{app_name}] %(name)s: %(message)s"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=handlers,
        force=True,
    )
