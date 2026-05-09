"""Sentimiento extremo negativo: FinBERT detecta noticia muy negativa."""
import pandas as pd
from shared.signals.base import BaseSignalSource, Signal, register_signal

@register_signal
class SentimentExtremeNegative(BaseSignalSource):
    name = "sentiment_extreme_negative"
    source_type = "rule"
    requires_training = False
    description = "FinBERT score muy negativo (noticia bajista impactante, alerta de riesgo)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        threshold = config.get("negative_threshold", -0.85)
        score = features.get("sentiment_score")
        if score is None:
            return Signal(triggered=False, score=0.0, text="Sentimiento no disponible",
                         source_name=self.name, source_type=self.source_type)
        triggered = bool(score < threshold)
        return Signal(
            triggered=triggered, score=abs(float(score)) if triggered else 0.0,
            text=f"Sentimiento muy negativo: FinBERT score {score:.3f} < {threshold}",
            source_name=self.name, source_type=self.source_type,
            priority="urgent",
        )
