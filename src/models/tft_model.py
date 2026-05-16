"""Simplified Temporal Fusion Transformer for price prediction.

A lightweight TFT-style model built with pure PyTorch primitives.
Provides an alternative to :class:`LSTMModel` for comparative
evaluation during the training phase.
"""

import torch
import torch.nn as nn


class SimpleTFT(nn.Module):
    """Simplified Temporal Fusion Transformer with pre-norm architecture.

    Architecture: input projection → multi-head self-attention → feed-forward
    block → output head. Both the attention and feed-forward blocks use
    pre-normalisation (LayerNorm before the sublayer) with residual
    connections.
    """

    def __init__(
        self,
        input_size: int = 12,
        hidden_size: int = 64,
        num_heads: int = 4,
        output_size: int = 1,
        dropout: float = 0.1,
        sequence_length: int = 24,
    ) -> None:
        """Initialise the TFT layers.

        Args:
            input_size: Number of features per timestep.
            hidden_size: Dimensionality of the transformer hidden state.
            num_heads: Number of attention heads.
            output_size: Dimensionality of the prediction target.
            dropout: Dropout probability applied throughout.
            sequence_length: Length of the input sequence (used for
                optional positional encoding).
        """
        super().__init__()
        self.input_projection = nn.Linear(input_size, hidden_size)
        self.pos_encoding = nn.Parameter(torch.randn(1, sequence_length, hidden_size) * 0.1)

        self.norm_attn = nn.LayerNorm(hidden_size)
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True,
        )

        self.norm_ffn = nn.LayerNorm(hidden_size)
        self.ffn = nn.Sequential(
            nn.Linear(hidden_size, hidden_size * 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size * 4, hidden_size),
            nn.Dropout(dropout),
        )

        self.output_head = nn.Linear(hidden_size, output_size)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass through the transformer encoder.

        Args:
            x: Input tensor of shape ``(batch, seq_len, input_size)``.

        Returns:
            Prediction tensor of shape ``(batch, output_size)``.
        """
        x = self.input_projection(x)
        x = x + self.pos_encoding[:, : x.size(1), :]
        x = self.dropout(x)

        residual = x
        x = self.norm_attn(x)
        attn_out, _ = self.attention(x, x, x)
        x = residual + attn_out

        residual = x
        x = self.norm_ffn(x)
        ffn_out = self.ffn(x)
        x = residual + ffn_out

        last = x[:, -1, :]
        out = self.output_head(last)
        return out
