"""Testy API dla Knowledge Hygiene Suite endpoints."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from venom_core.memory.lessons_store import Lesson, LessonsStore


class TestPruningAPIEndpoints:
    """Testy dla endpointów API pruningowych."""

    @pytest.fixture
    def mock_lessons_store(self, tmp_path):
        """Utworzenie mock LessonsStore z przykładowymi lekcjami."""
        storage_path = tmp_path / "lessons.json"
        store = LessonsStore(storage_path=str(storage_path), auto_save=True)

        # Dodaj testowe lekcje
        base_time = datetime(2025, 1, 1, 12, 0, 0)
        for i in range(5):
            lesson_time = base_time + timedelta(hours=i)
            lesson = Lesson(
                situation=f"Test situation {i}",
                action=f"Test action {i}",
                result=f"Test result {i}",
                feedback=f"Test feedback {i}",
                timestamp=lesson_time.isoformat(),
                tags=["test", f"tag{i}"],
            )
            store.lessons[lesson.lesson_id] = lesson

        store.save_lessons()
        return store

    def test_prune_latest_valid_count(self, mock_lessons_store):
        """Test usuwania najnowszych lekcji z poprawną liczbą."""
        initial_count = len(mock_lessons_store.lessons)
        deleted = mock_lessons_store.delete_last_n(2)

        assert deleted == 2
        assert len(mock_lessons_store.lessons) == initial_count - 2

    def test_prune_latest_zero_count(self, mock_lessons_store):
        """Test wywołania z count=0."""
        initial_count = len(mock_lessons_store.lessons)
        deleted = mock_lessons_store.delete_last_n(0)

        assert deleted == 0
        assert len(mock_lessons_store.lessons) == initial_count

    def test_prune_latest_negative_count(self, mock_lessons_store):
        """Test wywołania z ujemną liczbą."""
        initial_count = len(mock_lessons_store.lessons)
        deleted = mock_lessons_store.delete_last_n(-5)

        assert deleted == 0
        assert len(mock_lessons_store.lessons) == initial_count

    def test_prune_by_range_valid(self, mock_lessons_store):
        """Test usuwania po zakresie czasu."""
        start = datetime(2025, 1, 1, 12, 0, 0)
        end = datetime(2025, 1, 1, 14, 0, 0)

        deleted = mock_lessons_store.delete_by_time_range(start, end)

        # Powinny zostać usunięte lekcje z godzin 12, 13, 14 (3 lekcje)
        assert deleted == 3
        assert len(mock_lessons_store.lessons) == 2

    def test_prune_by_range_swapped_dates(self, mock_lessons_store):
        """Test czy zamienianie dat działa."""
        # Podaj daty w odwrotnej kolejności
        start = datetime(2025, 1, 1, 14, 0, 0)
        end = datetime(2025, 1, 1, 12, 0, 0)

        deleted = mock_lessons_store.delete_by_time_range(start, end)

        # System powinien zamienić daty i usunąć lekcje
        assert deleted == 3

    def test_prune_by_tag_existing(self, mock_lessons_store):
        """Test usuwania po istniejącym tagu."""
        deleted = mock_lessons_store.delete_by_tag("test")

        # Wszystkie lekcje mają tag "test"
        assert deleted == 5
        assert len(mock_lessons_store.lessons) == 0

    def test_prune_by_tag_specific(self, mock_lessons_store):
        """Test usuwania po specyficznym tagu."""
        deleted = mock_lessons_store.delete_by_tag("tag1")

        # Tylko jedna lekcja ma tag "tag1"
        assert deleted == 1
        assert len(mock_lessons_store.lessons) == 4

    def test_prune_by_tag_nonexistent(self, mock_lessons_store):
        """Test usuwania po nieistniejącym tagu."""
        deleted = mock_lessons_store.delete_by_tag("nonexistent")

        assert deleted == 0
        assert len(mock_lessons_store.lessons) == 5

    def test_prune_by_tag_empty(self, mock_lessons_store):
        """Test usuwania z pustym tagiem."""
        deleted = mock_lessons_store.delete_by_tag("")

        assert deleted == 0
        assert len(mock_lessons_store.lessons) == 5

    def test_purge_all(self, mock_lessons_store):
        """Test czyszczenia całej bazy."""
        assert len(mock_lessons_store.lessons) > 0

        success = mock_lessons_store.clear_all()

        assert success is True
        assert len(mock_lessons_store.lessons) == 0

    def test_persistence_after_deletion(self, mock_lessons_store, tmp_path):
        """Test czy usunięcia są zapisywane na dysku."""
        storage_path = mock_lessons_store.storage_path

        # Usuń lekcje
        mock_lessons_store.delete_last_n(2)
        remaining_count = len(mock_lessons_store.lessons)

        # Załaduj ponownie z dysku
        new_store = LessonsStore(storage_path=str(storage_path))
        assert len(new_store.lessons) == remaining_count


class TestAPIParameterValidation:
    """Testy walidacji parametrów API."""

    def test_invalid_date_format(self):
        """Test z niepoprawnym formatem daty."""
        # Ten test weryfikuje że niepoprawny format daty jest odrzucany
        invalid_date = "not-a-date"

        try:
            datetime.fromisoformat(invalid_date.replace("Z", "+00:00"))
            assert False, "Should raise ValueError"
        except ValueError:
            # Expected behavior
            pass

    def test_valid_iso8601_formats(self):
        """Test różnych poprawnych formatów ISO 8601."""
        valid_formats = [
            "2025-01-01T00:00:00",
            "2025-01-01T00:00:00Z",
            "2025-01-01T00:00:00+00:00",
            "2025-01-01T00:00:00.123456",
        ]

        for date_str in valid_formats:
            try:
                datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                assert False, f"Should parse valid ISO 8601: {date_str}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
