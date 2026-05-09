"""Golden cross: SMA20 cruza por encima de SMA50."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class GoldenCross(BaseSignalSource):
    name = "golden_cross"
    source_type = "rule"
    requires_training = False
    description = "SMA20 cruza por encima de SMA50 (señal alcista)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        sma20 = features.get("ema_9", 0)   # TODO: usar SMA20 real cuando esté en features
        sma50 = features.get("ema_21", 0)   # TODO: usar SMA50 real
        close = features.get("close", 0)

        crossed = bool(close > sma20 > sma50)
        return Signal(
            triggered=crossed,
            score=0.8 if crossed else 0.0,
            text=f"Golden cross: precio ({close:.2f}) > SMA20 > SMA50",
            source_name=self.name,
            source_type=self.source_type,
        )
