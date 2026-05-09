"""VWAP cross down: precio cruza por debajo del VWAP."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class VWAPCrossDown(BaseSignalSource):
    name = "vwap_cross_down"
    source_type = "rule"
    requires_training = False
    description = "Precio cruza por debajo del VWAP (vendedores toman control)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        min_distance_pct = config.get("min_distance_pct", 0.1)
        close = features.get("close", 0)
        vwap_val = features.get("vwap", 0)
        if vwap_val == 0:
            return Signal(triggered=False, score=0.0, text="VWAP no disponible",
                         source_name=self.name, source_type=self.source_type)
        was_above = True
        if df_hist is not None and len(df_hist) >= 2 and "vwap" in df_hist.columns:
            prev = df_hist.iloc[-2]
            was_above = bool(prev.get("close", 0) >= prev.get("vwap", 0))
        distance_pct = (vwap_val - close) / vwap_val * 100
        triggered = bool(close < vwap_val and was_above and distance_pct >= min_distance_pct)
        return Signal(
            triggered=triggered, score=0.7 if triggered else 0.0,
            text=f"VWAP cross down: precio ({close:.2f}) bajo VWAP ({vwap_val:.2f}), -{distance_pct:.2f}%",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if triggered else "normal",
        )
