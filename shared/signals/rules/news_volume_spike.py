"""News volume spike: número inusual de noticias sobre el ticker."""
import pandas as pd

from shared.signals.base import BaseSignalSource, Signal, register_signal


@register_signal
class NewsVolumeSpike(BaseSignalSource):
    name = "news_volume_spike"
    source_type = "rule"
    requires_training = False
    description = "Número de noticias sube drásticamente (algo está pasando con el ticker)"

    def evaluate(self, features: pd.Series, config: dict | None = None, df_hist=None) -> Signal:
        config = config or {}
        multiplier = config.get("news_multiplier", 3.0)
        news_count = features.get("news_count", 0)
        news_avg = features.get("news_count_avg", 0)
        if news_avg == 0:
            if news_count > 2:
                return Signal(triggered=True, score=0.6,
                    text=f"Spike de noticias: {news_count} noticias (sin media de referencia)",
                    source_name=self.name, source_type=self.source_type)
            return Signal(triggered=False, score=0.0, text="Sin datos de volumen de noticias",
                         source_name=self.name, source_type=self.source_type)
        ratio = news_count / news_avg
        triggered = bool(ratio > multiplier)
        return Signal(
            triggered=triggered, score=min(1.0, ratio / (multiplier * 2)) if triggered else 0.0,
            text=f"Spike de noticias: {news_count} noticias ({ratio:.1f}x la media, umbral: {multiplier}x)",
            source_name=self.name, source_type=self.source_type,
            priority="urgent" if ratio > multiplier * 2 else "normal",
        )
