"""
dataset.py
──────────
PyTorch Dataset que convierte arrays en secuencias
temporales para alimentar modelos LSTM/GRU/Transformer.

Cada muestra es una ventana deslizante de sequence_length
velas consecutivas.

Shape de cada batch:
    X: (batch_size, sequence_length, n_features)
    y: (batch_size,)
"""

from __future__ import annotations

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset


class TimeSeriesDataset(Dataset):
    """
    Dataset de series temporales con ventana deslizante.

    Args:
        X:               array de features (n_samples, n_features)
        y:               array de targets (n_samples,)
        sequence_length: longitud de la ventana temporal
    """

    def __init__(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sequence_length: int = 30,
    ):
        self.sequence_length = sequence_length
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32)

    def __len__(self) -> int:
        return max(0, len(self.X) - self.sequence_length)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        x_seq = self.X[idx : idx + self.sequence_length]
        y_val = self.y[idx + self.sequence_length - 1]
        return x_seq, y_val


def make_dataloaders(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    sequence_length: int = 30,
    batch_size: int = 32,
) -> tuple[DataLoader, DataLoader]:
    """
    Crea DataLoaders de train y test listos para PyTorch.

    Returns:
        (train_loader, test_loader)
    """
    train_dataset = TimeSeriesDataset(X_train, y_train, sequence_length)
    test_dataset = TimeSeriesDataset(X_test, y_test, sequence_length)

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=False,   # No shuffle en series temporales
        drop_last=False,  # N-21: antes True, descartaba últimas muestras
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        drop_last=False,
    )

    return train_loader, test_loader
