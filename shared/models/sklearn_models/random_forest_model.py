"""
random_forest_model.py
──────────────────────
Implementación de Random Forest en la interfaz BaseModel.

Intervalo de confianza: varianza entre predicciones
de los estimadores individuales del ensemble.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from shared.models.base import BaseModel
from shared.models.registry import register_model


@register_model
class RandomForestModel(BaseModel):

    name = "random_forest"
    model_type = "tree"
    requires_gpu = False

    def fit(self, X_train: np.ndarray, y_train: np.ndarray) -> None:
        if self.task == "classification":
            self._model = RandomForestClassifier(**self.params)
        else:
            self._model = RandomForestRegressor(**self.params)
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
        preds = []
        for estimator in self._model.estimators_:
            if self.task == "classification":
                preds.append(estimator.predict_proba(X)[:, 1])
            else:
                preds.append(estimator.predict(X))

        preds = np.array(preds)
        lower = np.percentile(preds, alpha / 2 * 100, axis=0)
        upper = np.percentile(preds, (1 - alpha / 2) * 100, axis=0)
        return lower, upper

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, path)

    @classmethod
    def load(cls, path: str | Path, task: str = "classification") -> "RandomForestModel":
        instance = cls(task=task)
        instance._model = joblib.load(path)
        return instance
