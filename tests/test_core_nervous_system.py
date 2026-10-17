"""Testy integracyjne dla systemu zadań Venom Core Nervous System V1."""

import asyncio
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import venom_core.main as main_app
from tests.helpers.url_fixtures import MOCK_HTTP, local_runtime_id
from venom_core.api import dependencies as api_deps
from venom_core.api.routes import tasks as tasks_routes
from venom_core.config import SETTINGS
from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.goal_store import GoalStore
from venom_core.core.intent_manager import IntentManager
from venom_core.core.orchestrator import Orchestrator, orchestrator_submit
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer, TraceStatus
from venom_core.execution.maf_runtime import AgentRuntime as Kernel
from venom_core.services import module_registry
from venom_core.utils.llm_runtime import LLMRuntimeInfo

MODEL_REPLY = "Odpowiedź testowego modelu"


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
def patch_runtime(mock_runtime_info, monkeypatch):
    """Automatycznie patchuje runtime dla wszystkich testów."""
    modules = (
        "venom_core.utils.llm_runtime",
        "venom_core.api.routes.tasks",
        "venom_core.core.orchestrator.orchestrator_submit",
        "venom_core.core.orchestrator.orchestrator_dispatch",
        "venom_core.core.orchestrator.kernel_manager",
        "venom_core.core.orchestrator.session_handler",
        "venom_core.core.orchestrator.task_pipeline.context_builder",
        "venom_core.core.orchestrator.task_pipeline.task_validator",
    )
    for module in modules:
        monkeypatch.setattr(
            f"{module}.get_active_llm_runtime", lambda: mock_runtime_info
        )
    monkeypatch.setattr(SETTINGS, "LLM_CONFIG_HASH", mock_runtime_info.config_hash)
    monkeypatch.setattr(SETTINGS, "ENABLE_INTENT_EMBEDDING_ROUTER", False)


@pytest.fixture
def client(tmp_path, monkeypatch, fake_vector_store):
    """Real task API and pipeline, with isolated ownership and external model edges."""
    monkeypatch.setattr(
        "venom_core.memory.memory_skill.VectorStore", lambda: fake_vector_store
    )
    monkeypatch.setattr(
        "venom_core.execution.kernel_builder.KernelBuilder.build_kernel",
        lambda _: Kernel(),
    )
    connector = SimpleNamespace(ai_model_id="mock-model", service_id="default")
    monkeypatch.setattr(Kernel, "get_service", lambda *_args, **_kwargs: connector)
    state_manager = StateManager(str(tmp_path / "tasks.json"))
    tracer = RequestTracer(trace_file_path=str(tmp_path / "traces.json"))
    # ONNX trace callbacks use this shared getter outside FastAPI Depends.
    monkeypatch.setattr(tasks_routes.system_deps, "get_request_tracer", lambda: tracer)
    kernel = Kernel()
    dispatcher = TaskDispatcher(
        kernel, goal_store=GoalStore(str(tmp_path / "goals.json"))
    )
    monkeypatch.setattr(
        dispatcher.chat_agent, "process", AsyncMock(return_value=MODEL_REPLY)
    )
    intent_manager = IntentManager(kernel=kernel)
    monkeypatch.setattr(
        intent_manager, "classify_intent", AsyncMock(return_value="GENERAL_CHAT")
    )
    orchestrator = Orchestrator(
        state_manager,
        intent_manager=intent_manager,
        task_dispatcher=dispatcher,
        request_tracer=tracer,
    )
    previous_tasks = set(orchestrator_submit._background_tasks)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            owned = orchestrator_submit._background_tasks - previous_tasks
            if owned:
                _, pending = await asyncio.wait(owned, timeout=1)
                for task in pending:
                    task.cancel()
                if pending:
                    _, remaining = await asyncio.wait(pending, timeout=1)
                    assert not remaining, "owned API tasks did not finish cleanup"
            await state_manager.shutdown()
            await tracer.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.include_router(tasks_routes.router)
    app.add_api_route("/healthz", main_app.healthz)
    app.dependency_overrides = {
        api_deps.get_orchestrator: lambda: orchestrator,
        api_deps.get_state_manager: lambda: state_manager,
        api_deps.get_request_tracer: lambda: tracer,
    }
    app.state.orchestrator = orchestrator
    app.state.task_state = state_manager
    app.state.request_tracer = tracer
    module_registry._install_conversation_provider_lifespan(app, SimpleNamespace())
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def clear_state(client):
    """Fixture czyszczący stan przed testem."""
    state_manager = client.app.state.task_state
    assert hasattr(state_manager, "_tasks"), "StateManager contract requires '_tasks'"
    assert not state_manager._tasks
    yield state_manager


def completed_task(client, task_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        task = response.json()
        assert task["status"] in {"PENDING", "PROCESSING", "COMPLETED"}, task
        if task["status"] == "COMPLETED":
            return task
        time.sleep(0.01)
    pytest.fail(f"Task did not complete: {task}")


def test_healthz_endpoint(client):
    """Test endpointu health check."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "component": "venom-core"}


def test_create_task(client, clear_state):
    """Test tworzenia zadania przez API."""
    response = client.post("/api/v1/tasks", json={"content": "Test zadania"})

    assert response.status_code == 201
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "PENDING"


def test_get_task(client, clear_state):
    """Test pobierania zadania po ID."""
    # Utwórz zadanie
    create_response = client.post("/api/v1/tasks", json={"content": "Test zadania"})
    task_id = create_response.json()["task_id"]

    # Pobierz zadanie
    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == task_id
    assert data["content"] == "Test zadania"
    assert data["status"] in ["PENDING", "PROCESSING", "COMPLETED"]


def test_get_nonexistent_task(client, clear_state):
    """Test pobierania nieistniejącego zadania."""
    fake_id = str(uuid4())
    response = client.get(f"/api/v1/tasks/{fake_id}")
    assert response.status_code == 404


def test_get_all_tasks(client, clear_state):
    """Test pobierania listy wszystkich zadań."""
    # Utwórz kilka zadań
    client.post("/api/v1/tasks", json={"content": "Zadanie 1"})
    client.post("/api/v1/tasks", json={"content": "Zadanie 2"})
    client.post("/api/v1/tasks", json={"content": "Zadanie 3"})

    # Pobierz wszystkie zadania
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3
    assert all("id" in task for task in data)
    assert all("content" in task for task in data)


def test_task_execution_lifecycle(client, clear_state):
    """Test pełnego cyklu życia zadania - integracyjny test synchroniczny."""
    # Utwórz zadanie
    create_response = client.post(
        "/api/v1/tasks", json={"content": "Zadanie do przetworzenia"}
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["task_id"]

    # Sprawdź status początkowy (PENDING lub już PROCESSING)
    get_response = client.get(f"/api/v1/tasks/{task_id}")
    task_data = get_response.json()
    assert task_data["status"] in ["PENDING", "PROCESSING", "COMPLETED"]

    # Sprawdź status końcowy (COMPLETED)
    final_data = completed_task(client, task_id)

    assert final_data["status"] == "COMPLETED"
    assert final_data["result"] == MODEL_REPLY
    assert len(final_data["logs"]) > 0


def test_multiple_tasks_concurrent(client, clear_state):
    """Test równoczesnego przetwarzania wielu zadań."""
    # Utwórz kilka zadań jednocześnie
    task_ids = []
    for i in range(5):
        response = client.post(
            "/api/v1/tasks",
            json={
                "content": f"Pomoc {i}",
                "forced_intent": "HELP_REQUEST",
            },
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert "task_id" in payload
        task_ids.append(payload["task_id"])

    assert len(set(task_ids)) == 5
    for task_id in task_ids:
        task = completed_task(client, task_id)
        assert task["status"] == "COMPLETED"
        assert "System Pomocy" in task["result"]


def test_invalid_task_request(client, clear_state):
    """Test błędnego requestu tworzenia zadania."""
    # Request bez wymaganego pola 'content'
    response = client.post("/api/v1/tasks", json={})
    assert response.status_code == 422  # Unprocessable Entity


def test_task_logs(client, clear_state):
    """Test czy zadanie zapisuje logi podczas wykonania."""
    # Utwórz zadanie
    create_response = client.post("/api/v1/tasks", json={"content": "Zadanie z logami"})
    task_id = create_response.json()["task_id"]

    data = completed_task(client, task_id)

    assert len(data["logs"]) >= 2  # Minimum: start i zakończenie
    assert any("uruchomione" in log.lower() for log in data["logs"])
    assert any(
        "zakończono" in log.lower() or "przetwarzanie" in log.lower()
        for log in data["logs"]
    )


def test_fixture_ignores_polluted_application_globals(request, monkeypatch):
    poisoned_orchestrator = SimpleNamespace(
        submit_task=AsyncMock(
            side_effect=AssertionError("shared orchestrator was used")
        )
    )
    poisoned_state = SimpleNamespace()
    monkeypatch.setattr(main_app, "orchestrator", poisoned_orchestrator)
    monkeypatch.setattr(main_app, "state_manager", poisoned_state)
    monkeypatch.setattr(api_deps, "_orchestrator", poisoned_orchestrator)
    api_deps.get_orchestrator.cache_clear()
    try:
        isolated = request.getfixturevalue("client")
        response = isolated.post("/api/v1/tasks", json={"content": "Isolated task"})
        assert response.status_code == 201, response.text
        task = completed_task(isolated, response.json()["task_id"])
        assert task["result"] == MODEL_REPLY
        assert task["context_history"]["llm_runtime"]["model"] == "mock-model"
        orchestrator = isolated.app.state.orchestrator
        state = isolated.app.state.task_state
        for component in (
            orchestrator.streaming_handler,
            orchestrator.lessons_manager,
            orchestrator.session_handler,
            orchestrator.middleware,
            orchestrator.flow_coordinator,
        ):
            assert component.state_manager is state
        assert main_app.orchestrator is poisoned_orchestrator
        assert main_app.state_manager is poisoned_state
        assert api_deps._orchestrator is poisoned_orchestrator
        poisoned_orchestrator.submit_task.assert_not_awaited()
    finally:
        api_deps.get_orchestrator.cache_clear()


@pytest.mark.parametrize("poisoned_tracer", [False, True])
def test_create_task_onnx_runtime_completes_via_tasks_path(
    request, monkeypatch, poisoned_tracer
):
    stale_tracer = object()
    if poisoned_tracer:
        monkeypatch.setattr(tasks_routes.system_deps, "_request_tracer", stale_tracer)
        monkeypatch.setattr(
            tasks_routes.system_deps, "get_request_tracer", lambda: stale_tracer
        )
    client = request.getfixturevalue("client")
    request.getfixturevalue("clear_state")
    runtime = LLMRuntimeInfo(
        provider="onnx",
        model_name="models/gemma-3-4b-it-onnx",
        endpoint=None,
        service_type="onnx",
        mode="LOCAL",
        config_hash="onnxhash",
        runtime_id="onnx@local",
    )
    monkeypatch.setattr(
        "venom_core.api.routes.tasks.get_active_llm_runtime", lambda: runtime
    )

    class FakeOnnxClient:
        def generate(self, **_kwargs):
            return "ONNX OK"

    monkeypatch.setattr(
        "venom_core.api.routes.tasks.OnnxLlmClient", lambda: FakeOnnxClient()
    )

    response = client.post("/api/v1/tasks", json={"content": "test onnx normal"})
    assert response.status_code == 201, response.text
    task_id = response.json()["task_id"]
    payload = completed_task(client, task_id)
    assert payload["result"] == "ONNX OK"
    tracer = client.app.state.request_tracer
    assert tasks_routes.system_deps.get_request_tracer() is tracer
    trace = tracer.get_trace(UUID(task_id))
    # Task completion precedes the asynchronous session/trace success callback.
    deadline = time.monotonic() + 5
    while (
        trace is not None
        and trace.status in {TraceStatus.PENDING, TraceStatus.PROCESSING}
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        trace = tracer.get_trace(UUID(task_id))
    assert trace is not None
    assert trace.status is TraceStatus.COMPLETED, trace.model_dump()
    assert trace.llm_provider == "onnx"
    assert any(
        step.component == "OnnxTask" and step.action == "complete"
        for step in trace.steps
    )
    if poisoned_tracer:
        assert tasks_routes.system_deps._request_tracer is stale_tracer
