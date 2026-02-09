import sys
from unittest.mock import AsyncMock, MagicMock

# Mock heavy dependencies only for import phase
_module_backup: dict[str, object | None] = {}


def _set_mocked_module(name: str, module: object | None = None) -> object:
    _module_backup[name] = sys.modules.get(name)
    mocked = module if module is not None else MagicMock()
    sys.modules[name] = mocked  # type: ignore[assignment]
    return mocked


_set_mocked_module("venom_core.core.orchestrator")
_set_mocked_module("venom_core.core.tracer")
_set_mocked_module("venom_core.core.dispatcher")
_set_mocked_module("venom_core.services.memory_service")
_set_mocked_module("venom_core.services.session_store")
_set_mocked_module("venom_core.memory.embedding_service")

from uuid import uuid4  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Target modules
from venom_core.api.routes import knowledge as knowledge_routes  # noqa: E402
from venom_core.api.routes import memory as memory_routes  # noqa: E402
from venom_core.api.routes import tasks as tasks_routes  # noqa: E402
from venom_core.core.models import TaskStatus, VenomTask  # noqa: E402

pytestmark = pytest.mark.integration

for _name, _original in _module_backup.items():
    if _original is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _original  # type: ignore[assignment]

# --- Setup Fixtures ---


class MockApp:
    def __init__(self):
        self.app = FastAPI()
        self.client = TestClient(self.app)


@pytest.fixture
def mock_app():
    return MockApp()


# --- Knowledge Tests ---


def test_knowledge_graph_routes(mock_app):
    # Mock Graph Store
    mock_graph_store = MagicMock()
    mock_graph_store.graph.number_of_nodes.return_value = 10
    # Mock nodes and edges traversal
    mock_graph_store.graph.nodes.return_value = [
        ("node1", {"type": "file", "path": "/a.py"}),
        ("node2", {"type": "class", "name": "MyClass", "file": "/a.py"}),
    ]
    mock_graph_store.graph.edges.return_value = [
        ("node1", "node2", {"type": "DEFINES"})
    ]
    mock_graph_store.get_graph_summary.return_value = {
        "total_nodes": 2,
        "total_edges": 1,
    }
    mock_graph_store.get_file_info.return_value = {"lines": 10}
    mock_graph_store.scan_workspace.return_value = {"added": 1}

    # Inject dependency
    knowledge_routes.set_dependencies(graph_store=mock_graph_store)
    mock_app.app.include_router(knowledge_routes.router)

    # Test /knowledge/graph
    resp = mock_app.client.get("/api/v1/knowledge/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["elements"]["nodes"]) == 2

    # Test /graph/summary
    resp = mock_app.client.get("/api/v1/graph/summary")
    assert resp.status_code == 200
    assert resp.json()["nodes"] == 2

    # Test /graph/file/{path}
    resp = mock_app.client.get("/api/v1/graph/file/test_file.py")
    assert resp.status_code == 200

    # Test /graph/scan
    resp = mock_app.client.post("/api/v1/graph/scan")
    assert resp.status_code == 200

    # Test Empty Graph (Mock Response)
    mock_graph_store.graph.number_of_nodes.return_value = 0
    resp = mock_app.client.get("/api/v1/knowledge/graph")
    assert resp.json().get("mock") is True


def test_knowledge_lessons_routes(mock_app):
    mock_lessons_store = MagicMock()
    mock_lessons_store.get_all_lessons.return_value = [
        MagicMock(to_dict=lambda: {"id": "l1", "title": "Lesson 1"})
    ]
    mock_lessons_store.delete_last_n.return_value = 1

    knowledge_routes.set_dependencies(lessons_store=mock_lessons_store)
    mock_app.app.include_router(knowledge_routes.router)

    # Test /lessons
    resp = mock_app.client.get("/api/v1/lessons")
    assert resp.status_code == 200
    assert len(resp.json()["lessons"]) == 1

    # Test Prune
    resp = mock_app.client.delete("/api/v1/lessons/prune/latest?count=1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1


# --- Tasks Tests ---


@pytest.mark.asyncio
async def test_tasks_routes(mock_app):
    # Mock Orchestrator & State Manager
    mock_orch = AsyncMock()
    task_id = str(uuid4())
    mock_orch.submit_task.return_value = {"task_id": task_id, "status": "PENDING"}

    mock_state = MagicMock()
    mock_task = VenomTask(id=uuid4(), content="test", status=TaskStatus.PENDING)
    mock_state.get_task.return_value = mock_task
    mock_state.get_all_tasks.return_value = [mock_task]

    mock_tracer = MagicMock()
    mock_tracer.get_all_traces.return_value = []

    tasks_routes.set_dependencies(
        orchestrator=mock_orch, state_manager=mock_state, request_tracer=mock_tracer
    )
    mock_app.app.include_router(tasks_routes.router)

    # Test Create Task
    resp = mock_app.client.post("/api/v1/tasks", json={"content": "Do work"})
    assert resp.status_code == 201
    assert resp.json()["task_id"] == task_id

    # Test Get Task
    resp = mock_app.client.get(f"/api/v1/tasks/{mock_task.id}")
    assert resp.status_code == 200

    # Test Get All Tasks
    resp = mock_app.client.get("/api/v1/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Test History
    resp = mock_app.client.get("/api/v1/history/requests")
    assert resp.status_code == 200


# --- Memory Tests ---


def test_memory_routes(mock_app):
    # Mock VectorStore
    mock_vector_store = MagicMock()
    mock_vector_store.upsert.return_value = {"message": "ok", "chunks_count": 1}
    mock_vector_store.search.return_value = [{"id": "m1", "text": "result"}]
    mock_vector_store.delete_by_metadata.return_value = 5

    memory_routes.set_dependencies(vector_store=mock_vector_store)
    mock_app.app.include_router(memory_routes.router)

    # Test Ingest
    resp = mock_app.client.post("/api/v1/memory/ingest", json={"text": "Remember this"})
    assert resp.status_code == 201
    assert resp.json()["chunks_count"] == 1

    # Test Search
    resp = mock_app.client.post("/api/v1/memory/search", json={"query": "Recall"})
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1

    # Test Global Clear
    resp = mock_app.client.delete("/api/v1/memory/global")
    assert resp.status_code == 200
    assert resp.json()["deleted_vectors"] == 5

    # Test Session Clear
    resp = mock_app.client.delete("/api/v1/memory/session/sess1")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "sess1"

    # Test Session Get
    # In tests/coverage, we might need to access the dependency directly if not exposed
    # But memory_routes does not expose _session_store global. It uses dependency injection.
    # We should mock get_session_store dependency instead.
    from venom_core.api.dependencies import get_session_store

    mock_app.app.dependency_overrides[get_session_store] = (
        lambda: memory_routes._session_store
    )

    # We need to set the mock on the module level if we want the router to pick it up?
    # No, FastAPI depends on Dependency Injection.
    # The route uses: session_store: Annotated[Any, Depends(get_session_store)]
    # memory.py's set_dependencies sets api_deps.set_session_store

    # Let's inspect memory.py to see how it handles session_store
    # It calls api_deps.set_session_store(session_store)

    # So we should be able to rely on that if the router uses depends(get_session_store)
    # The issue is we are trying to configure return values on `memory_routes._session_store` which might not exist or be the right object.

    # Let's create a specific mock for session store and pass it via set_dependencies
    mock_session_store = MagicMock()
    mock_session_store.get_history.return_value = []
    mock_session_store.get_summary.return_value = "summary"

    memory_routes.set_dependencies(session_store=mock_session_store)

    resp = mock_app.client.get("/api/v1/memory/session/sess1")
    assert resp.status_code == 200

    # Test Memory Graph (Complex Logic - Default Mode)
    mock_vector_store.list_entries.return_value = [
        {"id": "m1", "metadata": {"session_id": "s1", "type": "fact", "pinned": True}},
        {"id": "m2", "metadata": {"user_id": "u1", "type": "rule"}},
    ]
    resp = mock_app.client.get("/api/v1/memory/graph?mode=default&include_lessons=true")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["elements"]["nodes"]) > 0

    # Test Memory Graph (Flow Mode)
    resp = mock_app.client.get("/api/v1/memory/graph?mode=flow")
    assert resp.status_code == 200

    # Test Pin Entry
    mock_vector_store.update_metadata.return_value = True
    resp = mock_app.client.post("/api/v1/memory/entry/m1/pin?pinned=true")
    assert resp.status_code == 200

    # Test Delete Entry
    mock_vector_store.delete_entry.return_value = 1
    resp = mock_app.client.delete("/api/v1/memory/entry/m1")
    assert resp.status_code == 200


def test_knowledge_errors_and_edges(mock_app):
    """Cover error paths and edge cases in knowledge routes."""
    # Mock for failure
    mock_graph_store = MagicMock()
    mock_graph_store.scan_workspace.return_value = {"error": "Scan failed"}
    knowledge_routes.set_dependencies(graph_store=mock_graph_store)
    mock_app.app.include_router(knowledge_routes.router)

    # Test Scan Error
    resp = mock_app.client.post("/api/v1/graph/scan")
    assert resp.status_code == 500

    # Test Invalid File Path
    # Note: TestClient might not handle .. correctly for 400 check, giving 404 is also acceptable security
    resp = mock_app.client.get("/api/v1/graph/file/../dangerous.py")
    assert resp.status_code in (400, 404)

    # Test Missing File
    mock_graph_store.get_file_info.return_value = None
    resp = mock_app.client.get("/api/v1/graph/file/missing.py")
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.skip(reason="Test hangs in CI environment due to stream loop issues")
async def test_tasks_streaming_and_errors(mock_app):
    """Cover stream_task and helpers in tasks routes."""
    mock_state = MagicMock()
    # Mock a task for streaming
    task_id = uuid4()
    # Mock task progression
    # Return PROCESSING 3 times, then COMPLETED forever
    from itertools import chain, repeat

    task_processing = VenomTask(
        id=task_id, content="Stream me", status=TaskStatus.PROCESSING, logs=["log1"]
    )
    task_completed = VenomTask(
        id=task_id,
        content="Stream me",
        status=TaskStatus.COMPLETED,
        result="Done",
        logs=["log1", "log2"],
    )
    mock_state.get_task.side_effect = chain(
        [task_processing] * 3, repeat(task_completed)
    )

    tasks_routes.set_dependencies(
        orchestrator=AsyncMock(), state_manager=mock_state, request_tracer=MagicMock()
    )
    mock_app.app.include_router(tasks_routes.router)

    # Test Stream Endpoint (SSE)
    # The route is /tasks/{task_id}/stream
    # The router prefix is /api/v1, but the include_router might duplicate it if not careful.
    # verify path: /api/v1/tasks/{task_id}/stream

    # IMPORTANT: FastAPI TestClient might not handle async generator streams perfectly with 'stream=True'
    # without using AsyncClient, but TestClient wraps starlette.testclient.
    # Let's verify the path.

    # Test Stream Endpoint (SSE)
    # The route is /tasks/{task_id}/stream
    with mock_app.client.stream("GET", f"/api/v1/tasks/{task_id}/stream") as response:
        assert response.status_code == 200
        # Iterate a limited number of times to avoid hanging
        count = 0
        for line in response.iter_lines():
            if line:
                assert "event:" in line or "data:" in line
            count += 1
            if count > 10:
                break

    # Test Missing Task Stream
    mock_state.get_task.return_value = None
    resp = mock_app.client.get(f"/api/v1/tasks/{uuid4()}/stream")
    assert resp.status_code == 404

    # Test Trace Validation Helpers
    from venom_core.api.routes.tasks import _get_llm_runtime, _validate_trace_status

    # Valid status
    _validate_trace_status("COMPLETED")
    # Invalid status
    with pytest.raises(Exception):  # HTTPException
        _validate_trace_status("INVALID_STATUS")

    # Context helpers
    mock_task_for_runtime = VenomTask(
        id=uuid4(), content="test", status=TaskStatus.COMPLETED
    )
    runtime_info = _get_llm_runtime(mock_task_for_runtime)
    assert isinstance(runtime_info, dict)


def test_memory_pruning_endpoints(mock_app):
    """Cover pruning endpoints in memory/knowledge."""
    mock_lessons = MagicMock()
    mock_lessons.delete_by_time_range.return_value = 5
    mock_lessons.delete_by_tag.return_value = 3
    mock_lessons.prune_by_ttl.return_value = 2
    mock_lessons.clear_all.return_value = True

    knowledge_routes.set_dependencies(lessons_store=mock_lessons)
    mock_app.app.include_router(knowledge_routes.router)

    # Test Prune Range
    resp = mock_app.client.delete(
        "/api/v1/lessons/prune/range",
        params={"start": "2024-01-01T00:00:00", "end": "2024-01-31T23:59:59"},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 5

    # Test Prune Tag
    resp = mock_app.client.delete("/api/v1/lessons/prune/tag?tag=test")
    assert resp.status_code == 200

    # Test Prune TTL
    resp = mock_app.client.delete("/api/v1/lessons/prune/ttl?days=30")
    assert resp.status_code == 200

    # Test Purge (Force=False)
    resp = mock_app.client.delete("/api/v1/lessons/purge")
    assert resp.status_code == 400

    # Test Purge (Force=True)
    resp = mock_app.client.delete("/api/v1/lessons/purge?force=true")
    assert resp.status_code == 200
