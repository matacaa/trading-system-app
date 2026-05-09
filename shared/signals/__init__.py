"""shared.signals — fuentes de señales (ML + reglas técnicas)."""
from shared.signals.base import (
    BaseSignalSource, Signal, register_signal,
    list_signals, get_signal, SIGNAL_REGISTRY,
)
__all__ = ["BaseSignalSource", "Signal", "register_signal", "list_signals", "get_signal"]
