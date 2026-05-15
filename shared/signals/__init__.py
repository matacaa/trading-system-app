"""shared.signals — fuentes de señales (ML + reglas técnicas)."""
from shared.signals.base import (
    SIGNAL_REGISTRY,
    BaseSignalSource,
    Signal,
    get_signal,
    list_signals,
    register_signal,
)

__all__ = ["BaseSignalSource", "Signal", "register_signal", "list_signals", "get_signal"]
