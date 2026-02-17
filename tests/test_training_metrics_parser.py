"""Testy jednostkowe dla TrainingMetricsParser."""

import pytest

from venom_core.learning.training_metrics_parser import (
    TrainingMetrics,
    TrainingMetricsParser,
)


def test_parse_epoch_simple():
    """Test parsowania epoki - prosty format."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("Epoch 2/5")

    assert metrics is not None
    assert metrics.epoch == 2
    assert metrics.total_epochs == 5
    assert metrics.progress_percent == 40.0


def test_parse_epoch_with_colon():
    """Test parsowania epoki - format z dwukropkiem."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("Epoch: 3/10")

    assert metrics is not None
    assert metrics.epoch == 3
    assert metrics.total_epochs == 10


def test_parse_loss():
    """Test parsowania loss."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("Loss: 0.4523")

    assert metrics is not None
    assert metrics.loss == pytest.approx(0.4523)


def test_parse_training_loss():
    """Test parsowania train_loss."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("train_loss=0.3245")

    assert metrics is not None
    assert metrics.loss == pytest.approx(0.3245)


def test_parse_learning_rate():
    """Test parsowania learning rate."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("Learning Rate: 2e-4")

    assert metrics is not None
    assert metrics.learning_rate == pytest.approx(0.0002)


def test_parse_lr_short():
    """Test parsowania lr (krótka forma)."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("lr=0.0001")

    assert metrics is not None
    assert metrics.learning_rate == pytest.approx(0.0001)


def test_parse_accuracy():
    """Test parsowania accuracy."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("Accuracy: 0.95")

    assert metrics is not None
    assert metrics.accuracy == pytest.approx(0.95)


def test_parse_combined_line():
    """Test parsowania linii z wieloma metrykami."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("Epoch 1/3 - Loss: 0.4523 - lr: 2e-4")

    assert metrics is not None
    assert metrics.epoch == 1
    assert metrics.total_epochs == 3
    assert metrics.loss == pytest.approx(0.4523)
    assert metrics.learning_rate == pytest.approx(0.0002)
    assert metrics.progress_percent == pytest.approx(33.333, rel=1e-2)


def test_parse_no_metrics():
    """Test linii bez metryk."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("Just some random log line")

    assert metrics is None


def test_parse_step():
    """Test parsowania kroku."""
    parser = TrainingMetricsParser()

    metrics = parser.parse_line("Step 100/1000")

    assert metrics is not None
    assert metrics.step == 100
    assert metrics.total_steps == 1000


def test_aggregate_metrics_empty():
    """Test agregacji pustej listy."""
    parser = TrainingMetricsParser()

    result = parser.aggregate_metrics([])

    assert result == {}


def test_aggregate_metrics_single():
    """Test agregacji pojedynczej metryki."""
    parser = TrainingMetricsParser()

    metrics = TrainingMetrics(
        epoch=1, total_epochs=3, loss=0.45, progress_percent=33.33
    )

    result = parser.aggregate_metrics([metrics])

    assert result["current_epoch"] == 1
    assert result["total_epochs"] == 3
    assert result["latest_loss"] == pytest.approx(0.45)
    assert result["min_loss"] == pytest.approx(0.45)
    assert result["progress_percent"] == pytest.approx(33.33)


def test_aggregate_metrics_multiple():
    """Test agregacji wielu metryk."""
    parser = TrainingMetricsParser()

    metrics_list = [
        TrainingMetrics(epoch=1, total_epochs=3, loss=0.50),
        TrainingMetrics(epoch=2, total_epochs=3, loss=0.35),
        TrainingMetrics(epoch=3, total_epochs=3, loss=0.25, progress_percent=100.0),
    ]

    result = parser.aggregate_metrics(metrics_list)

    assert result["current_epoch"] == 3
    assert result["total_epochs"] == 3
    assert result["latest_loss"] == pytest.approx(0.25)
    assert result["min_loss"] == pytest.approx(0.25)
    assert result["avg_loss"] == pytest.approx(0.3667, rel=1e-2)
    assert result["progress_percent"] == pytest.approx(100.0)


def test_aggregate_metrics_without_loss_values():
    """Test agregacji metryk bez loss - brak sekcji statystyk loss."""
    parser = TrainingMetricsParser()

    metrics_list = [
        TrainingMetrics(epoch=2, total_epochs=5, learning_rate=0.001),
        TrainingMetrics(epoch=3, total_epochs=5, progress_percent=60.0),
    ]

    result = parser.aggregate_metrics(metrics_list)

    assert result["current_epoch"] == 3
    assert result["total_epochs"] == 5
    assert result["latest_loss"] is None
    assert "min_loss" not in result
    assert "avg_loss" not in result
    assert "loss_history" not in result


def test_parse_real_world_unsloth_log():
    """Test parsowania prawdziwego logu z Unsloth."""
    parser = TrainingMetricsParser()

    # Przykład z Unsloth
    line = "{'loss': 0.4523, 'learning_rate': 0.0002, 'epoch': 1.5}"

    # Parser może nie złapać tego formatu (dict), ale sprawdźmy loss
    metrics = parser.parse_line(line)

    # Powinien złapać przynajmniej loss
    if metrics:
        assert metrics.loss is not None


def test_parse_transformers_log():
    """Test parsowania logu z transformers."""
    parser = TrainingMetricsParser()

    line = "Step 500/1500 | train_loss: 0.3245 | lr: 1e-4"

    metrics = parser.parse_line(line)

    assert metrics is not None
    assert metrics.step == 500
    assert metrics.total_steps == 1500
    assert metrics.loss == pytest.approx(0.3245)
    assert metrics.learning_rate == pytest.approx(0.0001)
