import sys
from unittest.mock import AsyncMock, MagicMock

# Mock orchestrator to bypass heavy dependencies (semantic_kernel, pydantic errors)
sys.modules["venom_core.core.orchestrator"] = MagicMock()
sys.modules["venom_core.core.tracer"] = MagicMock()
sys.modules["venom_core.core.dispatcher"] = MagicMock()
sys.modules["venom_core.services.memory_service"] = MagicMock()
sys.modules["venom_core.services.session_store"] = MagicMock()
sys.modules["venom_core.memory.embedding_service"] = MagicMock()

from uuid import uuid4  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Target modules
from venom_core.api.routes import knowledge as knowledge_routes  # noqa: E402
from venom_core.api.routes import memory as memory_routes  # noqa: E402
from venom_core.api.routes import tasks as tasks_routes  # noqa: E402
from venom_core.core.models import TaskStatus, VenomTask  # noqa: E402

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
