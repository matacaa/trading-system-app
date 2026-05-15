"""RSI divergence: precio y RSI divergen (señal de cambio de tendencia)."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class RSIDivergence(BaseSignalSource):
    name = "rsi_divergence"
    source_type = "rule"
    requires_training = False
    description = "Precio hace nuevo máximo/mínimo pero RSI no confirma (divergencia)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        lookback = config.get("lookback_bars", 20)
        if df_hist is None or len(df_hist) < lookback or "rsi_14" not in df_hist.columns:
            return Signal(triggered=False, score=0.0, text="Historial insuficiente para divergencia",
                         source_name=self.name, source_type=self.source_type)
        window = df_hist.tail(lookback)
        close = features.get("close", 0)
        rsi_now = features.get("rsi_14", 50)
        price_max = float(window["close"].max())
        rsi_at_max = float(window.loc[window["close"].idxmax(), "rsi_14"])
        bearish_div = bool(close >= price_max * 0.998 and rsi_now < rsi_at_max - 5)
        price_min = float(window["close"].min())
        rsi_at_min = float(window.loc[window["close"].idxmin(), "rsi_14"])
        bullish_div = bool(close <= price_min * 1.002 and rsi_now > rsi_at_min + 5)
        triggered = bearish_div or bullish_div
        div_type = "bajista" if bearish_div else "alcista" if bullish_div else ""
        return Signal(
            triggered=triggered, score=0.8 if triggered else 0.0,
            text=f"Divergencia RSI {div_type}: precio {'máximo' if bearish_div else 'mínimo'} pero RSI no confirma",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if triggered else "normal",
            metadata={"divergence_type": div_type},
        )
