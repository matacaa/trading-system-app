"""RSI sobreventa: RSI cae por debajo de un umbral."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class RSIOversold(BaseSignalSource):
    name = "rsi_oversold"
    source_type = "rule"
    requires_training = False
    description = "RSI cae por debajo del umbral (sobreventa, posible rebote)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        threshold = config.get("rsi_threshold", 30)
        rsi = features.get("rsi_14")

        if rsi is None:
            return Signal(triggered=False, score=0.0, text="RSI no disponible",
                         source_name=self.name, source_type=self.source_type)

        triggered = bool(rsi < threshold)
        return Signal(
            triggered=triggered,
            score=max(0, (threshold - rsi) / threshold) if triggered else 0.0,
            text=f"RSI sobreventa: {rsi:.1f} < {threshold}",
            source_name=self.name,
            source_type=self.source_type,
            priority="urgent" if rsi < 20 else "normal",
        )
