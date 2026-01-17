"""Testy integracyjne dla Orchestrator z klasyfikacją intencji."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core.intent_manager import IntentManager
from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.utils.llm_runtime import LLMRuntimeInfo


@pytest.fixture
def mock_runtime_info():
    """Mock dla get_active_llm_runtime."""
    return LLMRuntimeInfo(
        provider="local",
        model_name="mock-model",
        endpoint="http://mock",
        service_type="local",
        mode="LOCAL",
        config_hash="abc123456789",
        runtime_id="local@http://mock",
    )


@pytest.fixture(autouse=True)
def patch_runtime(mock_runtime_info):
    """Automatycznie patchuje runtime dla wszystkich testów."""
    with patch(
        "venom_core.core.orchestrator.orchestrator_core.get_active_llm_runtime",
        return_value=mock_runtime_info,
    ):
        with patch(
            "venom_core.core.orchestrator.orchestrator_core.SETTINGS"
        ) as mock_settings:
            mock_settings.LLM_CONFIG_HASH = "abc123456789"
            yield


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
    manager.requires_tool = MagicMock(return_value=False)
    return manager


@pytest.fixture
def mock_task_dispatcher():
    """Fixture dla mockowego TaskDispatcher."""
    from venom_core.core.dispatcher import TaskDispatcher

    dispatcher = MagicMock(spec=TaskDispatcher)
    dispatcher.dispatch = AsyncMock()
    dispatcher.kernel = object()
    # Mock agent_map dla logging
    dispatcher.agent_map = {
        "CODE_GENERATION": MagicMock(__class__=MagicMock(__name__="CoderAgent")),
        "GENERAL_CHAT": MagicMock(__class__=MagicMock(__name__="ChatAgent")),
        "KNOWLEDGE_SEARCH": MagicMock(__class__=MagicMock(__name__="ChatAgent")),
    }
    return dispatcher


@pytest.mark.asyncio
async def test_orchestrator_with_intent_classification(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test że Orchestrator wywołuje klasyfikację intencji."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Mockuj odpowiedź klasyfikacji
    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"
    mock_task_dispatcher.dispatch.return_value = "def hello(): pass"

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
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
    assert "def hello" in task.result or "CODE_GENERATION" in " ".join(task.logs)


@pytest.mark.asyncio
async def test_orchestrator_intent_in_logs(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test że intencja jest zapisywana w logach zadania."""
    state_manager = StateManager(state_file_path=temp_state_file)
    mock_intent_manager.classify_intent.return_value = "KNOWLEDGE_SEARCH"
    mock_task_dispatcher.dispatch.return_value = "RAG to..."

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
    )

    response = await orchestrator.submit_task(TaskRequest(content="Co to jest RAG?"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    # Sprawdź czy w logach jest informacja o intencji
    log_text = " ".join(task.logs)
    assert "Sklasyfikowana intencja: KNOWLEDGE_SEARCH" in log_text


@pytest.mark.asyncio
async def test_orchestrator_different_intents(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test klasyfikacji różnych typów intencji."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Test CODE_GENERATION
    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"
    mock_task_dispatcher.dispatch.return_value = "#!/bin/bash\nls"
    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
    )

    response1 = await orchestrator.submit_task(
        TaskRequest(content="Napisz skrypt w Bash")
    )
    await asyncio.sleep(1)

    task1 = state_manager.get_task(response1.task_id)
    log_text1 = " ".join(task1.logs)
    assert "CODE_GENERATION" in log_text1

    # Test GENERAL_CHAT
    mock_intent_manager.classify_intent.return_value = "GENERAL_CHAT"
    mock_task_dispatcher.dispatch.return_value = "Cześć!"
    response2 = await orchestrator.submit_task(TaskRequest(content="Cześć!"))
    await asyncio.sleep(1)

    task2 = state_manager.get_task(response2.task_id)
    log_text2 = " ".join(task2.logs)
    assert "GENERAL_CHAT" in log_text2

    # Test KNOWLEDGE_SEARCH
    mock_intent_manager.classify_intent.return_value = "KNOWLEDGE_SEARCH"
    mock_task_dispatcher.dispatch.return_value = "GraphRAG to..."
    response3 = await orchestrator.submit_task(TaskRequest(content="Wyjaśnij GraphRAG"))
    await asyncio.sleep(1)

    task3 = state_manager.get_task(response3.task_id)
    log_text3 = " ".join(task3.logs)
    assert "KNOWLEDGE_SEARCH" in log_text3


@pytest.mark.asyncio
async def test_orchestrator_intent_classification_error(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test obsługi błędu podczas klasyfikacji intencji."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Symuluj błąd w klasyfikacji
    mock_intent_manager.classify_intent.side_effect = Exception("LLM error")

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
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
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test że wynik zawiera rzeczywistą pracę agenta."""
    state_manager = StateManager(state_file_path=temp_state_file)
    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"
    mock_task_dispatcher.dispatch.return_value = "def sort_func(): pass"

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
    )

    test_content = "Napisz funkcję sortującą"
    response = await orchestrator.submit_task(TaskRequest(content=test_content))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.COMPLETED
    # Intencja powinna być w logach
    log_text = " ".join(task.logs)
    assert "Sklasyfikowana intencja: CODE_GENERATION" in log_text
    # Wynik powinien zawierać pracę agenta
    assert "sort_func" in task.result


@pytest.mark.asyncio
async def test_orchestrator_perf_prompt_shortcut(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test że prompt testu wydajności omija klasyfikację i dispatch."""
    state_manager = StateManager(state_file_path=temp_state_file)
    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
    )

    response = await orchestrator.submit_task(
        TaskRequest(content="Parallel perf PID 123 #0")
    )
    # Pozwól zadaniu zakończyć się w tle
    await asyncio.sleep(0.2)

    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert "perf pipeline" in (task.result or "").lower()
    mock_intent_manager.classify_intent.assert_not_called()
    mock_task_dispatcher.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_help_request_intent(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test obsługi intencji HELP_REQUEST."""
    state_manager = StateManager(state_file_path=temp_state_file)

    # Mockuj odpowiedź klasyfikacji jako HELP_REQUEST
    mock_intent_manager.classify_intent.return_value = "HELP_REQUEST"

    # Mock agent_map dla _generate_help_response
    mock_task_dispatcher.agent_map = {
        "CODE_GENERATION": MagicMock(__class__=MagicMock(__name__="CoderAgent")),
        "RESEARCH": MagicMock(__class__=MagicMock(__name__="ResearcherAgent")),
        "KNOWLEDGE_SEARCH": MagicMock(__class__=MagicMock(__name__="ProfessorAgent")),
    }

    # Mock kernel z plugins
    mock_kernel = MagicMock()
    mock_kernel.plugins = {
        "FileSkill": MagicMock(),
        "GitSkill": MagicMock(),
        "_InternalSkill": MagicMock(),  # Should be filtered out
    }
    mock_task_dispatcher.kernel = mock_kernel

    # Mock event broadcaster
    mock_broadcaster = AsyncMock()

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
        event_broadcaster=mock_broadcaster,
    )

    response = await orchestrator.submit_task(TaskRequest(content="Co potrafisz?"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    assert task.status == TaskStatus.COMPLETED

    # Sprawdź logi
    log_text = " ".join(task.logs)
    assert "Sklasyfikowana intencja: HELP_REQUEST" in log_text
    assert "Generuję informacje pomocy" in log_text

    # Sprawdź wynik pomocy
    assert task.result is not None
    assert "Venom - System Pomocy" in task.result
    assert "Dostępni Agenci" in task.result


@pytest.mark.asyncio
async def test_orchestrator_help_response_content(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test zawartości odpowiedzi pomocy."""
    state_manager = StateManager(state_file_path=temp_state_file)

    mock_intent_manager.classify_intent.return_value = "HELP_REQUEST"

    # Mock agent_map z różnymi agentami
    mock_task_dispatcher.agent_map = {
        "CODE_GENERATION": MagicMock(__class__=MagicMock(__name__="CoderAgent")),
        "RESEARCH": MagicMock(__class__=MagicMock(__name__="ResearcherAgent")),
        "COMPLEX_PLANNING": MagicMock(__class__=MagicMock(__name__="ArchitectAgent")),
    }

    # Mock kernel z plugins
    mock_kernel = MagicMock()
    mock_kernel.plugins = {
        "FileSkill": MagicMock(),
        "GitSkill": MagicMock(),
        "ResearchSkill": MagicMock(),
    }
    mock_task_dispatcher.kernel = mock_kernel

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
    )

    response = await orchestrator.submit_task(TaskRequest(content="Pomoc"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    result = task.result

    # Sprawdź że odpowiedź zawiera opisy agentów
    assert "Coder" in result
    assert "Researcher" in result
    assert "Architect" in result

    # Sprawdź że odpowiedź zawiera sekcje
    assert "Tryby Pracy" in result
    assert "Umiejętności (Skills)" in result
    assert "Przykłady Użycia" in result

    # Sprawdź że lista pluginów jest wyświetlona
    assert "FileSkill" in result
    assert "GitSkill" in result
    assert "ResearchSkill" in result


@pytest.mark.asyncio
async def test_orchestrator_help_filters_internal_plugins(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test że pomoc filtruje wewnętrzne pluginy."""
    state_manager = StateManager(state_file_path=temp_state_file)

    mock_intent_manager.classify_intent.return_value = "HELP_REQUEST"
    mock_task_dispatcher.agent_map = {}

    # Mock kernel z mieszanką publicznych i prywatnych pluginów
    mock_kernel = MagicMock()
    mock_kernel.plugins = {
        "FileSkill": MagicMock(),  # Publiczny
        "_InternalSkill": MagicMock(),  # Powinien być filtrowany
        "__PrivateSkill": MagicMock(),  # Powinien być filtrowany
        "InternalDebugger": MagicMock(),  # Powinien być filtrowany (zawiera 'internal')
        "GitSkill": MagicMock(),  # Publiczny
    }
    mock_task_dispatcher.kernel = mock_kernel

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
    )

    response = await orchestrator.submit_task(TaskRequest(content="Help"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    result = task.result

    # Sprawdź że publiczne pluginy są wyświetlone
    assert "FileSkill" in result
    assert "GitSkill" in result

    # Sprawdź że prywatne pluginy są filtrowane
    assert "_InternalSkill" not in result
    assert "__PrivateSkill" not in result
    assert "InternalDebugger" not in result


@pytest.mark.asyncio
async def test_orchestrator_help_with_no_plugins(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test pomocy gdy brak dostępnych pluginów."""
    state_manager = StateManager(state_file_path=temp_state_file)

    mock_intent_manager.classify_intent.return_value = "HELP_REQUEST"
    mock_task_dispatcher.agent_map = {"CODE_GENERATION": MagicMock()}

    # Mock kernel bez plugins (None)
    mock_kernel = MagicMock()
    mock_kernel.plugins = None
    mock_task_dispatcher.kernel = mock_kernel

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
    )

    response = await orchestrator.submit_task(TaskRequest(content="Co umiesz?"))
    await asyncio.sleep(1)

    task = state_manager.get_task(response.task_id)
    result = task.result

    # Powinien zawierać podstawową wiadomość
    assert "Podstawowe umiejętności" in result
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_orchestrator_help_broadcasts_widget(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test że pomoc broadcastuje widget pomocy."""
    state_manager = StateManager(state_file_path=temp_state_file)

    mock_intent_manager.classify_intent.return_value = "HELP_REQUEST"
    mock_task_dispatcher.agent_map = {"CODE_GENERATION": MagicMock()}

    mock_kernel = MagicMock()
    mock_kernel.plugins = {"FileSkill": MagicMock()}
    mock_task_dispatcher.kernel = mock_kernel

    # Mock event broadcaster
    mock_broadcaster = AsyncMock()

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
        event_broadcaster=mock_broadcaster,
    )

    await orchestrator.submit_task(TaskRequest(content="Pokaż możliwości"))
    await asyncio.sleep(1)

    # Sprawdź czy widget został broadcastowany
    assert mock_broadcaster.broadcast_event.called

    # Znajdź wywołanie z RENDER_WIDGET
    calls = mock_broadcaster.broadcast_event.call_args_list
    widget_call = None
    for call in calls:
        if call.kwargs.get("event_type") == "RENDER_WIDGET":
            widget_call = call
            break

    assert widget_call is not None
    # Sprawdź strukturę widgetu
    widget_data = widget_call.kwargs.get("data", {})
    assert "widget" in widget_data
    widget = widget_data["widget"]
    assert widget["type"] == "markdown"
    assert "content" in widget["data"]


@pytest.mark.asyncio
async def test_orchestrator_forced_intent_skips_classification(
    temp_state_file, mock_intent_manager, mock_task_dispatcher
):
    """Test że forced_intent omija klasyfikację i wymusza ścieżkę."""
    state_manager = StateManager(state_file_path=temp_state_file)
    mock_task_dispatcher.dispatch.return_value = "Plan wykonany"
    mock_task_dispatcher.agent_map["COMPLEX_PLANNING"] = MagicMock(
        __class__=MagicMock(__name__="ArchitectAgent")
    )

    orchestrator = Orchestrator(
        state_manager=state_manager,
        intent_manager=mock_intent_manager,
        task_dispatcher=mock_task_dispatcher,
    )

    response = await orchestrator.submit_task(
        TaskRequest(content="Zrób plan projektu", forced_intent="COMPLEX_PLANNING")
    )
    await asyncio.sleep(1)

    assert not mock_intent_manager.classify_intent.called
    task = state_manager.get_task(response.task_id)
    log_text = " ".join(task.logs)
    assert "COMPLEX_PLANNING" in log_text
