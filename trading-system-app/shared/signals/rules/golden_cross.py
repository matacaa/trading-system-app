"""Golden cross: EMA9 cruza por encima de EMA21 (proxy de SMA20/SMA50)."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class GoldenCross(BaseSignalSource):
    name = "golden_cross"
    source_type = "rule"
    requires_training = False
    description = "EMA9 cruza por encima de EMA21 — proxy de golden cross (SMA20/SMA50)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        ema_short = features.get("ema_9", 0)   # Proxy de SMA20 — usar SMA real en Fase 6
        ema_long = features.get("ema_21", 0)    # Proxy de SMA50 — usar SMA real en Fase 6
        close = features.get("close", 0)

        crossed = bool(close > ema_short > ema_long)
        return Signal(
            triggered=crossed,
            score=0.8 if crossed else 0.0,
            text=f"Golden cross: precio ({close:.2f}) > EMA9 > EMA21",
            source_name=self.name,
            source_type=self.source_type,
        )
