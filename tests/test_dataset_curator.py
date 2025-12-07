"""Testy jednostkowe dla DatasetCurator."""

import json
import tempfile

import pytest

from venom_core.learning.dataset_curator import DatasetCurator, TrainingExample


def test_training_example_alpaca_format():
    """Test konwersji przykładu do formatu Alpaca."""
    example = TrainingExample(
        instruction="Napisz funkcję w Pythonie",
        input_text="Funkcja ma sumować dwie liczby",
        output="def suma(a, b):\n    return a + b",
    )

    alpaca = example.to_alpaca_format()

    assert alpaca["instruction"] == "Napisz funkcję w Pythonie"
    assert alpaca["input"] == "Funkcja ma sumować dwie liczby"
    assert alpaca["output"] == "def suma(a, b):\n    return a + b"


def test_training_example_sharegpt_format():
    """Test konwersji przykładu do formatu ShareGPT."""
    example = TrainingExample(
        instruction="Jesteś asystentem AI",
        input_text="Jak napisać pętlę for?",
        output="W Pythonie: for i in range(10):",
    )

    sharegpt = example.to_sharegpt_format()

    assert "conversations" in sharegpt
    assert len(sharegpt["conversations"]) == 3
    assert sharegpt["conversations"][0]["from"] == "system"
    assert sharegpt["conversations"][1]["from"] == "human"
    assert sharegpt["conversations"][2]["from"] == "gpt"


def test_dataset_curator_initialization():
    """Test inicjalizacji DatasetCurator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        curator = DatasetCurator(output_dir=tmpdir)
        assert curator.output_dir.exists()
        assert len(curator.examples) == 0


def test_dataset_curator_filter_low_quality():
    """Test filtrowania przykładów niskiej jakości."""
    with tempfile.TemporaryDirectory() as tmpdir:
        curator = DatasetCurator(output_dir=tmpdir)

        # Dodaj przykłady
        curator.examples = [
            TrainingExample("inst1", "short", "short"),  # Zbyt krótki
            TrainingExample("inst2", "Valid input text", "Valid output text"),  # OK
            TrainingExample("inst3", "Another valid", "Another output"),  # OK
            TrainingExample("inst4", "Another valid", "Another output"),  # Duplikat
        ]

        removed = curator.filter_low_quality()

        # Powinno usunąć 1 zbyt krótki + 1 duplikat = 2
        assert removed == 2
        assert len(curator.examples) == 2


def test_dataset_curator_save_dataset():
    """Test zapisywania datasetu."""
    with tempfile.TemporaryDirectory() as tmpdir:
        curator = DatasetCurator(output_dir=tmpdir)

        # Dodaj przykłady
        curator.examples = [
            TrainingExample("inst1", "input1", "output1"),
            TrainingExample("inst2", "input2", "output2"),
        ]

        # Zapisz
        output_path = curator.save_dataset(
            filename="test_dataset.jsonl", format="alpaca"
        )

        assert output_path.exists()

        # Sprawdź zawartość
        with open(output_path, "r") as f:
            lines = f.readlines()
            assert len(lines) == 2

            # Sprawdź pierwszy przykład
            data = json.loads(lines[0])
            assert data["instruction"] == "inst1"
            assert data["input"] == "input1"
            assert data["output"] == "output1"


def test_dataset_curator_statistics():
    """Test statystyk datasetu."""
    with tempfile.TemporaryDirectory() as tmpdir:
        curator = DatasetCurator(output_dir=tmpdir)

        # Dodaj przykłady
        curator.examples = [
            TrainingExample(
                "inst1", "input text", "output text", metadata={"source": "lessons"}
            ),
            TrainingExample("inst2", "input2", "output2", metadata={"source": "git"}),
            TrainingExample(
                "inst3", "input3", "output3", metadata={"source": "lessons"}
            ),
        ]

        stats = curator.get_statistics()

        assert stats["total_examples"] == 3
        assert stats["sources"]["lessons"] == 2
        assert stats["sources"]["git"] == 1
        assert "avg_input_length" in stats
        assert "avg_output_length" in stats


def test_dataset_curator_save_empty_raises_error():
    """Test że zapisywanie pustego datasetu rzuca błąd."""
    with tempfile.TemporaryDirectory() as tmpdir:
        curator = DatasetCurator(output_dir=tmpdir)

        with pytest.raises(ValueError, match="Brak przykładów"):
            curator.save_dataset()


def test_dataset_curator_clear():
    """Test czyszczenia przykładów."""
    with tempfile.TemporaryDirectory() as tmpdir:
        curator = DatasetCurator(output_dir=tmpdir)

        # Dodaj przykłady
        curator.examples = [
            TrainingExample("inst1", "input1", "output1"),
            TrainingExample("inst2", "input2", "output2"),
        ]

        assert len(curator.examples) == 2

        # Wyczyść
        curator.clear()

        assert len(curator.examples) == 0
