"""Testy integracyjne dla pętli Coder-Critic w Orchestratorze."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tests.helpers.url_fixtures import MOCK_HTTP, local_runtime_id
from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.orchestrator import MAX_REPAIR_ATTEMPTS, Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.utils.llm_runtime import LLMRuntimeInfo


@pytest.fixture
def mock_runtime_info():
    """Mock dla get_active_llm_runtime."""
    return LLMRuntimeInfo(
        provider="local",
        model_name="mock-model",
        endpoint=MOCK_HTTP,
        service_type="local",
        mode="LOCAL",
        config_hash="abc123456789",
        runtime_id=local_runtime_id(MOCK_HTTP),
    )


@pytest.fixture(autouse=True)
def patch_runtime(mock_runtime_info):
    """Automatycznie patchuje runtime dla wszystkich testów."""
    with (
        patch(
            "venom_core.utils.llm_runtime.get_active_llm_runtime",
            return_value=mock_runtime_info,
        ),
    ):
        with (
            patch("venom_core.config.SETTINGS") as mock_settings,
            patch(
                "venom_core.core.orchestrator.orchestrator_dispatch.SETTINGS",
                new=mock_settings,
            ),
        ):
            mock_settings.LLM_CONFIG_HASH = "abc123456789"
            yield


@pytest.fixture
def mock_state_manager():
    """Fixture dla mockowego StateManager."""
    manager = MagicMock(spec=StateManager)
    manager.create_task = MagicMock()
    manager.get_task = MagicMock()
    manager.add_log = MagicMock()
    manager.update_status = AsyncMock()
    return manager


@pytest.fixture
def mock_intent_manager():
    """Fixture dla mockowego IntentManager."""
    manager = MagicMock()
    manager.classify_intent = AsyncMock()
    return manager


@pytest.fixture
def mock_dispatcher():
    """Fixture dla mockowego TaskDispatcher."""
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock()
    dispatcher.coder_agent = MagicMock()
    dispatcher.coder_agent.process = AsyncMock()
    dispatcher.critic_agent = MagicMock()
    dispatcher.critic_agent.process = AsyncMock()
    dispatcher.agent_map = {}
    return dispatcher


@pytest.fixture
def mock_eyes():
    """Fixture dla mockowych Eyes."""
    eyes = MagicMock()
    eyes.analyze_image = AsyncMock()
    return eyes


# --- Testy pętli Coder-Critic ---


@pytest.mark.asyncio
async def test_coder_critic_loop_approval_first_attempt(
    mock_state_manager, mock_intent_manager, mock_dispatcher
):
    """Test zatwierdzenia kodu w pierwszej próbie."""
    # Setup
    orchestrator = Orchestrator(
        mock_state_manager, mock_intent_manager, mock_dispatcher
    )

    task_id = uuid4()
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.content = "Napisz funkcję hello world"
    mock_state_manager.get_task.return_value = mock_task

    # Mock klasyfikacji intencji jako CODE_GENERATION
    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"

    # Mock Coder generuje kod
    generated_code = '''
def hello_world():
    """Wyświetla Hello World."""
    print("Hello World")
'''
    mock_dispatcher.coder_agent.process.return_value = generated_code

    # Mock Critic zatwierdza kod
    mock_dispatcher.critic_agent.process.return_value = "APPROVED"

    # Execute
    request = TaskRequest(content="Napisz funkcję hello world")
    result = await orchestrator._code_generation_with_review(task_id, request.content)

    # Assert
    assert "hello_world" in result
    assert mock_dispatcher.coder_agent.process.call_count == 1
    assert mock_dispatcher.critic_agent.process.call_count == 1
    # Sprawdź czy zalogowano zatwierdzenie
    log_calls = [call[0][1] for call in mock_state_manager.add_log.call_args_list]
    assert any("ZAAKCEPTOWAŁ" in log for log in log_calls)


@pytest.mark.asyncio
async def test_coder_critic_loop_rejection_then_approval(
    mock_state_manager, mock_intent_manager, mock_dispatcher
):
    """Test odrzucenia kodu, naprawy i zatwierdzenia."""
    # Setup
    orchestrator = Orchestrator(
        mock_state_manager, mock_intent_manager, mock_dispatcher
    )

    task_id = uuid4()
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.content = "Napisz funkcję do połączenia z API"
    mock_state_manager.get_task.return_value = mock_task

    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"

    # Mock Coder - pierwsza próba (z hardcoded key)
    bad_code = """
def connect_api():
    api_key = "sk-proj-bad123456789012345678901234"
    return api_key
"""
    # Mock Coder - druga próba (poprawiona)
    good_code = '''
import os

def connect_api():
    """Łączy się z API."""
    api_key = os.getenv("API_KEY")
    return api_key
'''

    mock_dispatcher.coder_agent.process.side_effect = [bad_code, good_code]

    # Mock Critic - pierwsza próba odrzuca, druga zatwierdza
    mock_dispatcher.critic_agent.process.side_effect = [
        "ODRZUCONO - hardcoded credentials",
        "APPROVED",
    ]

    # Execute
    result = await orchestrator._code_generation_with_review(task_id, mock_task.content)

    # Assert
    assert "os.getenv" in result
    assert mock_dispatcher.coder_agent.process.call_count == 2
    assert mock_dispatcher.critic_agent.process.call_count == 2

    # Sprawdź logi
    log_calls = [call[0][1] for call in mock_state_manager.add_log.call_args_list]
    assert any("Próba 1" in log for log in log_calls)
    assert any("Próba 2" in log for log in log_calls)
    assert any("naprawa" in log.lower() for log in log_calls)
    assert any("ZAAKCEPTOWAŁ" in log for log in log_calls)


@pytest.mark.asyncio
async def test_coder_critic_loop_max_attempts_exceeded(
    mock_state_manager, mock_intent_manager, mock_dispatcher
):
    """Test wyczerpania limitu prób naprawy."""
    # Setup
    orchestrator = Orchestrator(
        mock_state_manager, mock_intent_manager, mock_dispatcher
    )

    task_id = uuid4()
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.content = "Napisz funkcję"
    mock_state_manager.get_task.return_value = mock_task

    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"

    # Mock Coder - zawsze zwraca zły kod
    bad_code = "api_key = 'sk-proj-bad123456789012345678901234'"
    mock_dispatcher.coder_agent.process.return_value = bad_code

    # Mock Critic - zawsze odrzuca
    mock_dispatcher.critic_agent.process.return_value = (
        "ODRZUCONO - hardcoded credentials"
    )

    # Execute
    result = await orchestrator._code_generation_with_review(task_id, mock_task.content)

    # Assert
    assert "OSTRZEŻENIE" in result
    assert "UWAGI KRYTYKA" in result
    # Powinno być MAX_REPAIR_ATTEMPTS + 1 wywołań Codera (pierwsza próba + naprawy)
    assert mock_dispatcher.coder_agent.process.call_count == MAX_REPAIR_ATTEMPTS + 1
    assert mock_dispatcher.critic_agent.process.call_count == MAX_REPAIR_ATTEMPTS + 1

    # Sprawdź logi
    log_calls = [call[0][1] for call in mock_state_manager.add_log.call_args_list]
    assert any("Wyczerpano limit" in log for log in log_calls)


@pytest.mark.asyncio
async def test_non_code_generation_bypasses_critic(
    mock_state_manager, mock_intent_manager, mock_dispatcher
):
    """Test że inne intencje omijają pętlę Coder-Critic."""
    # Setup
    orchestrator = Orchestrator(
        mock_state_manager, mock_intent_manager, mock_dispatcher
    )

    task_id = uuid4()
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.content = "Cześć, jak się masz?"
    mock_state_manager.get_task.return_value = mock_task

    # Mock klasyfikacji jako GENERAL_CHAT
    mock_intent_manager.classify_intent.return_value = "GENERAL_CHAT"
    mock_dispatcher.dispatch.return_value = "Cześć! Świetnie, dziękuję!"

    # Execute
    request = TaskRequest(content=mock_task.content)
    await orchestrator._run_task(task_id, request)

    # Assert
    # Dispatcher został wywołany zamiast pętli Coder-Critic
    assert mock_dispatcher.dispatch.called
    assert not mock_dispatcher.critic_agent.process.called


# --- Testy obsługi obrazów ---


@pytest.mark.asyncio
async def test_prepare_context_with_images(mock_state_manager):
    """Test przygotowania kontekstu z obrazami."""
    orchestrator = Orchestrator(mock_state_manager)

    # Mock Eyes
    orchestrator.eyes.analyze_image = AsyncMock(
        return_value="Na obrazie widać błąd: TypeError na linii 42"
    )

    task_id = uuid4()
    request = TaskRequest(
        content="Napraw ten błąd",
        images=["base64encodedimage123"],
    )

    # Execute
    context = await orchestrator._prepare_context(task_id, request)

    # Assert
    assert "Napraw ten błąd" in context
    assert "[OBRAZ 1]" in context
    assert "TypeError" in context
    assert "linii 42" in context
    orchestrator.eyes.analyze_image.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_context_multiple_images(mock_state_manager):
    """Test przygotowania kontekstu z wieloma obrazami."""
    orchestrator = Orchestrator(mock_state_manager)

    # Mock Eyes - różne opisy dla różnych obrazów
    orchestrator.eyes.analyze_image = AsyncMock(
        side_effect=[
            "Obraz 1: Błąd kompilacji",
            "Obraz 2: Stack trace z NullPointerException",
        ]
    )

    task_id = uuid4()
    request = TaskRequest(
        content="Diagnozuj problem",
        images=["image1_base64", "image2_base64"],
    )

    # Execute
    context = await orchestrator._prepare_context(task_id, request)

    # Assert
    assert "[OBRAZ 1]" in context
    assert "[OBRAZ 2]" in context
    assert "Błąd kompilacji" in context
    assert "NullPointerException" in context
    assert orchestrator.eyes.analyze_image.call_count == 2


@pytest.mark.asyncio
async def test_prepare_context_image_analysis_error(mock_state_manager):
    """Test obsługi błędu podczas analizy obrazu."""
    orchestrator = Orchestrator(mock_state_manager)

    # Mock Eyes - rzuca wyjątek
    orchestrator.eyes.analyze_image = AsyncMock(
        side_effect=Exception("Vision model unavailable")
    )

    task_id = uuid4()
    request = TaskRequest(
        content="Analizuj",
        images=["broken_image"],
    )

    # Execute
    context = await orchestrator._prepare_context(task_id, request)

    # Assert
    # Nie powinno crashować, tylko zalogować błąd
    assert "Analizuj" in context
    # Sprawdź że dodano log o błędzie
    log_calls = [call[0][1] for call in mock_state_manager.add_log.call_args_list]
    assert any("Nie udało się przeanalizować" in log for log in log_calls)


@pytest.mark.asyncio
async def test_prepare_context_no_images(mock_state_manager):
    """Test przygotowania kontekstu bez obrazów."""
    orchestrator = Orchestrator(mock_state_manager)

    task_id = uuid4()
    request = TaskRequest(content="Tylko tekst")

    # Execute
    context = await orchestrator._prepare_context(task_id, request)

    # Assert
    assert context == "Tylko tekst"


# --- Testy pełnego workflow ---


@pytest.mark.asyncio
async def test_full_workflow_code_generation_with_critic(
    mock_state_manager, mock_intent_manager, mock_dispatcher
):
    """Test pełnego workflow generowania kodu z oceną."""
    orchestrator = Orchestrator(
        mock_state_manager, mock_intent_manager, mock_dispatcher
    )

    task_id = uuid4()
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.status = TaskStatus.PENDING
    mock_task.content = "Napisz funkcję hello"
    mock_state_manager.create_task.return_value = mock_task
    mock_state_manager.get_task.return_value = mock_task

    mock_intent_manager.classify_intent.return_value = "CODE_GENERATION"

    # Mock Coder i Critic
    good_code = 'def hello():\n    """Says hello."""\n    print("Hello")'
    mock_dispatcher.coder_agent.process.return_value = good_code
    mock_dispatcher.critic_agent.process.return_value = "APPROVED"

    # Execute
    request = TaskRequest(content="Napisz funkcję hello")
    response = await orchestrator.submit_task(request)

    # Wait a bit for background task (w prawdziwym teście użylibyśmy await)
    # Tu tylko sprawdzamy czy submit_task zwraca poprawną odpowiedź
    assert response.task_id is not None
    assert response.status == TaskStatus.PENDING
