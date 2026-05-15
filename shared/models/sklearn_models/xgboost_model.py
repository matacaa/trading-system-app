"""
xgboost_model.py
────────────────
Implementación de XGBoost en la interfaz BaseModel.

Intervalo de confianza: bootstrap sobre predict_proba.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from xgboost import XGBClassifier, XGBRegressor

from shared.models.base import BaseModel
from shared.models.registry import register_model


@register_model
class XGBoostModel(BaseModel):

    name = "xgboost"
    model_type = "tree"
    requires_gpu = False

    def fit(self, X_train: np.ndarray, y_train: np.ndarray) -> None:
        if self.task == "classification":
            self._model = XGBClassifier(eval_metric="logloss", **self.params)
        else:
            self._model = XGBRegressor(**self.params)
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
        """Intervalo de confianza via bootstrap sobre predict_proba."""
        n_bootstrap = 50
        preds = []

        for _ in range(n_bootstrap):
            idx = np.random.choice(len(X), size=len(X), replace=True)
            X_bs = X[idx]
            if self.task == "classification":
                preds.append(self._model.predict_proba(X_bs)[:, 1])
            else:
                preds.append(self._model.predict(X_bs))

        preds = np.array(preds)
        lower = np.percentile(preds, alpha / 2 * 100, axis=0)
        upper = np.percentile(preds, (1 - alpha / 2) * 100, axis=0)
        return lower, upper

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, path)

    @classmethod
    def load(cls, path: str | Path, task: str = "classification") -> XGBoostModel:
        instance = cls(task=task)
        instance._model = joblib.load(path)
        return instance
