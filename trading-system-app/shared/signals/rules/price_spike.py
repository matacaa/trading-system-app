"""Spike de precio: movimiento porcentual brusco."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class PriceSpike(BaseSignalSource):
    name = "price_spike"
    source_type = "rule"
    requires_training = False
    description = "Movimiento de precio superior al umbral (% en la última vela)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        threshold_pct = config.get("spike_threshold_pct", 2.0)
        returns = features.get("returns_5")

        if returns is None:
            return Signal(triggered=False, score=0.0, text="Returns no disponible",
                         source_name=self.name, source_type=self.source_type)

        abs_return = abs(returns * 100)
        triggered = bool(abs_return > threshold_pct)
        direction = "alcista" if returns > 0 else "bajista"

        return Signal(
            triggered=triggered,
            score=min(1.0, abs_return / (threshold_pct * 2)) if triggered else 0.0,
            text=f"Spike {direction}: {abs_return:.1f}% (umbral: {threshold_pct}%)",
            source_name=self.name,
            source_type=self.source_type,
            priority="urgent" if abs_return > threshold_pct * 2 else "normal",
        )
