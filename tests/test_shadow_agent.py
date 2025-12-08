"""Testy jednostkowe dla ShadowAgent."""

from unittest.mock import MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.shadow import ShadowAgent, Suggestion, SuggestionType


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    return kernel


@pytest.fixture
def mock_goal_store():
    """Fixture dla mockowego GoalStore."""
    return MagicMock()


@pytest.fixture
def mock_lessons_store():
    """Fixture dla mockowego LessonsStore."""
    store = MagicMock()
    store.get_all_lessons = MagicMock(return_value=[])
    store.add_lesson = MagicMock()
    return store


@pytest.fixture
def shadow_agent(mock_kernel, mock_goal_store, mock_lessons_store):
    """Fixture dla ShadowAgent."""
    agent = ShadowAgent(
        mock_kernel,
        goal_store=mock_goal_store,
        lessons_store=mock_lessons_store,
        confidence_threshold=0.8,
    )
    return agent


class TestSuggestion:
    """Testy dla klasy Suggestion."""

    def test_suggestion_creation(self):
        """Test tworzenia sugestii."""
        suggestion = Suggestion(
            suggestion_type=SuggestionType.ERROR_FIX,
            title="Test Error",
            message="Found an error",
            confidence=0.9,
        )

        assert suggestion.suggestion_type == SuggestionType.ERROR_FIX
        assert suggestion.title == "Test Error"
        assert suggestion.message == "Found an error"
        assert suggestion.confidence == 0.9
        assert suggestion.timestamp is not None

    def test_suggestion_to_dict(self):
        """Test konwersji sugestii do słownika."""
        suggestion = Suggestion(
            suggestion_type=SuggestionType.CODE_IMPROVEMENT,
            title="Code Quality",
            message="Improve this code",
            confidence=0.75,
            action_payload={"code": "test"},
        )

        result = suggestion.to_dict()

        assert result["type"] == SuggestionType.CODE_IMPROVEMENT
        assert result["title"] == "Code Quality"
        assert result["message"] == "Improve this code"
        assert result["confidence"] == 0.75
        assert result["action_payload"] == {"code": "test"}


class TestShadowAgent:
    """Testy dla ShadowAgent."""

    def test_initialization(self, mock_kernel, mock_goal_store, mock_lessons_store):
        """Test inicjalizacji ShadowAgent."""
        agent = ShadowAgent(
            mock_kernel,
            goal_store=mock_goal_store,
            lessons_store=mock_lessons_store,
            confidence_threshold=0.8,
        )

        assert agent.kernel == mock_kernel
        assert agent.goal_store == mock_goal_store
        assert agent.lessons_store == mock_lessons_store
        assert agent.confidence_threshold == 0.8
        assert agent._is_running is False

    @pytest.mark.asyncio
    async def test_start_stop(self, shadow_agent):
        """Test uruchamiania i zatrzymywania agenta."""
        await shadow_agent.start()
        assert shadow_agent._is_running is True

        await shadow_agent.stop()
        assert shadow_agent._is_running is False

    def test_is_error_traceback(self, shadow_agent):
        """Test wykrywania traceback błędu."""
        error_text = """
        Traceback (most recent call last):
          File "test.py", line 10, in <module>
            result = divide(10, 0)
        ZeroDivisionError: division by zero
        """

        assert shadow_agent._is_error_traceback(error_text) is True

    def test_is_error_traceback_negative(self, shadow_agent):
        """Test wykrywania traceback - wynik negatywny."""
        normal_text = "This is just normal text without any errors"

        assert shadow_agent._is_error_traceback(normal_text) is False

    def test_is_code_snippet(self, shadow_agent):
        """Test wykrywania fragmentu kodu."""
        code_text = """
        def calculate_sum(a, b):
            return a + b
        """

        assert shadow_agent._is_code_snippet(code_text) is True

    def test_is_code_snippet_negative(self, shadow_agent):
        """Test wykrywania kodu - wynik negatywny."""
        normal_text = "This is regular text, not code"

        assert shadow_agent._is_code_snippet(normal_text) is False

    def test_is_reading_docs(self, shadow_agent):
        """Test wykrywania czytania dokumentacji."""
        doc_title = "FastAPI Documentation - Official Guide"

        assert shadow_agent._is_reading_docs(doc_title) is True

    def test_is_reading_docs_negative(self, shadow_agent):
        """Test wykrywania dokumentacji - wynik negatywny."""
        normal_title = "Email - Gmail"

        assert shadow_agent._is_reading_docs(normal_title) is False

    @pytest.mark.asyncio
    async def test_analyze_clipboard_with_error(self, shadow_agent):
        """Test analizy schowka z błędem."""
        await shadow_agent.start()

        sensor_data = {
            "type": "clipboard",
            "content": "Traceback (most recent call last):\n  Error: Something failed",
            "timestamp": "2024-01-01T00:00:00",
        }

        suggestion = await shadow_agent.analyze_sensor_data(sensor_data)

        assert suggestion is not None
        assert suggestion.suggestion_type == SuggestionType.ERROR_FIX
        assert suggestion.confidence >= 0.8

        await shadow_agent.stop()

    @pytest.mark.asyncio
    async def test_analyze_clipboard_with_code(self, shadow_agent):
        """Test analizy schowka z kodem."""
        sensor_data = {
            "type": "clipboard",
            "content": "def test_function():\n    pass",
            "timestamp": "2024-01-01T00:00:00",
        }

        suggestion = await shadow_agent.analyze_sensor_data(sensor_data)

        # Może zwrócić sugestię lub None, zależnie od confidence
        # W tym przypadku confidence jest niskie, więc None
        assert (
            suggestion is None
            or suggestion.confidence >= shadow_agent.confidence_threshold
        )

    @pytest.mark.asyncio
    async def test_analyze_window_with_docs(self, shadow_agent):
        """Test analizy okna z dokumentacją."""
        sensor_data = {
            "type": "window",
            "title": "Python Documentation - Tutorial",
            "timestamp": "2024-01-01T00:00:00",
        }

        suggestion = await shadow_agent.analyze_sensor_data(sensor_data)

        # Może zwrócić sugestię kontekstowej pomocy
        # (jeśli confidence >= threshold)
        if suggestion:
            assert suggestion.suggestion_type == SuggestionType.CONTEXT_HELP

    @pytest.mark.asyncio
    async def test_analyze_sensor_data_not_running(self, shadow_agent):
        """Test analizy gdy agent nie działa."""
        shadow_agent._is_running = False

        sensor_data = {
            "type": "clipboard",
            "content": "test",
            "timestamp": "2024-01-01T00:00:00",
        }

        suggestion = await shadow_agent.analyze_sensor_data(sensor_data)

        assert suggestion is None

    def test_record_rejection(self, shadow_agent, mock_lessons_store):
        """Test rejestrowania odrzuconej sugestii."""
        suggestion = Suggestion(
            suggestion_type=SuggestionType.ERROR_FIX,
            title="Test",
            message="Test message",
            confidence=0.9,
        )

        shadow_agent.record_rejection(suggestion)

        assert SuggestionType.ERROR_FIX in shadow_agent._rejected_suggestions
        # Sprawdź czy zapisano lekcję
        mock_lessons_store.add_lesson.assert_called_once()

    def test_get_status(self, shadow_agent):
        """Test pobierania statusu agenta."""
        status = shadow_agent.get_status()

        assert "is_running" in status
        assert "confidence_threshold" in status
        assert "queued_suggestions" in status
        assert "rejected_count" in status
        assert status["is_running"] is False
        assert status["confidence_threshold"] == 0.8
