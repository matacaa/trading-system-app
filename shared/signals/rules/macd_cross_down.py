"""MACD cross down: línea MACD cruza por debajo de la señal."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class MACDCrossDown(BaseSignalSource):
    name = "macd_cross_down"
    source_type = "rule"
    requires_training = False
    description = "MACD cruza por debajo de la línea de señal (momentum bajista)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        min_diff = config.get("min_diff", 0.0)
        macd = features.get("macd_line", 0)
        signal = features.get("macd_signal", 0)
        diff = signal - macd
        was_above = True
        if df_hist is not None and len(df_hist) >= 2 and "macd_line" in df_hist.columns:
            prev = df_hist.iloc[-2]
            was_above = bool(prev.get("macd_line", 0) >= prev.get("macd_signal", 0))
        crossed = bool(diff > min_diff and was_above)
        return Signal(
            triggered=crossed, score=min(1.0, abs(diff) * 10) if crossed else 0.0,
            text=f"MACD cross down: MACD ({macd:.4f}) < señal ({signal:.4f})",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if crossed else "normal",
        )
