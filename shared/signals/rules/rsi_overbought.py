"""RSI sobrecompra: RSI sube por encima del umbral."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class RSIOverbought(BaseSignalSource):
    name = "rsi_overbought"
    source_type = "rule"
    requires_training = False
    description = "RSI sube por encima del umbral (sobrecompra, posible corrección)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        threshold = config.get("rsi_threshold", 70)
        rsi = features.get("rsi_14")
        if rsi is None:
            return Signal(triggered=False, score=0.0, text="RSI no disponible",
                         source_name=self.name, source_type=self.source_type)
        triggered = bool(rsi > threshold)
        return Signal(
            triggered=triggered,
            score=min(1.0, (rsi - threshold) / (100 - threshold)) if triggered else 0.0,
            text=f"RSI sobrecompra: {rsi:.1f} > {threshold}",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if rsi > 85 else "normal",
        )
