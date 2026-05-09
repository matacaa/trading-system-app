"""ATR expansion: volatilidad creciente."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class ATRExpansion(BaseSignalSource):
    name = "atr_expansion"
    source_type = "rule"
    requires_training = False
    description = "ATR sube significativamente sobre su media reciente (volatilidad creciente)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        lookback = config.get("lookback_bars", 20)
        expansion_pct = config.get("expansion_pct", 50)
        atr = features.get("atr_14")
        if atr is None:
            return Signal(triggered=False, score=0.0, text="atr_14 no disponible",
                         source_name=self.name, source_type=self.source_type)
        if df_hist is None or len(df_hist) < lookback or "atr_14" not in df_hist.columns:
            return Signal(triggered=False, score=0.0, text="Historial insuficiente",
                         source_name=self.name, source_type=self.source_type)
        avg_atr = float(df_hist.tail(lookback)["atr_14"].mean())
        if avg_atr == 0:
            return Signal(triggered=False, score=0.0, text="ATR media = 0",
                         source_name=self.name, source_type=self.source_type)
        pct_above = (atr - avg_atr) / avg_atr * 100
        triggered = bool(pct_above > expansion_pct)
        return Signal(
            triggered=triggered, score=min(1.0, pct_above / 200) if triggered else 0.0,
            text=f"ATR expansion: {pct_above:.0f}% sobre la media de {lookback} velas (umbral: {expansion_pct}%)",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if pct_above > expansion_pct * 2 else "normal",
        )
