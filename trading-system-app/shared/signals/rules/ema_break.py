"""EMA break: precio rompe la EMA después de estar N velas por encima/debajo."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class EMABreak(BaseSignalSource):
    name = "ema_break"
    source_type = "rule"
    requires_training = False
    description = "Precio rompe la EMA tras N velas al otro lado (cambio de tendencia)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        ema_col = config.get("ema_col", "ema_21")
        min_bars = config.get("min_bars_below", 5)
        close = features.get("close", 0)
        ema_val = features.get(ema_col, 0)
        if df_hist is None or len(df_hist) < min_bars + 1 or ema_col not in df_hist.columns:
            return Signal(triggered=False, score=0.0, text="Historial insuficiente",
                         source_name=self.name, source_type=self.source_type)
        prev = df_hist.tail(min_bars + 1).head(min_bars)
        was_below = bool((prev["close"] < prev[ema_col]).all())
        now_above = bool(close > ema_val)
        triggered = was_below and now_above
        return Signal(
            triggered=triggered, score=0.85 if triggered else 0.0,
            text=f"EMA break: precio ({close:.2f}) rompe {ema_col} ({ema_val:.2f}) tras {min_bars} velas por debajo",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if triggered else "normal",
        )
