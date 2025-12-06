"""Testy integracyjne dla Motor Cortex - rzeczywiste wykonywanie zadań."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.core.dispatcher import TaskDispatcher
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
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def mock_intent_manager():
    """Fixture dla mockowego IntentManager."""
    manager = MagicMock(spec=IntentManager)
    manager.classify_intent = AsyncMock()
    return manager


@pytest.fixture
def mock_dispatcher():
    """Fixture dla mockowego TaskDispatcher."""
    dispatcher = MagicMock(spec=TaskDispatcher)
    dispatcher.dispatch = AsyncMock()
    dispatcher.agent_map = {
        "CODE_GENERATION": MagicMock(__class__=MagicMock(__name__="CoderAgent")),
        "GENERAL_CHAT": MagicMock(__class__=MagicMock(__name__="ChatAgent")),
        "KNOWLEDGE_SEARCH": MagicMock(__class__=MagicMock(__name__="ChatAgent")),
    }
    return dispatcher


@pytest.mark.asyncio
async def test_orchestrator_executes_code_generation_task(
    temp_state_file, mock_intent_manager, mock_dispatcher
):
    """Test rzeczywistego wykonywania zadania CODE_GENERATION."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Mockuj klasyfikację i generowanie kodu
    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"
    mock_dispatcher.dispatch.return_value = '```python\ndef hello_world():\n    """Wyświetla Hello World."""\n    print("Hello World")\n```'

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_dispatcher,
    )

    # Wyślij zadanie
    response = await orchestrator.submit_task(
        TaskRequest(content="Napisz funkcję Hello World w Python")
    )

    # Poczekaj na zakończenie
    await asyncio.sleep(1)

    # Sprawdź wynik
    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert "hello_world" in task.result
    assert "print" in task.result
    assert "Hello World" in task.result

    # Sprawdź czy dispatcher został wywołany
    mock_dispatcher.dispatch.assert_called_once_with(
        "CODE_GENERATION", "Napisz funkcję Hello World w Python"
    )


@pytest.mark.asyncio
async def test_orchestrator_executes_general_chat_task(
    temp_state_file, mock_intent_manager, mock_dispatcher
):
    """Test rzeczywistego wykonywania zadania GENERAL_CHAT."""
    state_manager = StateManager(state_file_path=temp_state_file)

    mock_intent_manager.classify_intent.return_value = "GENERAL_CHAT"
    mock_dispatcher.dispatch.return_value = (
        "Dlaczego programiści wolą ciemny motyw? Bo światło przyciąga błędy! 😄"
    )

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_dispatcher,
    )

    response = await orchestrator.submit_task(TaskRequest(content="Opowiedz kawał"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert len(task.result) > 0
    # Wynik powinien zawierać treść kawału
    assert "programiści" in task.result or "błędy" in task.result


@pytest.mark.asyncio
async def test_orchestrator_executes_knowledge_search_task(
    temp_state_file, mock_intent_manager, mock_dispatcher
):
    """Test rzeczywistego wykonywania zadania KNOWLEDGE_SEARCH."""
    state_manager = StateManager(state_file_path=temp_state_file)

    mock_intent_manager.classify_intent.return_value = "KNOWLEDGE_SEARCH"
    mock_dispatcher.dispatch.return_value = (
        "GraphRAG to system łączący grafy wiedzy z Retrieval-Augmented Generation."
    )

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_dispatcher,
    )

    response = await orchestrator.submit_task(
        TaskRequest(content="Co to jest GraphRAG?")
    )
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert len(task.result) > 0
    # Nie powinno być już tylko "Intencja: ..." ale rzeczywista odpowiedź
    assert "GraphRAG" in task.result


@pytest.mark.asyncio
async def test_orchestrator_logs_agent_information(
    temp_state_file, mock_intent_manager, mock_dispatcher
):
    """Test logowania informacji o agencie przetwarzającym zadanie."""
    state_manager = StateManager(state_file_path=temp_state_file)

    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"
    mock_dispatcher.dispatch.return_value = "```python\nprint('test')\n```"

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_dispatcher,
    )

    response = await orchestrator.submit_task(TaskRequest(content="Napisz kod"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    log_text = " ".join(task.logs)

    # Sprawdź czy w logach jest informacja o agencie
    assert "CoderAgent" in log_text or "przetworzył zadanie" in log_text


@pytest.mark.asyncio
async def test_orchestrator_handles_dispatcher_error(
    temp_state_file, mock_intent_manager, mock_dispatcher
):
    """Test obsługi błędu z dispatchera."""
    state_manager = StateManager(state_file_path=temp_state_file)

    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"
    mock_dispatcher.dispatch.side_effect = Exception("Dispatcher error")

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_dispatcher,
    )

    response = await orchestrator.submit_task(TaskRequest(content="Napisz kod"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.FAILED
    assert "Błąd" in task.result


@pytest.mark.asyncio
async def test_orchestrator_result_is_not_just_intent(
    temp_state_file, mock_intent_manager, mock_dispatcher
):
    """Test że wynik to nie tylko nazwa intencji, ale rzeczywista praca."""
    state_manager = StateManager(state_file_path=temp_state_file)

    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"
    mock_dispatcher.dispatch.return_value = "def test(): pass"

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_dispatcher,
    )

    response = await orchestrator.submit_task(TaskRequest(content="Test"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)

    # Stary format wyglądał tak: "Intencja: CODE_GENERATION | Treść: Test"
    # Nowy format powinien zawierać rzeczywistą pracę agenta
    assert task.result == "def test(): pass"
    assert "Intencja: CODE_GENERATION | Treść:" not in task.result


@pytest.mark.asyncio
async def test_orchestrator_processes_multiple_tasks_in_parallel(
    temp_state_file, mock_intent_manager, mock_dispatcher
):
    """Test przetwarzania wielu zadań równolegle."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Różne intencje i wyniki
    intents_and_results = [
        ("CODE_GENERATION", "def func1(): pass"),
        ("GENERAL_CHAT", "Odpowiedź 1"),
        ("CODE_GENERATION", "def func2(): pass"),
        ("KNOWLEDGE_SEARCH", "Wiedza 1"),
    ]

    call_count = 0

    async def mock_classify(content):
        nonlocal call_count
        intent = intents_and_results[call_count % len(intents_and_results)][0]
        call_count += 1
        return intent

    async def mock_dispatch_func(intent, content):
        for i, r in intents_and_results:
            if i == intent:
                return r
        return "Default result"

    mock_intent_manager.classify_intent.side_effect = mock_classify
    mock_dispatcher.dispatch.side_effect = mock_dispatch_func

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_dispatcher,
    )

    # Wyślij wiele zadań
    responses = []
    for i in range(4):
        response = await orchestrator.submit_task(TaskRequest(content=f"Zadanie {i}"))
        responses.append(response)

    # Poczekaj na zakończenie wszystkich
    await asyncio.sleep(2)

    # Sprawdź czy wszystkie zakończone
    for response in responses:
        task = state_manager.get_task(response.task_id)
        assert task.status == TaskStatus.COMPLETED
        assert len(task.result) > 0
