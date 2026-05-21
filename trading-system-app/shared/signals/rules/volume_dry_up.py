"""Volume dry up: volumen se seca, posible ruptura inminente."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class VolumeDryUp(BaseSignalSource):
    name = "volume_dry_up"
    source_type = "rule"
    requires_training = False
    description = "Volumen cae muy por debajo de la media (falta de interés, ruptura cerca)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        threshold = config.get("dry_threshold", 0.3)
        vol_norm = features.get("volume_norm")
        if vol_norm is None:
            return Signal(triggered=False, score=0.0, text="volume_norm no disponible",
                         source_name=self.name, source_type=self.source_type)
        triggered = bool(vol_norm < threshold)
        return Signal(
            triggered=triggered,
            score=max(0, (threshold - vol_norm) / threshold) if triggered else 0.0,
            text=f"Volumen seco: {vol_norm:.2f}x la media (umbral: <{threshold}x)",
            source_name=self.name, source_type=self.source_type,
        )
