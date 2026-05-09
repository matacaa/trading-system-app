"""Death cross: SMA rápida cruza por debajo de SMA lenta."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class DeathCross(BaseSignalSource):
    name = "death_cross"
    source_type = "rule"
    requires_training = False
    description = "SMA rápida cruza por debajo de SMA lenta (señal bajista)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        fast_col = config.get("fast_ema", "ema_9")
        slow_col = config.get("slow_ema", "ema_21")
        fast = features.get(fast_col, 0)
        slow = features.get(slow_col, 0)
        close = features.get("close", 0)
        crossed = bool(close < fast < slow)
        return Signal(
            triggered=crossed, score=0.8 if crossed else 0.0,
            text=f"Death cross: precio ({close:.2f}) < {fast_col} ({fast:.2f}) < {slow_col} ({slow:.2f})",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if crossed else "normal",
        )
