"""
lightgbm_model.py
─────────────────
Implementación de LightGBM en la interfaz BaseModel.

Intervalo de confianza: varianza entre predicciones
de los árboles individuales del ensemble.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from lightgbm import LGBMClassifier, LGBMRegressor

from shared.models.base import BaseModel
from shared.models.registry import register_model


@register_model
class LightGBMModel(BaseModel):

    name = "lightgbm"
    model_type = "tree"
    requires_gpu = False

    def fit(self, X_train: np.ndarray, y_train: np.ndarray) -> None:
        if self.task == "classification":
            self._model = LGBMClassifier(**self.params)
        else:
            self._model = LGBMRegressor(**self.params)
        self._model.fit(X_train, y_train)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.task == "classification":
            return self._model.predict_proba(X)[:, 1]
        return self.predict(X)

    def confidence_interval(
        self,
        X: np.ndarray,
        alpha: float = 0.05,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Intervalo de confianza via predicciones de cada árbol individual."""
        booster = self._model.booster_
        n_trees = booster.num_trees()
        preds = []
        step = max(1, n_trees // 50)

        for i in range(step, n_trees + 1, step):
            raw = booster.predict(X, num_iteration=i, raw_score=False)
            preds.append(raw)

        if not preds:
            p = self.predict_proba(X)
            lower = np.clip(p - 0.1, 0, 1)
            upper = np.clip(p + 0.1, 0, 1)
            return lower, upper

        preds = np.array(preds)
        lower = np.percentile(preds, alpha / 2 * 100, axis=0)
        upper = np.percentile(preds, (1 - alpha / 2) * 100, axis=0)
        return lower, upper

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, path)

    @classmethod
    def load(cls, path: str | Path, task: str = "classification") -> "LightGBMModel":
        instance = cls(task=task)
        instance._model = joblib.load(path)
        return instance
