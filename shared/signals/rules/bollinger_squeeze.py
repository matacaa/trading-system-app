"""Bollinger squeeze: ancho de bandas en mínimo histórico reciente."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class BollingerSqueeze(BaseSignalSource):
    name = "bollinger_squeeze"
    source_type = "rule"
    requires_training = False
    description = "Ancho de Bollinger en mínimo de N periodos (explosión de volatilidad inminente)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        lookback = config.get("lookback_bars", 20)
        bb_width = features.get("bb_width")
        if bb_width is None:
            return Signal(triggered=False, score=0.0, text="bb_width no disponible",
                         source_name=self.name, source_type=self.source_type)
        if df_hist is None or len(df_hist) < lookback or "bb_width" not in df_hist.columns:
            return Signal(triggered=False, score=0.0, text="Historial insuficiente para squeeze",
                         source_name=self.name, source_type=self.source_type)
        min_width = float(df_hist.tail(lookback)["bb_width"].min())
        triggered = bool(bb_width <= min_width * 1.05)
        return Signal(
            triggered=triggered, score=0.85 if triggered else 0.0,
            text=f"Bollinger squeeze: ancho ({bb_width:.4f}) cerca del mínimo de {lookback} velas ({min_width:.4f})",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if triggered else "normal",
        )
