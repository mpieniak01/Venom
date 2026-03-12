"""Testy jednostkowe dla agentów."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.agents.chat import ChatAgent
from venom_core.agents.coder import CoderAgent


class ConcreteAgent(BaseAgent):
    """Konkretna implementacja BaseAgent do testów."""

    async def process(self, input_text: str) -> str:
        return f"Processed: {input_text}"


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    return kernel


@pytest.fixture
def mock_chat_service():
    """Fixture dla mockowego serwisu chat."""
    service = MagicMock()
    service.get_chat_message_content = AsyncMock()
    return service


# --- Testy BaseAgent ---


def test_base_agent_initialization(mock_kernel):
    """Test inicjalizacji BaseAgent."""
    agent = ConcreteAgent(mock_kernel)
    assert agent.kernel == mock_kernel


@pytest.mark.asyncio
async def test_base_agent_process(mock_kernel):
    """Test metody process w konkretnej implementacji."""
    agent = ConcreteAgent(mock_kernel)
    result = await agent.process("test input")
    assert result == "Processed: test input"


# --- Testy CoderAgent ---


def test_coder_agent_initialization(mock_kernel):
    """Test inicjalizacji CoderAgent."""
    agent = CoderAgent(mock_kernel)
    assert agent.kernel == mock_kernel
    assert "Senior Developer" in agent.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_coder_agent_generates_code(mock_kernel, mock_chat_service):
    """Test generowania kodu przez CoderAgent."""
    # Mockuj odpowiedź od LLM
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value='```python\ndef hello_world():\n    print("Hello World")\n```'
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    agent = CoderAgent(mock_kernel)
    result = await agent.process("Napisz funkcję Hello World w Python")

    assert "hello_world" in result
    assert "python" in result
    assert mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_coder_agent_handles_error(mock_kernel, mock_chat_service):
    """Test obsługi błędu przez CoderAgent."""
    mock_chat_service.get_chat_message_content.side_effect = Exception(
        "Connection error"
    )
    mock_kernel.get_service.return_value = mock_chat_service

    agent = CoderAgent(mock_kernel)

    with pytest.raises(Exception, match="Connection error"):
        await agent.process("Napisz kod")


# --- Testy ChatAgent ---


def test_chat_agent_initialization(mock_kernel):
    """Test inicjalizacji ChatAgent."""
    agent = ChatAgent(mock_kernel)
    assert agent.kernel == mock_kernel
    assert "Venom" in agent.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_chat_agent_responds_to_greeting(mock_kernel, mock_chat_service):
    """Test odpowiedzi ChatAgent na powitanie."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value="Cześć! Świetnie się mam, dziękuję. Gotowy do pomocy!"
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel)
    result = await agent.process("Cześć Venom, jak się masz?")

    assert "Cześć" in result or "cześć" in result.lower()
    assert mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_chat_agent_answers_question(mock_kernel, mock_chat_service):
    """Test odpowiedzi ChatAgent na pytanie."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="Stolicą Francji jest Paryż.")
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel)
    result = await agent.process("Jaka jest stolica Francji?")

    assert "Paryż" in result or "pary" in result.lower()
    assert mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_chat_agent_tells_joke(mock_kernel, mock_chat_service):
    """Test opowiadania kawału przez ChatAgent."""
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(
        return_value="Dlaczego programiści wolą ciemny motyw? Bo światło przyciąga błędy! 😄"
    )
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel)
    result = await agent.process("Opowiedz kawał")

    assert len(result) > 0
    assert mock_chat_service.get_chat_message_content.called


@pytest.mark.asyncio
async def test_chat_agent_handles_error(mock_kernel, mock_chat_service):
    """Test obsługi błędu przez ChatAgent."""
    mock_chat_service.get_chat_message_content.side_effect = Exception("LLM error")
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel)

    with pytest.raises(Exception, match="LLM error"):
        await agent.process("Jakieś pytanie")


# --- Testy ChatAgent z ModelRegistry ---


def test_chat_agent_initialization_with_model_registry(mock_kernel):
    """Test inicjalizacji ChatAgent z ModelRegistry."""
    from venom_core.core.model_registry import ModelRegistry

    mock_registry = MagicMock(spec=ModelRegistry)
    agent = ChatAgent(mock_kernel, model_registry=mock_registry)
    assert agent.kernel == mock_kernel
    assert agent.model_registry == mock_registry


def test_chat_agent_supports_system_prompt_with_registry(mock_kernel):
    """Test sprawdzania wsparcia system prompt przez ModelRegistry."""
    from venom_core.core.model_registry import (
        ModelCapabilities,
        ModelMetadata,
        ModelProvider,
        ModelRegistry,
    )

    # Utwórz registry z modelem niewspierającym system role
    mock_registry = MagicMock(spec=ModelRegistry)
    mock_registry.manifest = {
        "google/gemma-2b-it": ModelMetadata(
            name="google/gemma-2b-it",
            provider=ModelProvider.HUGGINGFACE,
            display_name="Gemma 2B IT",
            capabilities=ModelCapabilities(supports_system_role=False),
        )
    }
    mock_registry.get_model_capabilities = MagicMock(
        return_value=ModelCapabilities(supports_system_role=False)
    )

    agent = ChatAgent(mock_kernel, model_registry=mock_registry)

    # Mock chat service z model_id = "gemma-2b-it" (base name matches)
    mock_service = MagicMock()
    mock_service.ai_model_id = "gemma-2b-it"

    result = agent._supports_system_prompt(mock_service)
    assert result is False
    assert mock_registry.get_model_capabilities.called


def test_chat_agent_supports_system_prompt_fallback(mock_kernel):
    """Test fallback do hardcoded listy gdy model nie w manifeście."""
    from venom_core.core.model_registry import ModelRegistry

    # Registry bez modelu gemma
    mock_registry = MagicMock(spec=ModelRegistry)
    mock_registry.manifest = {}

    agent = ChatAgent(mock_kernel, model_registry=mock_registry)

    # Mock chat service z model_id zawierającym "gemma-2b"
    mock_service = MagicMock()
    mock_service.ai_model_id = "gemma-2b-local"

    result = agent._supports_system_prompt(mock_service)
    # Powinno użyć fallback i zwrócić False (gemma-2b jest w MODELS_WITHOUT_SYSTEM_ROLE)
    assert result is False


def test_chat_agent_supports_system_prompt_without_registry(mock_kernel):
    """Test sprawdzania wsparcia system prompt bez ModelRegistry."""
    agent = ChatAgent(mock_kernel)  # Bez registry

    # Model wspierający system prompt
    mock_service = MagicMock()
    mock_service.ai_model_id = "gpt-4o"

    result = agent._supports_system_prompt(mock_service)
    assert result is True

    # Model niewspierający system prompt (z hardcoded listy)
    mock_service.ai_model_id = "gemma-2b"
    result = agent._supports_system_prompt(mock_service)
    assert result is False


@pytest.mark.asyncio
async def test_chat_agent_combines_prompt_for_gemma(mock_kernel, mock_chat_service):
    """Test łączenia system prompt z user message dla Gemma 2B."""
    from venom_core.core.model_registry import (
        ModelCapabilities,
        ModelMetadata,
        ModelProvider,
        ModelRegistry,
    )

    # Utwórz registry z Gemma 2B
    mock_registry = MagicMock(spec=ModelRegistry)
    mock_registry.manifest = {
        "google/gemma-2b-it": ModelMetadata(
            name="google/gemma-2b-it",
            provider=ModelProvider.HUGGINGFACE,
            display_name="Gemma 2B IT",
            capabilities=ModelCapabilities(supports_system_role=False),
        )
    }
    mock_registry.get_model_capabilities = MagicMock(
        return_value=ModelCapabilities(supports_system_role=False)
    )

    # Mock odpowiedzi
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="Test response")
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_chat_service.ai_model_id = "gemma-2b-it"
    mock_chat_service.service_id = "local_llm"
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel, model_registry=mock_registry)
    await agent.process("Test question")

    # Sprawdź że została wywołana funkcja get_chat_message_content
    assert mock_chat_service.get_chat_message_content.called

    # Sprawdź że chat_history zawiera połączoną wiadomość
    call_args = mock_chat_service.get_chat_message_content.call_args
    chat_history = call_args[1]["chat_history"]

    # Powinno być tylko 1 wiadomość (USER) zamiast 2 (SYSTEM + USER)
    assert len(chat_history.messages) == 1
    assert chat_history.messages[0].role.value == "user"

    # Wiadomość powinna zawierać zarówno system prompt jak i pytanie użytkownika
    message_content = str(chat_history.messages[0].content)
    assert "Venom" in message_content or "asystent" in message_content.lower()
    assert "Test question" in message_content


def _ghost_client(mod, ghost=None):
    app = FastAPI()
    mod.set_dependencies(None, None, None, None, None, ghost)
    app.include_router(mod.router)
    return TestClient(app)


@pytest.fixture
def ghost_mod():
    from venom_core.api.routes import agents as mod

    originals = (
        mod._gardener_agent,
        mod._shadow_agent,
        mod._file_watcher,
        mod._documenter_agent,
        mod._orchestrator,
        mod._ghost_agent,
        dict(mod._ghost_local_tasks),
        getattr(mod.SETTINGS, "ENABLE_GHOST_API", False),
        getattr(mod.SETTINGS, "ENABLE_GHOST_AGENT", False),
    )
    mod._ghost_run_store.clear()
    mod._ghost_local_tasks.clear()
    yield mod
    mod._ghost_run_store.clear()
    mod._ghost_local_tasks.clear()
    (
        mod._gardener_agent,
        mod._shadow_agent,
        mod._file_watcher,
        mod._documenter_agent,
        mod._orchestrator,
        mod._ghost_agent,
        local_tasks,
        mod.SETTINGS.ENABLE_GHOST_API,
        mod.SETTINGS.ENABLE_GHOST_AGENT,
    ) = originals
    mod._ghost_local_tasks.update(local_tasks)


def test_ghost_store_branches_and_helpers(ghost_mod):
    store = ghost_mod._ghost_run_store
    store.clear()

    assert store.try_start({"task_id": "t1", "status": "running"}) is True
    assert store.try_start({"task_id": "t2", "status": "running"}) is False
    assert store.update("missing", {"status": "failed"})["task_id"] == "t1"
    store.clear()
    assert store.update("missing", {"status": "failed"}) is None
    assert ghost_mod._get_runtime_profile("missing") is None
    assert len(ghost_mod._hash_content("abc")) == 64


def test_ghost_store_invalid_json_read_returns_none(ghost_mod):
    state_path = ghost_mod._ghost_run_store._state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{not-json", encoding="utf-8")
    assert ghost_mod._ghost_run_store.get() is None


@pytest.mark.asyncio
async def test_ghost_run_process_cancel_watch_branches(ghost_mod):
    store = ghost_mod._ghost_run_store
    store.clear()
    store.try_start({"task_id": "cancel-me", "status": "running"})

    started = asyncio.Event()

    async def _slow_process(_content: str) -> str:
        started.set()
        await asyncio.sleep(0.4)
        return "never"

    ghost = MagicMock()
    ghost.process = AsyncMock(side_effect=_slow_process)
    ghost.emergency_stop_trigger = MagicMock()

    with patch.object(ghost_mod, "_ghost_agent", ghost):
        task = asyncio.create_task(
            ghost_mod._run_ghost_process_with_cancel_watch(
                task_id="cancel-me", content="open app"
            )
        )
        await started.wait()
        store.update("cancel-me", {"status": "cancelling"})
        with pytest.raises(asyncio.CancelledError):
            await task

    ghost.emergency_stop_trigger.assert_called_once()


@pytest.mark.asyncio
async def test_ghost_run_job_failure_and_cancelled_paths(ghost_mod):
    store = ghost_mod._ghost_run_store
    store.clear()
    store.try_start(
        {
            "task_id": "f1",
            "status": "running",
            "runtime_profile": "desktop_safe",
        }
    )
    ghost_mod._ghost_local_tasks["f1"] = MagicMock()

    with (
        patch.object(
            ghost_mod,
            "_run_ghost_process_with_cancel_watch",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch.object(ghost_mod, "_publish_ghost_audit", MagicMock()),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await ghost_mod._run_ghost_job(
                task_id="f1",
                payload=ghost_mod.GhostRunRequest(content="do"),
                actor="tester",
            )

    store.clear()
    store.try_start(
        {
            "task_id": "c1",
            "status": "running",
            "runtime_profile": "desktop_safe",
        }
    )
    ghost_mod._ghost_local_tasks["c1"] = MagicMock()
    with (
        patch.object(
            ghost_mod,
            "_run_ghost_process_with_cancel_watch",
            AsyncMock(side_effect=asyncio.CancelledError),
        ),
        patch.object(ghost_mod, "_publish_ghost_audit", MagicMock()),
    ):
        with pytest.raises(asyncio.CancelledError):
            await ghost_mod._run_ghost_job(
                task_id="c1",
                payload=ghost_mod.GhostRunRequest(content="do"),
                actor="tester",
            )


def test_ghost_status_endpoint_branches(ghost_mod):
    ghost_mod.SETTINGS.ENABLE_GHOST_API = False
    ghost_mod.SETTINGS.ENABLE_GHOST_AGENT = False
    client = _ghost_client(ghost_mod)
    assert client.get("/api/v1/ghost/status").status_code == 200

    ghost_mod.SETTINGS.ENABLE_GHOST_API = True
    ghost_mod.SETTINGS.ENABLE_GHOST_AGENT = True
    assert client.get("/api/v1/ghost/status").status_code == 503

    ghost = MagicMock()
    ghost.get_status.side_effect = RuntimeError("status fail")
    client = _ghost_client(ghost_mod, ghost=ghost)
    assert client.get("/api/v1/ghost/status").status_code == 500

    ghost.get_status.side_effect = None
    ghost.get_status.return_value = {"is_running": False}
    ghost_mod._ghost_run_store.clear()
    ghost_mod._ghost_run_store.try_start(
        {"task_id": "done-task", "status": "running", "runtime_profile": "desktop_safe"}
    )
    done_task = MagicMock()
    done_task.done.return_value = True
    ghost_mod._ghost_local_tasks["done-task"] = done_task
    response = client.get("/api/v1/ghost/status")
    assert response.status_code == 200
    assert response.json()["task_active"] is False


def test_ghost_start_endpoint_branches(ghost_mod):
    ghost = MagicMock()
    ghost.apply_runtime_profile.return_value = {"profile": "desktop_safe"}
    client = _ghost_client(ghost_mod, ghost=ghost)

    ghost_mod.SETTINGS.ENABLE_GHOST_API = False
    ghost_mod.SETTINGS.ENABLE_GHOST_AGENT = False
    assert (
        client.post("/api/v1/ghost/start", json={"content": "open"}).status_code == 503
    )

    ghost_mod.SETTINGS.ENABLE_GHOST_API = True
    ghost_mod.SETTINGS.ENABLE_GHOST_AGENT = True
    client_missing = _ghost_client(ghost_mod)
    assert (
        client_missing.post("/api/v1/ghost/start", json={"content": "open"}).status_code
        == 503
    )
    client = _ghost_client(ghost_mod, ghost=ghost)

    ghost_mod._ghost_run_store.clear()
    ghost_mod._ghost_run_store.try_start(
        {"task_id": "active", "status": "running", "runtime_profile": "desktop_safe"}
    )
    assert (
        client.post("/api/v1/ghost/start", json={"content": "open"}).status_code == 409
    )

    ghost_mod._ghost_run_store.clear()
    with (
        patch.object(
            ghost_mod,
            "ensure_data_mutation_allowed",
            side_effect=PermissionError("deny"),
        ),
        patch.object(
            ghost_mod,
            "raise_permission_denied_http",
            side_effect=HTTPException(status_code=403, detail="deny"),
        ),
    ):
        assert (
            client.post("/api/v1/ghost/start", json={"content": "open"}).status_code
            == 403
        )

    with (
        patch.object(ghost_mod._ghost_run_store, "get", return_value=None),
        patch.object(ghost_mod._ghost_run_store, "try_start", return_value=False),
    ):
        assert (
            client.post("/api/v1/ghost/start", json={"content": "open"}).status_code
            == 409
        )

    with patch.object(ghost_mod, "_run_ghost_job", new=AsyncMock(return_value="ok")):
        response = client.post("/api/v1/ghost/start", json={"content": "very secret"})
    assert response.status_code == 200
    state = ghost_mod._ghost_run_store.get()
    assert state["content_length"] == len("very secret")
    assert "content" not in state
    assert "content_sha256" in state


def test_ghost_cancel_endpoint_branches(ghost_mod):
    ghost = MagicMock()
    ghost.emergency_stop_trigger = MagicMock()
    client = _ghost_client(ghost_mod, ghost=ghost)

    ghost_mod.SETTINGS.ENABLE_GHOST_API = False
    ghost_mod.SETTINGS.ENABLE_GHOST_AGENT = False
    assert client.post("/api/v1/ghost/cancel").status_code == 503

    ghost_mod.SETTINGS.ENABLE_GHOST_API = True
    ghost_mod.SETTINGS.ENABLE_GHOST_AGENT = True
    client_missing = _ghost_client(ghost_mod)
    assert client_missing.post("/api/v1/ghost/cancel").status_code == 503
    client = _ghost_client(ghost_mod, ghost=ghost)

    with (
        patch.object(
            ghost_mod,
            "ensure_data_mutation_allowed",
            side_effect=PermissionError("deny"),
        ),
        patch.object(
            ghost_mod,
            "raise_permission_denied_http",
            side_effect=HTTPException(status_code=403, detail="deny"),
        ),
    ):
        assert client.post("/api/v1/ghost/cancel").status_code == 403

    ghost_mod._ghost_run_store.clear()
    response = client.post("/api/v1/ghost/cancel")
    assert response.status_code == 200
    assert response.json() == {"status": "success", "cancelled": False, "task_id": None}

    class _PendingTask:
        def __init__(self):
            self._done = False

        def done(self):
            return self._done

        def cancel(self):
            self._done = True

        def __await__(self):
            if False:
                yield None
            raise asyncio.CancelledError

    ghost_mod._ghost_run_store.clear()
    ghost_mod._ghost_run_store.try_start(
        {
            "task_id": "cancel-active",
            "status": "running",
            "runtime_profile": "desktop_safe",
        }
    )
    ghost_mod._ghost_local_tasks["cancel-active"] = _PendingTask()
    response = client.post("/api/v1/ghost/cancel")
    assert response.status_code == 200
    assert response.json()["cancelled"] is True


@pytest.mark.asyncio
async def test_chat_agent_separate_prompt_for_standard_models(
    mock_kernel, mock_chat_service
):
    """Test osobnych wiadomości system/user dla standardowych modeli."""
    from venom_core.core.model_registry import (
        ModelCapabilities,
        ModelMetadata,
        ModelProvider,
        ModelRegistry,
    )

    # Utwórz registry z modelem wspierającym system role
    # Uwaga: Używamy ModelProvider.LOCAL tylko w kontekście testu mockowego,
    # aby nie wprowadzać zależności od providera OpenAI w ModelProvider enum.
    # W rzeczywistych scenariuszach gpt-4o byłby obsługiwany przez OpenAI API.
    mock_registry = MagicMock(spec=ModelRegistry)
    mock_registry.manifest = {
        "gpt-4o": ModelMetadata(
            name="gpt-4o",
            provider=ModelProvider.LOCAL,
            display_name="GPT-4o",
            capabilities=ModelCapabilities(supports_system_role=True),
        )
    }
    mock_registry.get_model_capabilities = MagicMock(
        return_value=ModelCapabilities(supports_system_role=True)
    )

    # Mock odpowiedzi
    mock_response = MagicMock()
    mock_response.__str__ = MagicMock(return_value="Test response")
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_chat_service.ai_model_id = "gpt-4o"
    mock_chat_service.service_id = "cloud_high"
    mock_kernel.get_service.return_value = mock_chat_service

    agent = ChatAgent(mock_kernel, model_registry=mock_registry)
    await agent.process("Test question")

    # Sprawdź że została wywołana funkcja get_chat_message_content
    assert mock_chat_service.get_chat_message_content.called

    # Sprawdź że chat_history zawiera 2 oddzielne wiadomości
    call_args = mock_chat_service.get_chat_message_content.call_args
    chat_history = call_args[1]["chat_history"]

    # Powinno być 2 wiadomości: SYSTEM i USER
    assert len(chat_history.messages) == 2
    assert chat_history.messages[0].role.value == "system"
    assert chat_history.messages[1].role.value == "user"

    # System message powinno zawierać prompt
    assert "Venom" in str(chat_history.messages[0].content)
    # User message powinno zawierać tylko pytanie
    assert str(chat_history.messages[1].content) == "Test question"


@pytest.mark.asyncio
async def test_base_agent_handle_chat_api_error_applies_system_fallback(mock_kernel):
    agent = ConcreteAgent(mock_kernel)
    chat_history = ChatHistory()
    chat_history.add_message(ChatMessageContent(role=AuthorRole.SYSTEM, content="S"))
    chat_history.add_message(ChatMessageContent(role=AuthorRole.USER, content="Q"))
    settings = OpenAIChatPromptExecutionSettings()

    handled, new_history, functions_enabled, system_fallback_used = (
        agent._handle_chat_api_error(
            api_error=Exception("system role not supported"),
            chat_history=chat_history,
            settings=settings,
            functions_enabled=False,
            system_fallback_used=False,
        )
    )

    assert handled is True
    assert functions_enabled is False
    assert system_fallback_used is True
    assert len(new_history.messages) == 1
    assert new_history.messages[0].role == AuthorRole.USER


@pytest.mark.asyncio
async def test_chat_agent_invoke_with_tool_fallback_disables_functions(
    mock_kernel, mock_chat_service
):
    mock_kernel.get_service.return_value = mock_chat_service
    agent = ChatAgent(mock_kernel)
    agent._invoke_chat_service = AsyncMock(
        side_effect=[Exception("does not support tools"), "fallback response"]
    )

    response = await agent._invoke_with_tool_fallback(
        chat_service=mock_chat_service,
        chat_history=ChatHistory(),
        allow_functions=True,
        generation_params=None,
    )

    assert response == "fallback response"
    assert agent._invoke_chat_service.call_count == 2
    assert (
        agent._invoke_chat_service.call_args_list[1].kwargs["enable_functions"] is False
    )
