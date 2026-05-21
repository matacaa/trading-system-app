"""Sentiment flip: sentimiento cambia de dirección en las últimas horas."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class SentimentFlip(BaseSignalSource):
    name = "sentiment_flip"
    source_type = "rule"
    requires_training = False
    description = "Sentimiento cambia de positivo a negativo o viceversa (cambio de narrativa)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        lookback = config.get("lookback_bars", 30)
        flip_threshold = config.get("flip_threshold", 0.5)
        score_now = features.get("sentiment_score")
        if score_now is None:
            return Signal(triggered=False, score=0.0, text="Sentimiento no disponible",
                         source_name=self.name, source_type=self.source_type)
        if df_hist is None or len(df_hist) < lookback or "sentiment_score" not in df_hist.columns:
            return Signal(triggered=False, score=0.0, text="Historial de sentimiento insuficiente",
                         source_name=self.name, source_type=self.source_type)
        past_scores = df_hist.tail(lookback)["sentiment_score"].dropna()
        if past_scores.empty:
            return Signal(triggered=False, score=0.0, text="Sin datos de sentimiento históricos",
                         source_name=self.name, source_type=self.source_type)
        avg_past = float(past_scores.mean())
        diff = score_now - avg_past
        triggered = bool(abs(diff) > flip_threshold)
        direction = "positivo → negativo" if diff < 0 else "negativo → positivo"
        return Signal(
            triggered=triggered, score=min(1.0, abs(diff)) if triggered else 0.0,
            text=f"Sentiment flip ({direction}): ahora {score_now:.2f} vs media {avg_past:.2f} (cambio: {diff:+.2f})",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if abs(diff) > flip_threshold * 2 else "normal",
        )
