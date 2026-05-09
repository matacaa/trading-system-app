"""MACD zero cross: MACD cruza la línea cero."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class MACDZeroCross(BaseSignalSource):
    name = "macd_zero_cross"
    source_type = "rule"
    requires_training = False
    description = "MACD cruza la línea cero (cambio de tendencia de medio plazo)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        macd = features.get("macd_line", 0)
        was_negative = True
        was_positive = True
        if df_hist is not None and len(df_hist) >= 2 and "macd_line" in df_hist.columns:
            prev_macd = float(df_hist.iloc[-2].get("macd_line", 0))
            was_negative = prev_macd < 0
            was_positive = prev_macd > 0
        cross_up = bool(macd > 0 and was_negative)
        cross_down = bool(macd < 0 and was_positive)
        triggered = cross_up or cross_down
        direction = "alcista" if cross_up else "bajista"
        return Signal(
            triggered=triggered, score=0.75 if triggered else 0.0,
            text=f"MACD zero cross {direction}: MACD ({macd:.4f}) cruza cero",
            source_name=self.name, source_type=self.source_type,
            metadata={"direction": direction},
        )
