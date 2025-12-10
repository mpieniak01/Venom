"""Testy jednostkowe dla Knowledge Hygiene Suite (Lab Mode i Pruning)."""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core.models import TaskRequest
from venom_core.memory.lessons_store import Lesson, LessonsStore


class TestLabMode:
    """Testy dla trybu Lab Mode (Memory Freeze)."""

    def test_task_request_default_store_knowledge(self):
        """Test czy domyślnie store_knowledge jest True."""
        request = TaskRequest(content="Test zadanie")
        assert request.store_knowledge is True

    def test_task_request_lab_mode_disabled(self):
        """Test czy można wyłączyć zapisywanie wiedzy."""
        request = TaskRequest(content="Test zadanie", store_knowledge=False)
        assert request.store_knowledge is False

    def test_task_request_lab_mode_explicit_enabled(self):
        """Test jawnego włączenia zapisywania wiedzy."""
        request = TaskRequest(content="Test zadanie", store_knowledge=True)
        assert request.store_knowledge is True


class TestLessonsStorePruning:
    """Testy dla metod pruningowych LessonsStore."""

    @pytest.fixture
    def temp_storage(self):
        """Utworzenie tymczasowego pliku storage dla testów."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        yield temp_path
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()

    @pytest.fixture
    def lessons_store(self, temp_storage):
        """Utworzenie instancji LessonsStore z tymczasowym storage."""
        store = LessonsStore(storage_path=str(temp_storage), auto_save=True)
        return store

    def test_delete_last_n_empty_store(self, lessons_store):
        """Test usuwania z pustego magazynu."""
        deleted = lessons_store.delete_last_n(5)
        assert deleted == 0

    def test_delete_last_n_partial(self, lessons_store):
        """Test usuwania części lekcji."""
        # Dodaj 5 lekcji
        for i in range(5):
            lessons_store.add_lesson(
                situation=f"Sytuacja {i}",
                action=f"Akcja {i}",
                result=f"Wynik {i}",
                feedback=f"Feedback {i}",
            )

        assert len(lessons_store.lessons) == 5

        # Usuń 3 najnowsze
        deleted = lessons_store.delete_last_n(3)
        assert deleted == 3
        assert len(lessons_store.lessons) == 2

    def test_delete_last_n_all(self, lessons_store):
        """Test usuwania wszystkich lekcji."""
        # Dodaj 3 lekcje
        for i in range(3):
            lessons_store.add_lesson(
                situation=f"Sytuacja {i}",
                action=f"Akcja {i}",
                result=f"Wynik {i}",
                feedback=f"Feedback {i}",
            )

        # Usuń więcej niż jest
        deleted = lessons_store.delete_last_n(10)
        assert deleted == 3
        assert len(lessons_store.lessons) == 0

    def test_delete_last_n_zero(self, lessons_store):
        """Test usuwania zero lekcji."""
        lessons_store.add_lesson(
            situation="Test", action="Test", result="Test", feedback="Test"
        )
        deleted = lessons_store.delete_last_n(0)
        assert deleted == 0
        assert len(lessons_store.lessons) == 1

    def test_delete_by_time_range(self, lessons_store):
        """Test usuwania lekcji po zakresie czasu."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Dodaj lekcje z różnymi timestampami
        timestamps = [
            base_time - timedelta(days=2),  # Przed zakresem
            base_time - timedelta(days=1),  # W zakresie
            base_time,  # W zakresie
            base_time + timedelta(days=1),  # W zakresie
            base_time + timedelta(days=2),  # Po zakresie
        ]

        for i, ts in enumerate(timestamps):
            lesson = Lesson(
                situation=f"Sytuacja {i}",
                action=f"Akcja {i}",
                result=f"Wynik {i}",
                feedback=f"Feedback {i}",
                timestamp=ts.isoformat(),
            )
            lessons_store.lessons[lesson.lesson_id] = lesson

        lessons_store.save_lessons()
        assert len(lessons_store.lessons) == 5

        # Usuń lekcje z zakresu
        start = base_time - timedelta(days=1)
        end = base_time + timedelta(days=1)
        deleted = lessons_store.delete_by_time_range(start, end)

        assert deleted == 3
        assert len(lessons_store.lessons) == 2

    def test_delete_by_time_range_swap_dates(self, lessons_store):
        """Test czy zamienianie dat działa poprawnie."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        lesson = Lesson(
            situation="Test",
            action="Test",
            result="Test",
            feedback="Test",
            timestamp=base_time.isoformat(),
        )
        lessons_store.lessons[lesson.lesson_id] = lesson

        # Podaj daty w odwrotnej kolejności
        start = base_time + timedelta(days=1)
        end = base_time - timedelta(days=1)

        deleted = lessons_store.delete_by_time_range(start, end)
        assert deleted == 1  # Powinna zostać usunięta

    def test_delete_by_tag(self, lessons_store):
        """Test usuwania lekcji po tagu."""
        # Dodaj lekcje z różnymi tagami
        lessons_store.add_lesson(
            situation="Test 1",
            action="Action",
            result="Result",
            feedback="Feedback",
            tags=["błąd", "test"],
        )
        lessons_store.add_lesson(
            situation="Test 2",
            action="Action",
            result="Result",
            feedback="Feedback",
            tags=["sukces", "test"],
        )
        lessons_store.add_lesson(
            situation="Test 3",
            action="Action",
            result="Result",
            feedback="Feedback",
            tags=["błąd", "produkcja"],
        )

        assert len(lessons_store.lessons) == 3

        # Usuń lekcje z tagiem "błąd"
        deleted = lessons_store.delete_by_tag("błąd")
        assert deleted == 2
        assert len(lessons_store.lessons) == 1

    def test_delete_by_tag_empty(self, lessons_store):
        """Test usuwania z pustym tagiem."""
        lessons_store.add_lesson(
            situation="Test",
            action="Action",
            result="Result",
            feedback="Feedback",
            tags=["test"],
        )

        deleted = lessons_store.delete_by_tag("")
        assert deleted == 0
        assert len(lessons_store.lessons) == 1

    def test_delete_by_tag_not_found(self, lessons_store):
        """Test usuwania nieistniejącego tagu."""
        lessons_store.add_lesson(
            situation="Test",
            action="Action",
            result="Result",
            feedback="Feedback",
            tags=["test"],
        )

        deleted = lessons_store.delete_by_tag("nieistniejący")
        assert deleted == 0
        assert len(lessons_store.lessons) == 1

    def test_clear_all(self, lessons_store):
        """Test czyszczenia całej bazy."""
        # Dodaj kilka lekcji
        for i in range(5):
            lessons_store.add_lesson(
                situation=f"Sytuacja {i}",
                action=f"Akcja {i}",
                result=f"Wynik {i}",
                feedback=f"Feedback {i}",
            )

        assert len(lessons_store.lessons) == 5

        # Wyczyść wszystko
        success = lessons_store.clear_all()
        assert success is True
        assert len(lessons_store.lessons) == 0

        # Sprawdź czy plik został zaktualizowany
        with open(lessons_store.storage_path, "r") as f:
            data = json.load(f)
            assert data["count"] == 0
            assert len(data["lessons"]) == 0

    def test_pruning_persistence(self, lessons_store, temp_storage):
        """Test czy usunięcia są zapisywane na dysku."""
        # Dodaj lekcje
        for i in range(3):
            lessons_store.add_lesson(
                situation=f"Test {i}",
                action="Action",
                result="Result",
                feedback="Feedback",
            )

        # Usuń jedną
        lessons_store.delete_last_n(1)

        # Stwórz nową instancję - powinna załadować stan z dysku
        new_store = LessonsStore(storage_path=str(temp_storage))
        assert len(new_store.lessons) == 2


class TestOrchestratorLabMode:
    """Testy integracyjne dla Lab Mode w orchestratorze."""

    @pytest.mark.asyncio
    async def test_orchestrator_respects_store_knowledge_flag(self):
        """Test czy orchestrator respektuje flagę store_knowledge."""
        # Ten test wymaga mocków orchestratora - zostawiamy jako placeholder
        # dla pełnej implementacji testów integracyjnych
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
