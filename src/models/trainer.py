"""Training loop and checkpointing for the LSTM price prediction model.

Provides a trainer class with early stopping, validation-based
checkpointing, and evaluation utilities.
"""

from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.optim import Optimizer
from torch.utils.data import DataLoader

from src.models.lstm_model import LSTMClassifier, LSTMModel
from src.utils.config import settings
from src.utils.helpers import format_pair_for_binance
from src.utils.logger import get_logger

_logger = get_logger(__name__)


class LSTMTrainer:
    """Train and evaluate an LSTMModel with early stopping and checkpointing.

    Uses cross-entropy loss for binary classification (up/down).
    """

    def __init__(
        self,
        model: LSTMModel,
        learning_rate: float = 0.001,
        checkpoint_dir: str | None = None,
    ) -> None:
        """Initialise the trainer.

        Args:
            model: An :class:`LSTMModel` instance to train.
            learning_rate: Learning rate for the Adam optimiser.
            checkpoint_dir: Directory for model checkpoints. Defaults to
                ``settings.MODEL_CHECKPOINT_DIR``.
        """
        self.model = model
        self.optimizer: Optimizer = torch.optim.Adam(
            model.parameters(), lr=learning_rate
        )
        self.criterion: nn.Module = nn.CrossEntropyLoss()
        self.checkpoint_dir = Path(checkpoint_dir or settings.MODEL_CHECKPOINT_DIR)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._best_val_loss = float("inf")
        self._patience_counter = 0
        self._patience = 10

    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        epochs: int = 50,
        symbol: str = "",
        min_epochs: int = 10,
    ) -> dict[str, list[float]]:
        """Run the full training loop with early stopping.

        Args:
            train_loader: DataLoader for training samples.
            val_loader: DataLoader for validation samples.
            epochs: Maximum number of training epochs.
            symbol: Trading pair symbol (e.g. ``BTCUSDT``) used for
                checkpoint filenames.
            min_epochs: Minimum number of epochs to run regardless of
                early stopping.

        Returns:
            Dict with keys ``train_loss`` and ``val_loss``, each a list
            of per-epoch loss values.
        """
        history: dict[str, list[float]] = {"train_loss": [], "val_loss": []}
        self._best_val_loss = float("inf")
        self._patience_counter = 0
        self._current_symbol = symbol

        _logger.info("Starting training for up to %d epochs (min_epochs=%d)", epochs, min_epochs)

        for epoch in range(1, epochs + 1):
            train_loss = self._run_epoch(train_loader, training=True)
            val_loss, val_acc = self.evaluate(val_loader)

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)

            _logger.info(
                "Epoch %3d/%d — train_loss: %.6f, val_loss: %.6f, val_acc: %.1f%%%s",
                epoch,
                epochs,
                train_loss,
                val_loss,
                val_acc,
                "  (best so far)" if val_loss < self._best_val_loss else "",
            )

            if val_loss < self._best_val_loss:
                self._best_val_loss = val_loss
                self._patience_counter = 0
                self.save_checkpoint(
                    symbol=self._current_symbol,
                    epoch=epoch,
                    train_loss=train_loss,
                    val_loss=val_loss,
                )
            else:
                self._patience_counter += 1
                if epoch >= min_epochs and self._patience_counter >= self._patience:
                    _logger.info(
                        "Early stopping triggered after %d epochs without improvement",
                        self._patience,
                    )
                    break

        _logger.info("Training complete — best val_loss: %.6f", self._best_val_loss)
        return history

    def _run_epoch(self, loader: DataLoader, training: bool = True) -> float:
        """Run a single epoch in train or eval mode.

        Args:
            loader: DataLoader to iterate over.
            training: If True, update model weights.

        Returns:
            Average loss over all batches in the epoch.
        """
        if training:
            self.model.train()
        else:
            self.model.eval()

        total_loss = 0.0
        num_batches = 0

        for features, targets in loader:
            if training:
                self.optimizer.zero_grad()

            outputs = self.model(features)
            loss = self.criterion(outputs, targets)

            if training:
                loss.backward()
                self.optimizer.step()

            total_loss += loss.item()
            num_batches += 1

        return total_loss / max(num_batches, 1)

    def evaluate(self, loader: DataLoader) -> tuple[float, float]:
        """Compute average loss and accuracy on a DataLoader.

        Args:
            loader: DataLoader to evaluate on.

        Returns:
            Tuple of ``(average_loss, accuracy_pct)``.
        """
        self.model.eval()
        total_loss = 0.0
        correct = 0
        total = 0
        num_batches = 0

        with torch.no_grad():
            for features, targets in loader:
                outputs = self.model(features)
                loss = self.criterion(outputs, targets)
                total_loss += loss.item()
                num_batches += 1

                preds = outputs.argmax(dim=1)
                correct += (preds == targets).sum().item()
                total += targets.size(0)

        avg_loss = total_loss / max(num_batches, 1)
        accuracy = correct / total * 100 if total > 0 else 0.0
        return avg_loss, accuracy

    def save_checkpoint(self, symbol: str, epoch: int, train_loss: float, val_loss: float) -> None:
        """Persist a model checkpoint to disk.

        Args:
            symbol: Trading pair symbol (e.g. ``BTCUSDT``).
            epoch: Current epoch number.
            train_loss: Training loss at this checkpoint.
            val_loss: Validation loss at this checkpoint.
        """
        safe_symbol = format_pair_for_binance(symbol)
        path = self.checkpoint_dir / f"{safe_symbol}_lstm_best.pt"
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": val_loss,
            },
            path,
        )
        _logger.info("Checkpoint saved to %s (epoch %d, val_loss=%.6f)", path, epoch, val_loss)

    def load_checkpoint(self, symbol: str) -> dict[str, Any] | None:
        """Load the best checkpoint for *symbol* if it exists.

        Args:
            symbol: Trading pair symbol (e.g. ``BTCUSDT``).

        Returns:
            Dict with ``epoch`` and ``val_loss`` if loaded, or None if
            no checkpoint file was found.
        """
        safe_symbol = format_pair_for_binance(symbol)
        path = self.checkpoint_dir / f"{safe_symbol}_lstm_best.pt"
        if not path.exists():
            _logger.warning("No checkpoint found at %s", path)
            return None

        checkpoint = torch.load(path, map_location="cpu")
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        _logger.info(
            "Loaded checkpoint from %s (epoch %d, val_loss=%.6f)",
            path,
            checkpoint["epoch"],
            checkpoint["val_loss"],
        )
        return {"epoch": checkpoint["epoch"], "val_loss": checkpoint["val_loss"]}


class LSTMClassifierTrainer:
    """Train and evaluate an LSTMClassifier with early stopping and checkpointing.

    Uses BCE loss for binary volatility-regime classification. The model
    is assumed to produce a sigmoid output in [0, 1].
    """

    def __init__(
        self,
        model: LSTMClassifier,
        learning_rate: float = 0.001,
        checkpoint_dir: str | None = None,
    ) -> None:
        """Initialise the trainer.

        Args:
            model: An :class:`LSTMClassifier` instance to train.
            learning_rate: Learning rate for the Adam optimiser.
            checkpoint_dir: Directory for model checkpoints. Defaults to
                ``settings.MODEL_CHECKPOINT_DIR``.
        """
        self.model = model
        self.optimizer: Optimizer = torch.optim.Adam(
            model.parameters(), lr=learning_rate
        )
        self.criterion: nn.Module = nn.BCELoss()
        self.checkpoint_dir = Path(checkpoint_dir or settings.MODEL_CHECKPOINT_DIR)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._best_val_loss = float("inf")
        self._patience_counter = 0
        self._patience = 10

    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        epochs: int = 50,
        symbol: str = "",
        min_epochs: int = 10,
    ) -> dict[str, list[float]]:
        """Run the full training loop with early stopping.

        Logs both BCE loss and binary accuracy every epoch.

        Args:
            train_loader: DataLoader for training samples.
            val_loader: DataLoader for validation samples.
            epochs: Maximum number of training epochs.
            symbol: Trading pair symbol (e.g. ``BTCUSDT``) used for
                checkpoint filenames.
            min_epochs: Minimum number of epochs to run regardless of
                early stopping.

        Returns:
            Dict with keys ``train_loss``, ``val_loss``, and
            ``val_accuracy``, each a list of per-epoch values.
        """
        history: dict[str, list[float]] = {
            "train_loss": [], "val_loss": [], "val_accuracy": [],
        }
        self._best_val_loss = float("inf")
        self._patience_counter = 0
        self._current_symbol = symbol

        _logger.info("Starting training for up to %d epochs (min_epochs=%d)", epochs, min_epochs)

        for epoch in range(1, epochs + 1):
            train_loss = self._run_epoch(train_loader, training=True)
            val_loss = self.evaluate(val_loader)
            val_acc = self.evaluate_accuracy(val_loader)

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)
            history["val_accuracy"].append(val_acc)

            _logger.info(
                "Epoch %3d/%d — train_loss: %.6f, val_loss: %.6f, val_acc: %.2f%%%s",
                epoch,
                epochs,
                train_loss,
                val_loss,
                val_acc * 100,
                "  (best so far)" if val_loss < self._best_val_loss else "",
            )

            if val_loss < self._best_val_loss:
                self._best_val_loss = val_loss
                self._patience_counter = 0
                self.save_checkpoint(
                    symbol=self._current_symbol,
                    epoch=epoch,
                    train_loss=train_loss,
                    val_loss=val_loss,
                )
            else:
                self._patience_counter += 1
                if epoch >= min_epochs and self._patience_counter >= self._patience:
                    _logger.info(
                        "Early stopping triggered after %d epochs without improvement",
                        self._patience,
                    )
                    break

        _logger.info("Training complete — best val_loss: %.6f", self._best_val_loss)
        return history

    def _run_epoch(self, loader: DataLoader, training: bool = True) -> float:
        """Run a single epoch in train or eval mode.

        Args:
            loader: DataLoader to iterate over.
            training: If True, update model weights.

        Returns:
            Average BCE loss over all batches in the epoch.
        """
        if training:
            self.model.train()
        else:
            self.model.eval()

        total_loss = 0.0
        num_batches = 0

        for features, targets in loader:
            if training:
                self.optimizer.zero_grad()

            outputs = self.model(features)
            loss = self.criterion(outputs, targets.float().unsqueeze(1))

            if training:
                loss.backward()
                self.optimizer.step()

            total_loss += loss.item()
            num_batches += 1

        return total_loss / max(num_batches, 1)

    def evaluate(self, loader: DataLoader) -> float:
        """Compute average BCE loss on a DataLoader without weight updates.

        Args:
            loader: DataLoader to evaluate on.

        Returns:
            Average loss value.
        """
        self.model.eval()
        total_loss = 0.0
        num_batches = 0

        with torch.no_grad():
            for features, targets in loader:
                outputs = self.model(features)
                loss = self.criterion(outputs, targets.float().unsqueeze(1))
                total_loss += loss.item()
                num_batches += 1

        return total_loss / max(num_batches, 1)

    def evaluate_accuracy(self, loader: DataLoader) -> float:
        """Compute binary classification accuracy on a DataLoader.

        Predicted probability above 0.5 counts as class 1, below or
        equal as class 0.

        Args:
            loader: DataLoader to evaluate on.

        Returns:
            Accuracy as a float between 0 and 1.
        """
        self.model.eval()
        correct = 0
        total = 0

        with torch.no_grad():
            for features, targets in loader:
                outputs = self.model(features)
                preds = (outputs > 0.5).long().squeeze(1)
                correct += (preds == targets).sum().item()
                total += targets.size(0)

        return correct / total if total > 0 else 0.0

    def save_checkpoint(self, symbol: str, epoch: int, train_loss: float, val_loss: float) -> None:
        """Persist a model checkpoint to disk with a ``_classifier`` suffix.

        Args:
            symbol: Trading pair symbol (e.g. ``BTCUSDT``).
            epoch: Current epoch number.
            train_loss: Training loss at this checkpoint.
            val_loss: Validation loss at this checkpoint.
        """
        safe_symbol = format_pair_for_binance(symbol)
        path = self.checkpoint_dir / f"{safe_symbol}_classifier_best.pt"
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": val_loss,
            },
            path,
        )
        _logger.info("Checkpoint saved to %s (epoch %d, val_loss=%.6f)", path, epoch, val_loss)

    def load_checkpoint(self, symbol: str) -> dict[str, Any] | None:
        """Load the best classifier checkpoint for *symbol* if it exists.

        Looks for a file with the ``_classifier`` suffix.

        Args:
            symbol: Trading pair symbol (e.g. ``BTCUSDT``).

        Returns:
            Dict with ``epoch`` and ``val_loss`` if loaded, or None if
            no checkpoint file was found.
        """
        safe_symbol = format_pair_for_binance(symbol)
        path = self.checkpoint_dir / f"{safe_symbol}_classifier_best.pt"
        if not path.exists():
            _logger.warning("No classifier checkpoint found at %s", path)
            return None

        checkpoint = torch.load(path, map_location="cpu")
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        _logger.info(
            "Loaded classifier checkpoint from %s (epoch %d, val_loss=%.6f)",
            path,
            checkpoint["epoch"],
            checkpoint["val_loss"],
        )
        return {"epoch": checkpoint["epoch"], "val_loss": checkpoint["val_loss"]}
