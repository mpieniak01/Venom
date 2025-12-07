"""Testy jednostkowe dla LessonsStore."""

import tempfile
from pathlib import Path

import pytest

from venom_core.memory.lessons_store import Lesson, LessonsStore


@pytest.fixture
def temp_storage_path():
    """Fixture dla tymczasowej ścieżki przechowywania."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "lessons.json")


@pytest.fixture
def lessons_store(temp_storage_path):
    """Fixture dla LessonsStore bez vector store."""
    return LessonsStore(storage_path=temp_storage_path, vector_store=None)


class TestLesson:
    """Testy dla klasy Lesson."""

    def test_lesson_creation(self):
        """Test tworzenia lekcji."""
        lesson = Lesson(
            situation="Próba napisania kodu",
            action="Wygenerowałem kod Python",
            result="SUKCES",
            feedback="Kod działa poprawnie",
            tags=["python", "sukces"],
        )

        assert lesson.lesson_id is not None
        assert lesson.timestamp is not None
        assert lesson.situation == "Próba napisania kodu"
        assert lesson.action == "Wygenerowałem kod Python"
        assert lesson.result == "SUKCES"
        assert lesson.feedback == "Kod działa poprawnie"
        assert "python" in lesson.tags

    def test_lesson_to_dict(self):
        """Test konwersji lekcji do słownika."""
        lesson = Lesson(
            situation="Test", action="Test action", result="OK", feedback="Good"
        )

        data = lesson.to_dict()

        assert isinstance(data, dict)
        assert "lesson_id" in data
        assert "timestamp" in data
        assert "situation" in data
        assert data["situation"] == "Test"

    def test_lesson_from_dict(self):
        """Test tworzenia lekcji ze słownika."""
        data = {
            "lesson_id": "test-123",
            "timestamp": "2024-01-01T00:00:00",
            "situation": "Test situation",
            "action": "Test action",
            "result": "Test result",
            "feedback": "Test feedback",
            "tags": ["test"],
            "metadata": {"key": "value"},
        }

        lesson = Lesson.from_dict(data)

        assert lesson.lesson_id == "test-123"
        assert lesson.situation == "Test situation"
        assert lesson.tags == ["test"]

    def test_lesson_to_text(self):
        """Test konwersji lekcji do tekstu."""
        lesson = Lesson(
            situation="Sytuacja testowa",
            action="Akcja testowa",
            result="Rezultat testowy",
            feedback="Feedback testowy",
            tags=["test", "example"],
        )

        text = lesson.to_text()

        assert "Sytuacja: Sytuacja testowa" in text
        assert "Akcja: Akcja testowa" in text
        assert "Rezultat: Rezultat testowy" in text
        assert "Lekcja: Feedback testowy" in text
        assert "test, example" in text


class TestLessonsStore:
    """Testy dla LessonsStore."""

    def test_initialization(self, lessons_store, temp_storage_path):
        """Test inicjalizacji LessonsStore."""
        assert lessons_store.storage_path == Path(temp_storage_path)
        assert isinstance(lessons_store.lessons, dict)
        assert len(lessons_store.lessons) == 0

    def test_add_lesson(self, lessons_store):
        """Test dodawania lekcji."""
        lesson = lessons_store.add_lesson(
            situation="Test situation",
            action="Test action",
            result="SUKCES",
            feedback="Test feedback",
            tags=["test"],
        )

        assert lesson is not None
        assert lesson.lesson_id in lessons_store.lessons
        assert lesson.situation == "Test situation"

    def test_get_lesson(self, lessons_store):
        """Test pobierania lekcji po ID."""
        lesson = lessons_store.add_lesson(
            situation="Test", action="Test", result="OK", feedback="Good"
        )

        retrieved = lessons_store.get_lesson(lesson.lesson_id)

        assert retrieved is not None
        assert retrieved.lesson_id == lesson.lesson_id
        assert retrieved.situation == lesson.situation

    def test_get_lesson_not_found(self, lessons_store):
        """Test pobierania nieistniejącej lekcji."""
        result = lessons_store.get_lesson("nonexistent-id")
        assert result is None

    def test_get_all_lessons(self, lessons_store):
        """Test pobierania wszystkich lekcji."""
        # Dodaj kilka lekcji
        for i in range(3):
            lessons_store.add_lesson(
                situation=f"Situation {i}",
                action=f"Action {i}",
                result="OK",
                feedback=f"Feedback {i}",
            )

        all_lessons = lessons_store.get_all_lessons()

        assert len(all_lessons) == 3

    def test_get_all_lessons_with_limit(self, lessons_store):
        """Test pobierania lekcji z limitem."""
        # Dodaj kilka lekcji
        for i in range(5):
            lessons_store.add_lesson(
                situation=f"Situation {i}",
                action=f"Action {i}",
                result="OK",
                feedback=f"Feedback {i}",
            )

        limited = lessons_store.get_all_lessons(limit=2)

        assert len(limited) == 2

    def test_get_lessons_by_tags(self, lessons_store):
        """Test pobierania lekcji po tagach."""
        lessons_store.add_lesson(
            situation="Test 1",
            action="Action 1",
            result="OK",
            feedback="Feedback 1",
            tags=["python", "code"],
        )
        lessons_store.add_lesson(
            situation="Test 2",
            action="Action 2",
            result="OK",
            feedback="Feedback 2",
            tags=["javascript", "code"],
        )
        lessons_store.add_lesson(
            situation="Test 3",
            action="Action 3",
            result="OK",
            feedback="Feedback 3",
            tags=["python"],
        )

        python_lessons = lessons_store.get_lessons_by_tags(["python"])

        assert len(python_lessons) == 2

    def test_delete_lesson(self, lessons_store):
        """Test usuwania lekcji."""
        lesson = lessons_store.add_lesson(
            situation="Test", action="Action", result="OK", feedback="Feedback"
        )

        # Usuń lekcję
        deleted = lessons_store.delete_lesson(lesson.lesson_id)

        assert deleted is True
        assert lesson.lesson_id not in lessons_store.lessons

    def test_delete_nonexistent_lesson(self, lessons_store):
        """Test usuwania nieistniejącej lekcji."""
        deleted = lessons_store.delete_lesson("nonexistent-id")
        assert deleted is False

    def test_save_and_load_lessons(self, temp_storage_path):
        """Test zapisywania i ładowania lekcji."""
        # Utwórz store i dodaj lekcje
        store1 = LessonsStore(storage_path=temp_storage_path)
        store1.add_lesson(
            situation="Test", action="Action", result="OK", feedback="Feedback"
        )
        store1.add_lesson(
            situation="Test 2", action="Action 2", result="OK", feedback="Feedback 2"
        )

        lesson_count = len(store1.lessons)

        # Utwórz nowy store i załaduj
        store2 = LessonsStore(storage_path=temp_storage_path)

        assert len(store2.lessons) == lesson_count

    def test_get_statistics(self, lessons_store):
        """Test pobierania statystyk."""
        # Dodaj kilka lekcji z tagami
        lessons_store.add_lesson(
            situation="Test 1",
            action="Action",
            result="OK",
            feedback="Feedback",
            tags=["python", "code"],
        )
        lessons_store.add_lesson(
            situation="Test 2",
            action="Action",
            result="OK",
            feedback="Feedback",
            tags=["python"],
        )
        lessons_store.add_lesson(
            situation="Test 3",
            action="Action",
            result="OK",
            feedback="Feedback",
            tags=["javascript"],
        )

        stats = lessons_store.get_statistics()

        assert stats["total_lessons"] == 3
        assert stats["unique_tags"] > 0
        assert "tag_distribution" in stats
        assert stats["tag_distribution"]["python"] == 2

    def test_search_lessons_without_vector_store(self, lessons_store):
        """Test wyszukiwania lekcji bez vector store."""
        # Dodaj lekcje
        lessons_store.add_lesson(
            situation="Test", action="Action", result="OK", feedback="Feedback"
        )

        # Wyszukiwanie powinno zwrócić pustą listę (brak vector store)
        results = lessons_store.search_lessons("test query")

        assert isinstance(results, list)
        assert len(results) == 0
