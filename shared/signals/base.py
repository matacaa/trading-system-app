"""
shared/signals/base.py
──────────────────────
Interfaz común para todas las fuentes de señales.
Tanto los modelos ML como las reglas técnicas implementan esta interfaz,
lo que permite que el Squawk Engine los trate de forma idéntica.

Para añadir una señal nueva:
    1. Crea un archivo en signals/rules/
    2. Hereda de BaseSignalSource
    3. Añade @register_signal
    4. Implementa evaluate()
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

log = logging.getLogger(__name__)

# ── Resultado de una evaluación ───────────────────────────────────

@dataclass
class Signal:
    """Resultado de evaluar una fuente de señal."""
    triggered: bool         # ¿Se disparó la señal?
    score: float            # 0.0-1.0 (confianza o intensidad)
    text: str               # Texto legible para el squawk
    source_name: str = ""   # Nombre de la fuente que generó la señal
    source_type: str = ""   # "rule" o "ml"
    priority: str = "normal"  # "urgent", "normal", "low"
    metadata: dict = None   # Datos extra (indicadores, scores por modelo, etc.)

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# ── Clase base ────────────────────────────────────────────────────

class BaseSignalSource(ABC):
    """Interfaz que todas las fuentes de señales deben implementar.

    Atributos de clase (obligatorios en cada subclase):
        name:              identificador único ("golden_cross", "rsi_oversold", etc.)
        source_type:       "rule" o "ml"
        requires_training: False para reglas, True para ML
        description:       descripción corta para la UI
    """

    name: str = ""
    source_type: str = ""           # "rule" | "ml"
    requires_training: bool = False
    description: str = ""

    @abstractmethod
    def evaluate(
        self,
        features: pd.Series,
        config: dict | None = None,
        df_hist: pd.DataFrame | None = None,
    ) -> Signal:
        """Evalúa la señal para una vela.

        Args:
            features: última vela con indicadores técnicos (pd.Series)
            config:   parámetros del usuario (umbrales, etc.)
            df_hist:  historial de velas anteriores (para reglas que necesitan comparar)

        Returns:
            Signal con triggered, score, text
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, type={self.source_type})"


# ── Registro de señales ───────────────────────────────────────────

SIGNAL_REGISTRY: dict[str, type[BaseSignalSource]] = {}


def register_signal(cls: type[BaseSignalSource]) -> type[BaseSignalSource]:
    """Decorador que registra una fuente de señal."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} no tiene 'name' definido.")
    SIGNAL_REGISTRY[cls.name] = cls
    log.debug(f"Señal registrada: {cls.name} ({cls.__name__})")
    return cls


def list_signals() -> list[dict]:
    """Devuelve metadata de todas las señales registradas."""
    _auto_discover_signals()
    return [
        {
            "name": cls.name,
            "source_type": cls.source_type,
            "requires_training": cls.requires_training,
            "description": cls.description,
        }
        for cls in SIGNAL_REGISTRY.values()
    ]


def get_signal(name: str) -> BaseSignalSource:
    """Instancia una fuente de señal por nombre."""
    _auto_discover_signals()
    if name not in SIGNAL_REGISTRY:
        raise ValueError(f"Señal '{name}' no registrada. Disponibles: {list(SIGNAL_REGISTRY.keys())}")
    return SIGNAL_REGISTRY[name]()


def _auto_discover_signals():
    """Importa automáticamente todos los módulos en signals/rules/."""
    if SIGNAL_REGISTRY:
        return
    import importlib
    import pkgutil
    from pathlib import Path

    rules_dir = Path(__file__).parent / "rules"
    if not rules_dir.is_dir():
        return
    for _, module_name, _ in pkgutil.iter_modules([str(rules_dir)]):
        if module_name.startswith("_"):
            continue
        try:
            importlib.import_module(f"shared.signals.rules.{module_name}")
        except ImportError as e:
            log.warning(f"No se pudo importar signals.rules.{module_name}: {e}")
