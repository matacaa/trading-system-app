"""
transformer_model.py
────────────────────
Implementación de Transformer encoder en la interfaz BaseModel.

Intervalo de confianza via Monte Carlo Dropout.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from shared.models.base import BaseModel
from shared.models.pytorch_models.dataset import make_dataloaders
from shared.models.registry import register_model

log = logging.getLogger(__name__)


class PositionalEncoding(nn.Module):

    def __init__(self, d_model: int, max_len: int = 500, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len).unsqueeze(1).float()
        div = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, : x.size(1)]
        return self.dropout(x)


class TransformerNet(nn.Module):

    def __init__(
        self,
        input_size: int,
        d_model: int = 32,
        nhead: int = 4,
        num_layers: int = 1,
        dropout: float = 0.0,
        task: str = "classification",
    ):
        super().__init__()
        self.task = task
        self.input_proj = nn.Linear(input_size, d_model)
        self.pos_enc = PositionalEncoding(d_model, dropout=dropout)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.bn = nn.BatchNorm1d(d_model)
        self.fc = nn.Linear(d_model, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.input_proj(x)
        x = self.pos_enc(x)
        x = self.transformer(x)
        x = x[:, -1, :]
        x = self.bn(x)
        out = self.fc(x).squeeze(-1)
        return out


@register_model
class TransformerModel(BaseModel):

    name = "transformer"
    model_type = "deep_learning"
    requires_gpu = True

    def __init__(self, task: str = "classification", **params):
        super().__init__(task=task, **params)
        self.d_model = params.get("d_model", 32)
        self.nhead = params.get("nhead", 4)
        self.num_layers = params.get("num_layers", 1)
        self.dropout = params.get("dropout", 0.0)
        self.seq_len = params.get("sequence_length", 10)
        self.epochs = params.get("epochs", 50)
        self.batch_size = params.get("batch_size", 16)
        self.lr = params.get("learning_rate", 0.0001)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._net = None

    def fit(self, X_train: np.ndarray, y_train: np.ndarray) -> None:
        n_features = X_train.shape[1]

        y_train = y_train.astype(np.float32)
        X_train = np.clip(X_train, -10, 10)
        X_train = np.nan_to_num(X_train, nan=0.0, posinf=10.0, neginf=-10.0)

        self._net = TransformerNet(
            input_size=n_features,
            d_model=self.d_model,
            nhead=self.nhead,
            num_layers=self.num_layers,
            dropout=self.dropout,
            task=self.task,
        ).to(self.device)

        optimizer = torch.optim.Adam(self._net.parameters(), lr=self.lr)
        criterion = nn.BCEWithLogitsLoss() if self.task == "classification" else nn.MSELoss()

        train_loader, _ = make_dataloaders(
            X_train, X_train, y_train, y_train,
            sequence_length=self.seq_len,
            batch_size=self.batch_size,
        )

        if len(train_loader) == 0:
            raise ValueError(
                f"DataLoader vacío — reduce sequence_length "
                f"(actual: {self.seq_len}, filas: {len(X_train)})"
            )

        self._net.train()
        for epoch in range(self.epochs):
            total_loss = 0
            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.float().to(self.device)
                optimizer.zero_grad()
                preds = self._net(X_batch)
                loss = criterion(preds, y_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._net.parameters(), max_norm=1.0)
                optimizer.step()
                total_loss += loss.item()
            if (epoch + 1) % 10 == 0:
                log.info(
                    f"  Transformer Epoch {epoch+1}/{self.epochs} "
                    f"loss: {total_loss/len(train_loader):.4f}"
                )

        self._model = self._net

    def _get_sequences(self, X: np.ndarray) -> torch.Tensor:
        X = np.clip(X, -10, 10)
        X = np.nan_to_num(X, nan=0.0, posinf=10.0, neginf=-10.0)
        if len(X) < self.seq_len:
            n_pad = self.seq_len - len(X)
            log.warning(
                f"Transformer: secuencia corta ({len(X)} < {self.seq_len}), "
                f"padding con {n_pad} filas de ceros. "
                f"Predicciones en warm-up no son fiables."
            )
            pad = np.zeros((n_pad, X.shape[1]))
            X = np.vstack([pad, X])
        sequences = []
        for i in range(self.seq_len, len(X) + 1):
            sequences.append(X[i - self.seq_len : i])
        return torch.tensor(np.array(sequences), dtype=torch.float32).to(self.device)

    def predict(self, X: np.ndarray) -> np.ndarray:
        self._net.eval()
        with torch.no_grad():
            seqs = self._get_sequences(X)
            logits = self._net(seqs)
            preds = torch.sigmoid(logits).cpu().numpy()
        preds = np.nan_to_num(preds, nan=0.5)
        if self.task == "classification":
            return (preds > 0.5).astype(int)
        return preds

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        self._net.eval()
        with torch.no_grad():
            seqs = self._get_sequences(X)
            logits = self._net(seqs)
            preds = torch.sigmoid(logits).cpu().numpy()
        preds = np.nan_to_num(preds, nan=0.5)
        return preds

    def confidence_interval(
        self,
        X: np.ndarray,
        alpha: float = 0.05,
        n_samples: int = 100,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Intervalo de confianza via Monte Carlo Dropout."""
        self._net.train()
        seqs = self._get_sequences(X)
        preds = []
        with torch.no_grad():
            for _ in range(n_samples):
                logits = self._net(seqs)
                p = torch.sigmoid(logits).cpu().numpy()
                p = np.nan_to_num(p, nan=0.5)
                preds.append(p)
        self._net.eval()

        preds = np.array(preds)
        lower = np.percentile(preds, alpha / 2 * 100, axis=0)
        upper = np.percentile(preds, (1 - alpha / 2) * 100, axis=0)
        return lower, upper

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self._net.state_dict(),
                "input_size": self._net.input_proj.in_features,
                "d_model": self.d_model,
                "nhead": self.nhead,
                "num_layers": self.num_layers,
                "dropout": self.dropout,
                "task": self.task,
                "seq_len": self.seq_len,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path, task: str = "classification") -> TransformerModel:
        checkpoint = torch.load(path, map_location="cpu")
        instance = cls(
            task=checkpoint["task"],
            sequence_length=checkpoint.get("seq_len", 10),
        )
        instance._net = TransformerNet(
            input_size=checkpoint["input_size"],
            d_model=checkpoint["d_model"],
            nhead=checkpoint["nhead"],
            num_layers=checkpoint["num_layers"],
            dropout=checkpoint["dropout"],
            task=checkpoint["task"],
        )
        instance._net.load_state_dict(checkpoint["state_dict"])
        instance._net.eval()
        instance._model = instance._net
        return instance
