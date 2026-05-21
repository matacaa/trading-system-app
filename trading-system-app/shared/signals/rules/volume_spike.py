"""Volumen anómalo: volumen normalizado supera un múltiplo de la media."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class VolumeSpike(BaseSignalSource):
    name = "volume_spike"
    source_type = "rule"
    requires_training = False
    description = "Volumen supera X veces la media (actividad inusual)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        multiplier = config.get("volume_multiplier", 3.0)
        vol_norm = features.get("volume_norm")

        if vol_norm is None:
            return Signal(triggered=False, score=0.0, text="Volumen no disponible",
                         source_name=self.name, source_type=self.source_type)

        triggered = bool(vol_norm > multiplier)
        return Signal(
            triggered=triggered,
            score=min(1.0, vol_norm / (multiplier * 2)) if triggered else 0.0,
            text=f"Volumen anómalo: {vol_norm:.1f}x la media (umbral: {multiplier}x)",
            source_name=self.name,
            source_type=self.source_type,
            priority="urgent" if vol_norm > multiplier * 2 else "normal",
        )
