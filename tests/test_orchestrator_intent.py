"""Testy integracyjne dla Orchestrator z klasyfikacją intencji."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.core.intent_manager import IntentManager
from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager


@pytest.fixture
def temp_state_file():
    """Fixture dla tymczasowego pliku stanu."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def mock_intent_manager():
    """Fixture dla mockowego IntentManager."""
    manager = MagicMock(spec=IntentManager)
    manager.classify_intent = AsyncMock()
    return manager


@pytest.mark.asyncio
async def test_orchestrator_with_intent_classification(
    temp_state_file, mock_intent_manager
):
    """Test że Orchestrator wywołuje klasyfikację intencji."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Mockuj odpowiedź klasyfikacji
    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"

    orchestrator = Orchestrator(
        state_manager=state_manager, intent_manager=mock_intent_manager
    )

    # Utwórz zadanie
    response = await orchestrator.submit_task(
        TaskRequest(content="Napisz funkcję w Pythonie")
    )

    # Poczekaj na zakończenie zadania
    await asyncio.sleep(1)

    # Sprawdź czy klasyfikacja została wywołana
    assert mock_intent_manager.classify_intent.called
    mock_intent_manager.classify_intent.assert_called_with("Napisz funkcję w Pythonie")

    # Sprawdź status zadania
    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert "CODE_GENERATION" in task.result


@pytest.mark.asyncio
async def test_orchestrator_intent_in_logs(temp_state_file, mock_intent_manager):
    """Test że intencja jest zapisywana w logach zadania."""
    state_manager = StateManager(state_file_path=temp_state_file)
    mock_intent_manager.classify_intent.return_value = "KNOWLEDGE_SEARCH"

    orchestrator = Orchestrator(
        state_manager=state_manager, intent_manager=mock_intent_manager
    )

    response = await orchestrator.submit_task(TaskRequest(content="Co to jest RAG?"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    # Sprawdź czy w logach jest informacja o intencji
    log_text = " ".join(task.logs)
    assert "Sklasyfikowana intencja: KNOWLEDGE_SEARCH" in log_text


@pytest.mark.asyncio
async def test_orchestrator_different_intents(temp_state_file, mock_intent_manager):
    """Test klasyfikacji różnych typów intencji."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Test CODE_GENERATION
    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"
    orchestrator = Orchestrator(
        state_manager=state_manager, intent_manager=mock_intent_manager
    )

    response1 = await orchestrator.submit_task(
        TaskRequest(content="Napisz skrypt w Bash")
    )
    await asyncio.sleep(1)

    task1 = state_manager.get_task(response1.task_id)
    assert "CODE_GENERATION" in task1.result

    # Test GENERAL_CHAT
    mock_intent_manager.classify_intent.return_value = "GENERAL_CHAT"
    response2 = await orchestrator.submit_task(TaskRequest(content="Cześć!"))
    await asyncio.sleep(1)

    task2 = state_manager.get_task(response2.task_id)
    assert "GENERAL_CHAT" in task2.result

    # Test KNOWLEDGE_SEARCH
    mock_intent_manager.classify_intent.return_value = "KNOWLEDGE_SEARCH"
    response3 = await orchestrator.submit_task(
        TaskRequest(content="Wyjaśnij GraphRAG")
    )
    await asyncio.sleep(1)

    task3 = state_manager.get_task(response3.task_id)
    assert "KNOWLEDGE_SEARCH" in task3.result


@pytest.mark.asyncio
async def test_orchestrator_intent_classification_error(
    temp_state_file, mock_intent_manager
):
    """Test obsługi błędu podczas klasyfikacji intencji."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Symuluj błąd w klasyfikacji
    mock_intent_manager.classify_intent.side_effect = Exception("LLM error")

    orchestrator = Orchestrator(
        state_manager=state_manager, intent_manager=mock_intent_manager
    )

    response = await orchestrator.submit_task(TaskRequest(content="Test content"))
    await asyncio.sleep(1)

    # Zadanie powinno być FAILED
    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.FAILED
    assert "Błąd" in task.result


@pytest.mark.asyncio
async def test_orchestrator_creates_default_intent_manager(temp_state_file):
    """Test że Orchestrator tworzy domyślny IntentManager jeśli nie przekazano."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Nie przekazuj intent_manager - powinien utworzyć własny
    orchestrator = Orchestrator(state_manager=state_manager)

    assert orchestrator.intent_manager is not None
    assert isinstance(orchestrator.intent_manager, IntentManager)


@pytest.mark.asyncio
async def test_orchestrator_result_contains_intent_and_content(
    temp_state_file, mock_intent_manager
):
    """Test że wynik zawiera zarówno intencję jak i oryginalną treść."""
    state_manager = StateManager(state_file_path=temp_state_file)
    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"

    orchestrator = Orchestrator(
        state_manager=state_manager, intent_manager=mock_intent_manager
    )

    test_content = "Napisz funkcję sortującą"
    response = await orchestrator.submit_task(TaskRequest(content=test_content))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert "Intencja: CODE_GENERATION" in task.result
    assert test_content in task.result
