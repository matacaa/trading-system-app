"""
test_models.py
──────────────
F-110: Tests para BaseModel y las implementaciones concretas.
Verifica que todos los modelos respetan la API de BaseModel.
"""

from __future__ import annotations

import numpy as np
import pytest


# ─── Tests de la interfaz BaseModel ───────────────────────────────────────────


class TestBaseModelInterface:
    """Verifica que BaseModel define la API correcta."""

    def test_cannot_instantiate_abstract(self):
        from shared.models.base import BaseModel
        with pytest.raises(TypeError):
            BaseModel(task="classification")

    def test_has_required_methods(self):
        from shared.models.base import BaseModel
        required = ["fit", "predict", "predict_proba", "confidence_interval", "save", "load"]
        for method in required:
            assert hasattr(BaseModel, method), f"BaseModel falta método: {method}"


# ─── Tests de modelos sklearn ─────────────────────────────────────────────────


class TestSklearnModels:
    """Verifica que los modelos sklearn respetan BaseModel API."""

    @pytest.fixture
    def sample_data(self):
        np.random.seed(42)
        X = np.random.randn(100, 5).astype(np.float32)
        y = (X[:, 0] > 0).astype(np.int32)
        return X, y

    def test_xgboost_fit_predict(self, sample_data):
        from shared.models.sklearn_models.xgboost_model import XGBoostModel
        X, y = sample_data
        model = XGBoostModel(task="classification", n_estimators=10)
        assert not model.is_fitted
        model.fit(X, y)
        assert model.is_fitted
        preds = model.predict(X)
        assert preds.shape == (100,)
        assert set(preds).issubset({0, 1})

    def test_xgboost_predict_proba(self, sample_data):
        from shared.models.sklearn_models.xgboost_model import XGBoostModel
        X, y = sample_data
        model = XGBoostModel(task="classification", n_estimators=10)
        model.fit(X, y)
        proba = model.predict_proba(X)
        assert proba.shape == (100,)
        assert (proba >= 0).all() and (proba <= 1).all()

    def test_random_forest_fit_predict(self, sample_data):
        from shared.models.sklearn_models.random_forest_model import RandomForestModel
        X, y = sample_data
        model = RandomForestModel(task="classification", n_estimators=10)
        model.fit(X, y)
        preds = model.predict(X)
        assert preds.shape == (100,)

    def test_lightgbm_fit_predict(self, sample_data):
        from shared.models.sklearn_models.lightgbm_model import LightGBMModel
        X, y = sample_data
        model = LightGBMModel(task="classification", n_estimators=10)
        model.fit(X, y)
        preds = model.predict(X)
        assert preds.shape == (100,)

    def test_xgboost_save_load(self, sample_data, tmp_path):
        from shared.models.sklearn_models.xgboost_model import XGBoostModel
        X, y = sample_data
        model = XGBoostModel(task="classification", n_estimators=10)
        model.fit(X, y)
        path = tmp_path / "test_model.pkl"
        model.save(path)
        loaded = XGBoostModel.load(path, task="classification")
        assert loaded.is_fitted
        np.testing.assert_array_equal(model.predict(X), loaded.predict(X))

    def test_confidence_interval_shape(self, sample_data):
        from shared.models.sklearn_models.xgboost_model import XGBoostModel
        X, y = sample_data
        model = XGBoostModel(task="classification", n_estimators=10)
        model.fit(X, y)
        lower, upper = model.confidence_interval(X)
        assert lower.shape == upper.shape
        assert (upper >= lower).all()


# ─── Tests de modelos PyTorch ─────────────────────────────────────────────────


class TestPyTorchModels:
    """Verifica que los modelos PyTorch respetan BaseModel API."""

    @pytest.fixture
    def sample_sequence_data(self):
        np.random.seed(42)
        X = np.random.randn(50, 5).astype(np.float32)
        y = (X[:, 0] > 0).astype(np.float32)
        return X, y

    def test_lstm_fit_predict(self, sample_sequence_data):
        from shared.models.pytorch_models.lstm_model import LSTMModel
        X, y = sample_sequence_data
        model = LSTMModel(task="classification", sequence_length=5, epochs=2, batch_size=8)
        model.fit(X, y)
        assert model.is_fitted
        preds = model.predict(X)
        assert len(preds) > 0

    def test_lstm_predict_proba_range(self, sample_sequence_data):
        from shared.models.pytorch_models.lstm_model import LSTMModel
        X, y = sample_sequence_data
        model = LSTMModel(task="classification", sequence_length=5, epochs=2, batch_size=8)
        model.fit(X, y)
        proba = model.predict_proba(X)
        assert (proba >= 0).all() and (proba <= 1).all()

    def test_gru_fit_predict(self, sample_sequence_data):
        from shared.models.pytorch_models.gru_model import GRUModel
        X, y = sample_sequence_data
        model = GRUModel(task="classification", sequence_length=5, epochs=2, batch_size=8)
        model.fit(X, y)
        preds = model.predict(X)
        assert len(preds) > 0

    def test_transformer_fit_predict(self, sample_sequence_data):
        from shared.models.pytorch_models.transformer_model import TransformerModel
        X, y = sample_sequence_data
        model = TransformerModel(
            task="classification", sequence_length=5, epochs=2,
            batch_size=8, d_model=8, nhead=2,
        )
        model.fit(X, y)
        preds = model.predict(X)
        assert len(preds) > 0

    def test_lstm_save_load(self, sample_sequence_data, tmp_path):
        from shared.models.pytorch_models.lstm_model import LSTMModel
        X, y = sample_sequence_data
        model = LSTMModel(task="classification", sequence_length=5, epochs=2, batch_size=8)
        model.fit(X, y)
        path = tmp_path / "test_lstm.pt"
        model.save(path)
        loaded = LSTMModel.load(path, task="classification")
        assert loaded.is_fitted
        assert loaded.seq_len == 5
