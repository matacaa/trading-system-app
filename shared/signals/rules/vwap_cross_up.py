"""VWAP cross up: precio cruza por encima del VWAP."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class VWAPCrossUp(BaseSignalSource):
    name = "vwap_cross_up"
    source_type = "rule"
    requires_training = False
    description = "Precio cruza por encima del VWAP (compradores toman control)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        min_distance_pct = config.get("min_distance_pct", 0.1)
        close = features.get("close", 0)
        vwap_val = features.get("vwap", 0)
        if vwap_val == 0:
            return Signal(triggered=False, score=0.0, text="VWAP no disponible",
                         source_name=self.name, source_type=self.source_type)
        was_below = True
        if df_hist is not None and len(df_hist) >= 2 and "vwap" in df_hist.columns:
            prev = df_hist.iloc[-2]
            was_below = bool(prev.get("close", 0) <= prev.get("vwap", 0))
        distance_pct = (close - vwap_val) / vwap_val * 100
        triggered = bool(close > vwap_val and was_below and distance_pct >= min_distance_pct)
        return Signal(
            triggered=triggered, score=0.7 if triggered else 0.0,
            text=f"VWAP cross up: precio ({close:.2f}) cruza VWAP ({vwap_val:.2f}), +{distance_pct:.2f}%",
            source_name=self.name, source_type=self.source_type,
        )
