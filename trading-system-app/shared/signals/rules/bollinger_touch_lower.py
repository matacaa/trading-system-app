"""Bollinger touch lower: precio toca o rompe la banda inferior."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class BollingerTouchLower(BaseSignalSource):
    name = "bollinger_touch_lower"
    source_type = "rule"
    requires_training = False
    description = "Precio toca o rompe la banda inferior de Bollinger (posible rebote)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        threshold = config.get("bb_pct_threshold", 0.05)
        bb_pct = features.get("bb_pct")
        if bb_pct is None:
            return Signal(triggered=False, score=0.0, text="bb_pct no disponible",
                         source_name=self.name, source_type=self.source_type)
        triggered = bool(bb_pct < threshold)
        return Signal(
            triggered=triggered,
            score=min(1.0, (threshold - bb_pct) / threshold) if triggered else 0.0,
            text=f"Bollinger lower touch: bb_pct={bb_pct:.3f} < {threshold}",
            source_name=self.name, source_type=self.source_type,
        )
