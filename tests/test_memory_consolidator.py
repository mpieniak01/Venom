"""Testy jednostkowe dla MemoryConsolidator."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.services.memory_service import MemoryConsolidator


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    return kernel


@pytest.fixture
def consolidator(mock_kernel):
    """Fixture dla MemoryConsolidator."""
    return MemoryConsolidator(mock_kernel)


def test_consolidator_initialization(mock_kernel):
    """Test inicjalizacji MemoryConsolidator."""
    consolidator = MemoryConsolidator(mock_kernel)
    assert consolidator.kernel == mock_kernel


def test_filter_sensitive_data_passwords(consolidator):
    """Test filtrowania haseł."""
    text = "User logged in with password: EXAMPLE_SECRET_123"
    filtered = consolidator._filter_sensitive_data(text)
    assert "[FILTERED]" in filtered
    assert "EXAMPLE_SECRET_123" not in filtered


def test_filter_sensitive_data_api_keys(consolidator):
    """Test filtrowania kluczy API."""
    text = "Using api_key=FAKE_API_KEY_1234567890"
    filtered = consolidator._filter_sensitive_data(text)
    assert "[FILTERED]" in filtered
    assert "FAKE_API_KEY_1234567890" not in filtered


def test_filter_sensitive_data_tokens(consolidator):
    """Test filtrowania tokenów."""
    text = "Authorization token: EXAMPLE_JWT_TOKEN_FOR_TESTING"
    filtered = consolidator._filter_sensitive_data(text)
    assert "[FILTERED]" in filtered


def test_filter_sensitive_data_multiple_patterns(consolidator):
    """Test filtrowania wielu wzorców wrażliwych danych."""
    text = "password=EXAMPLE_PASS and api_key=FAKE_KEY_123 and token=TEST_TOKEN_789"
    filtered = consolidator._filter_sensitive_data(text)
    assert "EXAMPLE_PASS" not in filtered
    assert "FAKE_KEY_123" not in filtered
    assert "TEST_TOKEN_789" not in filtered
    assert "[FILTERED]" in filtered


def test_filter_sensitive_data_normal_text(consolidator):
    """Test że normalny tekst pozostaje niezmieniony."""
    text = "User completed task: create new file main.py"
    filtered = consolidator._filter_sensitive_data(text)
    assert filtered == text


@pytest.mark.asyncio
async def test_consolidate_empty_logs(consolidator):
    """Test konsolidacji pustej listy logów."""
    logs = []
    result = await consolidator.consolidate_daily_logs(logs)

    assert result["summary"] == "Brak aktywności"
    assert result["lessons"] == []


@pytest.mark.asyncio
async def test_consolidate_daily_logs_success(consolidator, mock_kernel):
    """Test pomyślnej konsolidacji logów."""
    logs = [
        "User created file main.py",
        "User edited config.yaml",
        "System detected dependency: main.py requires utils.py",
    ]

    # Mock LLM response
    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = (
        lambda self: """PODSUMOWANIE:
Użytkownik stworzył nowy plik i edytował konfigurację. System wykrył zależności między plikami.

LEKCJE:
1. Plik main.py wymaga utils.py
2. Użytkownik pracuje nad konfiguracją systemu
3. System może automatycznie wykrywać zależności"""
    )
    mock_service.get_chat_message_content = AsyncMock(return_value=mock_response)
    mock_kernel.get_service = MagicMock(return_value=mock_service)

    result = await consolidator.consolidate_daily_logs(logs)

    assert "summary" in result
    assert "lessons" in result
    assert len(result["summary"]) > 0
    assert len(result["lessons"]) > 0
    assert "Plik main.py wymaga utils.py" in result["lessons"]


@pytest.mark.asyncio
async def test_consolidate_daily_logs_with_sensitive_data(consolidator, mock_kernel):
    """Test że wrażliwe dane są filtrowane przed wysłaniem do LLM."""
    logs = [
        "User logged in with password: EXAMPLE_SECRET_123",
        "API key configured: FAKE_API_KEY_TEST",
        "User created file test.py",
    ]

    # Mock LLM response
    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = (
        lambda self: """PODSUMOWANIE:
Użytkownik zalogował się i skonfigurował system.

LEKCJE:
1. Konfiguracja jest kluczowa"""
    )
    mock_service.get_chat_message_content = AsyncMock(return_value=mock_response)
    mock_kernel.get_service = MagicMock(return_value=mock_service)

    await consolidator.consolidate_daily_logs(logs)

    # Sprawdź że wywołano LLM
    mock_service.get_chat_message_content.assert_called_once()

    # Sprawdź że prompt nie zawiera wrażliwych danych
    call_args = mock_service.get_chat_message_content.call_args
    chat_history = call_args.kwargs["chat_history"]
    messages = chat_history.messages
    prompt_content = messages[0].content

    assert "EXAMPLE_SECRET_123" not in prompt_content
    assert "FAKE_API_KEY_TEST" not in prompt_content
    assert "[FILTERED]" in prompt_content


@pytest.mark.asyncio
async def test_consolidate_daily_logs_llm_error_fallback(consolidator, mock_kernel):
    """Test fallback gdy LLM zawiedzie."""
    logs = ["User did something", "System processed task"]

    # Mock LLM który rzuca błąd
    mock_service = MagicMock()
    mock_service.get_chat_message_content = AsyncMock(
        side_effect=Exception("LLM Error")
    )
    mock_kernel.get_service = MagicMock(return_value=mock_service)

    result = await consolidator.consolidate_daily_logs(logs)

    # Powinien zwrócić fallback
    assert "summary" in result
    assert "lessons" in result
    assert "Wykonano 2 akcji w systemie" in result["summary"]
    assert "Nieudana konsolidacja" in result["lessons"][0]


def test_parse_consolidation_response_proper_format(consolidator):
    """Test parsowania poprawnie sformatowanej odpowiedzi."""
    response = """PODSUMOWANIE:
System wykonał wiele zadań i nauczył się nowych wzorców.

LEKCJE:
1. Plik X jest zależny od Y
2. Użytkownik preferuje format JSON
3. Testy powinny być uruchamiane automatycznie"""

    summary, lessons = consolidator._parse_consolidation_response(response)

    assert len(summary) > 0
    assert "System wykonał wiele zadań" in summary
    assert len(lessons) == 3
    assert "Plik X jest zależny od Y" in lessons
    assert "Użytkownik preferuje format JSON" in lessons


def test_parse_consolidation_response_no_sections(consolidator):
    """Test parsowania odpowiedzi bez sekcji."""
    response = "Just a plain text response without structure"

    summary, lessons = consolidator._parse_consolidation_response(response)

    # Powinien użyć fallback
    assert len(summary) > 0
    assert summary == response[:200]


def test_parse_consolidation_response_only_summary(consolidator):
    """Test parsowania odpowiedzi tylko z podsumowaniem."""
    response = """PODSUMOWANIE:
To jest podsumowanie bez lekcji."""

    summary, lessons = consolidator._parse_consolidation_response(response)

    assert "To jest podsumowanie" in summary
    # Lekcje mogą być puste lub fallback
    assert isinstance(lessons, list)


def test_parse_consolidation_response_different_numbering(consolidator):
    """Test parsowania różnych formatów numeracji lekcji."""
    response = """PODSUMOWANIE:
Summary text

LEKCJE:
1. Lekcja pierwsza
2. Lekcja druga
3. Lekcja trzecia"""

    summary, lessons = consolidator._parse_consolidation_response(response)

    assert len(lessons) == 3
    assert "Lekcja pierwsza" in lessons
    assert "Lekcja druga" in lessons
    assert "Lekcja trzecia" in lessons


@pytest.mark.asyncio
async def test_consolidate_integration_with_real_logs(consolidator, mock_kernel):
    """Test integracyjny z realistycznymi logami."""
    logs = [
        "2024-12-09 10:00: User requested code generation for utils.py",
        "2024-12-09 10:05: System created file utils.py with helper functions",
        "2024-12-09 10:10: User asked to refactor main.py",
        "2024-12-09 10:15: System refactored main.py, extracted 3 functions",
        "2024-12-09 10:20: Tests passed successfully",
    ]

    # Mock realistic LLM response
    mock_service = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = (
        lambda self: """PODSUMOWANIE:
Dzisiaj użytkownik pracował nad refaktoryzacją kodu. Stworzono nowy plik utils.py
z funkcjami pomocniczymi i zrefaktoryzowano main.py. Wszystkie testy przeszły pomyślnie.

LEKCJE:
1. Ekstrakcja funkcji poprawia czytelność kodu
2. Testy są kluczowe dla bezpieczeństwa refaktoryzacji
3. Funkcje pomocnicze powinny być w osobnym module utils
4. Użytkownik preferuje małe, skoncentrowane funkcje"""
    )
    mock_service.get_chat_message_content = AsyncMock(return_value=mock_response)
    mock_kernel.get_service = MagicMock(return_value=mock_service)

    result = await consolidator.consolidate_daily_logs(logs)

    assert "refaktoryzacją" in result["summary"]
    assert len(result["lessons"]) >= 3
    assert any("utils" in lesson.lower() for lesson in result["lessons"])
