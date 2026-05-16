"""LSTM model for cryptocurrency price prediction.

Provides a PyTorch LSTM module with configurable architecture, a
custom Dataset for sliding-window sequence creation, and a helper
function to wire them together.
"""

from typing import Any

import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset


class LSTMModel(nn.Module):
    """Multi-layer LSTM with a linear output head.

    Uses the last timestep's hidden state to produce a single
    prediction (e.g. next-period price or return).
    """

    def __init__(
        self,
        input_size: int = 12,
        hidden_size: int = 128,
        num_layers: int = 2,
        output_size: int = 1,
        dropout: float = 0.2,
    ) -> None:
        """Initialise the LSTM layers and output head.

        Args:
            input_size: Number of features per timestep.
            hidden_size: Number of hidden units per LSTM layer.
            num_layers: Number of stacked LSTM layers.
            output_size: Dimensionality of the prediction target.
            dropout: Dropout probability applied between LSTM layers
                     (only effective when ``num_layers > 1``).
        """
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass through LSTM and linear head.

        Args:
            x: Input tensor of shape ``(batch, sequence_length, input_size)``.

        Returns:
            Prediction tensor of shape ``(batch, output_size)``.
        """
        _, (hidden, _) = self.lstm(x)
        last_hidden = hidden[-1]
        out = self.fc(last_hidden)
        return out


class LSTMDataset(Dataset):
    """Sliding-window dataset for LSTM training.

    Each sample is a sequence of ``sequence_length`` consecutive
    feature rows paired with the target value immediately following
    that window.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        target_col: str,
        sequence_length: int = 24,
    ) -> None:
        """Build the sequence dataset from a DataFrame.

        Args:
            df: DataFrame containing feature and target columns.
            feature_cols: Column names to use as model inputs.
            target_col: Column name to use as prediction target.
            sequence_length: Number of past timesteps in each sample.
        """
        self.features = torch.tensor(
            df[feature_cols].values, dtype=torch.float32
        )
        self.targets = torch.tensor(
            df[target_col].values, dtype=torch.float32
        )
        self.sequence_length = sequence_length

    def __len__(self) -> int:
        """Return the number of sequences available."""
        return len(self.features) - self.sequence_length

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        """Return a (sequence, target) pair.

        Args:
            idx: Starting index of the sequence window.

        Returns:
            Tuple of ``(sequence_tensor, target_tensor)`` each as
            ``float32``. The sequence has shape
            ``(sequence_length, num_features)``, and the target is
            a scalar tensor.
        """
        seq = self.features[idx : idx + self.sequence_length]
        tgt = self.targets[idx + self.sequence_length]
        return seq, tgt


def create_sequences(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    seq_len: int = 24,
) -> LSTMDataset:
    """Create an LSTMDataset from a DataFrame.

    Args:
        df: DataFrame with feature and target columns.
        feature_cols: Column names to use as inputs.
        target_col: Column name to use as target.
        seq_len: Number of past timesteps per sample.

    Returns:
        Configured :class:`LSTMDataset` instance.
    """
    return LSTMDataset(
        df=df,
        feature_cols=feature_cols,
        target_col=target_col,
        sequence_length=seq_len,
    )
