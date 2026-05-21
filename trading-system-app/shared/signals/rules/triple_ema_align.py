"""Triple EMA align: las 3 EMAs alineadas en la misma dirección."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class TripleEMAAlign(BaseSignalSource):
    name = "triple_ema_align"
    source_type = "rule"
    requires_training = False
    description = "EMA9 > EMA12 > EMA21 (alcista) o inverso (bajista). Tendencia fuerte confirmada"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        ema9 = features.get("ema_9", 0)
        ema12 = features.get("ema_12", 0)
        ema21 = features.get("ema_21", 0)
        bullish = bool(ema9 > ema12 > ema21)
        bearish = bool(ema9 < ema12 < ema21)
        triggered = bullish or bearish
        direction = "alcista" if bullish else "bajista" if bearish else "neutral"
        return Signal(
            triggered=triggered, score=0.75 if triggered else 0.0,
            text=f"Triple EMA {direction}: EMA9={ema9:.2f}, EMA12={ema12:.2f}, EMA21={ema21:.2f}",
            source_name=self.name, source_type=self.source_type,
            metadata={"direction": direction},
        )
