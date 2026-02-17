"""Moduł: training_metrics_parser - Parsowanie metryk z logów treningowych."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TrainingMetrics:
    """Metryki z pojedynczego kroku/epoki treningu."""

    epoch: Optional[int] = None
    total_epochs: Optional[int] = None
    step: Optional[int] = None
    total_steps: Optional[int] = None
    loss: Optional[float] = None
    learning_rate: Optional[float] = None
    accuracy: Optional[float] = None
    progress_percent: Optional[float] = None
    raw_line: Optional[str] = None


class TrainingMetricsParser:
    """
    Parser metryk treningowych z logów.

    Wspiera różne formaty logów z popularnych bibliotek:
    - Unsloth/transformers
    - TRL
    - PyTorch Lightning
    - Standardowe print statements
    """

    # Regex patterns dla różnych formatów
    EPOCH_PATTERNS = [
        r"Epoch\s*(\d+)/(\d+)",  # "Epoch 1/3"
        r"Epoch:\s*(\d+)/(\d+)",  # "Epoch: 1/3"
        r"\[(\d+)/(\d+)\]",  # "[1/3]"
        r"epoch\s*=\s*(\d+).*?total.*?(\d+)",  # "epoch = 1, total = 3"
    ]

    LOSS_PATTERNS = [
        r"[Ll]oss[:\s=]+([0-9.]+)",  # "Loss: 0.45" or "loss=0.45"
        r"train_loss[:\s=]+([0-9.]+)",  # "train_loss: 0.45"
        r"training_loss[:\s=]+([0-9.]+)",  # "training_loss: 0.45"
    ]

    LEARNING_RATE_PATTERNS = [
        r"[Ll]earning [Rr]ate[:\s=]+([0-9.e-]+)",  # "Learning Rate: 2e-4"
        r"lr[:\s=]+([0-9.e-]+)",  # "lr: 0.0002"
    ]

    ACCURACY_PATTERNS = [
        r"[Aa]ccuracy[:\s=]+([0-9.]+)",  # "Accuracy: 0.95"
        r"acc[:\s=]+([0-9.]+)",  # "acc: 0.95"
    ]

    STEP_PATTERNS = [
        r"[Ss]tep\s*(\d+)/(\d+)",  # "Step 100/1000"
        r"\[(\d+)/(\d+)\]",  # "[100/1000]"
    ]

    def parse_line(self, log_line: str) -> Optional[TrainingMetrics]:
        """
        Parsuje pojedynczą linię logu i wydobywa metryki.

        Args:
            log_line: Linia logu do sparsowania

        Returns:
            TrainingMetrics jeśli znaleziono metryki, None w przeciwnym razie
        """
        metrics = TrainingMetrics(raw_line=log_line)
        found_any = False

        # Parsuj epoch
        epoch_info = self._extract_epoch(log_line)
        if epoch_info:
            metrics.epoch, metrics.total_epochs = epoch_info
            found_any = True

        # Parsuj loss
        loss = self._extract_loss(log_line)
        if loss is not None:
            metrics.loss = loss
            found_any = True

        # Parsuj learning rate
        lr = self._extract_learning_rate(log_line)
        if lr is not None:
            metrics.learning_rate = lr
            found_any = True

        # Parsuj accuracy
        acc = self._extract_accuracy(log_line)
        if acc is not None:
            metrics.accuracy = acc
            found_any = True

        # Parsuj step
        step_info = self._extract_step(log_line)
        if step_info:
            metrics.step, metrics.total_steps = step_info
            found_any = True

        # Oblicz progress jeśli mamy epoch
        if metrics.epoch and metrics.total_epochs:
            metrics.progress_percent = (metrics.epoch / metrics.total_epochs) * 100

        return metrics if found_any else None

    def _extract_epoch(self, line: str) -> Optional[tuple[int, int]]:
        """Wydobywa numer epoki i łączną liczbę epok."""
        for pattern in self.EPOCH_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                try:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    return (current, total)
                except (ValueError, IndexError):
                    continue
        return None

    def _extract_loss(self, line: str) -> Optional[float]:
        """Wydobywa wartość loss."""
        for pattern in self.LOSS_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None

    def _extract_learning_rate(self, line: str) -> Optional[float]:
        """Wydobywa learning rate."""
        for pattern in self.LEARNING_RATE_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None

    def _extract_accuracy(self, line: str) -> Optional[float]:
        """Wydobywa accuracy."""
        for pattern in self.ACCURACY_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None

    def _extract_step(self, line: str) -> Optional[tuple[int, int]]:
        """Wydobywa numer kroku i łączną liczbę kroków."""
        for pattern in self.STEP_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                try:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    return (current, total)
                except (ValueError, IndexError):
                    continue
        return None

    def aggregate_metrics(self, metrics_list: List[TrainingMetrics]) -> Dict[str, Any]:
        """
        Agreguje metryki z wielu linii.

        Args:
            metrics_list: Lista metryk do zagregowania

        Returns:
            Słownik z zagregowanymi metrykami
        """
        if not metrics_list:
            return {}

        # Znajdź najnowsze wartości
        latest_epoch = None
        total_epochs = None
        latest_loss = None
        latest_lr = None
        latest_accuracy = None
        progress_percent = None

        loss_values: List[float] = []

        for m in metrics_list:
            if m.epoch is not None:
                latest_epoch = m.epoch
            if m.total_epochs is not None:
                total_epochs = m.total_epochs
            if m.loss is not None:
                latest_loss = m.loss
                loss_values.append(m.loss)
            if m.learning_rate is not None:
                latest_lr = m.learning_rate
            if m.accuracy is not None:
                latest_accuracy = m.accuracy
            if m.progress_percent is not None:
                progress_percent = m.progress_percent

        result: Dict[str, Any] = {
            "current_epoch": latest_epoch,
            "total_epochs": total_epochs,
            "latest_loss": latest_loss,
            "learning_rate": latest_lr,
            "accuracy": latest_accuracy,
            "progress_percent": progress_percent,
        }

        # Oblicz statystyki loss
        if loss_values:
            result["min_loss"] = min(loss_values)
            result["avg_loss"] = sum(loss_values) / len(loss_values)
            result["loss_history"] = loss_values[-10:]  # Last 10 values

        return result
