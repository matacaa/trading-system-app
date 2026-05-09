"""EMA bounce: precio toca la EMA desde arriba y rebota."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class EMABounce(BaseSignalSource):
    name = "ema_bounce"
    source_type = "rule"
    requires_training = False
    description = "Precio toca la EMA desde arriba y rebota (soporte dinámico)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        ema_col = config.get("ema_col", "ema_21")
        tolerance_pct = config.get("tolerance_pct", 0.3)
        ema_val = features.get(ema_col, 0)
        close = features.get("close", 0)
        low = features.get("low", close)
        if ema_val == 0:
            return Signal(triggered=False, score=0.0, text=f"{ema_col} no disponible",
                         source_name=self.name, source_type=self.source_type)
        distance_pct = abs(low - ema_val) / ema_val * 100
        bounced = bool(close > ema_val and distance_pct < tolerance_pct)
        return Signal(
            triggered=bounced, score=0.7 if bounced else 0.0,
            text=f"EMA bounce: low ({low:.2f}) tocó {ema_col} ({ema_val:.2f}), cierre por encima ({close:.2f})",
            source_name=self.name, source_type=self.source_type,
        )
