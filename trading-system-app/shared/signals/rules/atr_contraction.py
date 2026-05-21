"""ATR contraction: volatilidad en mínimos."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class ATRContraction(BaseSignalSource):
    name = "atr_contraction"
    source_type = "rule"
    requires_training = False
    description = "ATR cae a mínimo de N periodos (calma antes de la tormenta)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        lookback = config.get("lookback_bars", 20)
        atr = features.get("atr_14")
        if atr is None:
            return Signal(triggered=False, score=0.0, text="atr_14 no disponible",
                         source_name=self.name, source_type=self.source_type)
        if df_hist is None or len(df_hist) < lookback or "atr_14" not in df_hist.columns:
            return Signal(triggered=False, score=0.0, text="Historial insuficiente",
                         source_name=self.name, source_type=self.source_type)
        min_atr = float(df_hist.tail(lookback)["atr_14"].min())
        triggered = bool(atr <= min_atr * 1.05)
        return Signal(
            triggered=triggered, score=0.7 if triggered else 0.0,
            text=f"ATR contraction: ATR ({atr:.4f}) en mínimo de {lookback} velas ({min_atr:.4f})",
            source_name=self.name, source_type=self.source_type,
        )
