from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes import knowledge as knowledge_routes
from venom_core.api.routes import memory as memory_routes


def _build_client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, client=("127.0.0.1", 51000))


def test_knowledge_graph_supports_overview_mode() -> None:
    graph_store = MagicMock()
    graph_store.graph.number_of_nodes.return_value = 4
    graph_store.graph.nodes.return_value = [
        ("a", {"type": "file", "path": "a.py"}),
        ("b", {"type": "file", "path": "b.py"}),
        ("c", {"type": "file", "path": "c.py"}),
        ("d", {"type": "file", "path": "d.py"}),
    ]
    graph_store.graph.edges.return_value = [
        ("a", "b", {"type": "IMPORTS"}),
        ("b", "c", {"type": "IMPORTS"}),
        ("c", "d", {"type": "IMPORTS"}),
    ]

    knowledge_routes.set_dependencies(graph_store=graph_store)
    client = _build_client(knowledge_routes.router)

    response = client.get(
        "/api/v1/knowledge/graph", params={"view": "overview", "limit_nodes": 2}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["view"] == "overview"
    assert payload["stats"]["nodes"] <= 2


def test_knowledge_graph_supports_focus_mode() -> None:
    graph_store = MagicMock()
    graph_store.graph.number_of_nodes.return_value = 4
    graph_store.graph.nodes.return_value = [
        ("a", {"type": "file", "path": "a.py"}),
        ("b", {"type": "file", "path": "b.py"}),
        ("c", {"type": "file", "path": "c.py"}),
        ("d", {"type": "file", "path": "d.py"}),
    ]
    graph_store.graph.edges.return_value = [
        ("a", "b", {"type": "IMPORTS"}),
        ("b", "c", {"type": "IMPORTS"}),
        ("c", "d", {"type": "IMPORTS"}),
    ]

    knowledge_routes.set_dependencies(graph_store=graph_store)
    client = _build_client(knowledge_routes.router)

    response = client.get(
        "/api/v1/knowledge/graph",
        params={
            "view": "focus",
            "seed_id": "b",
            "max_hops": 1,
            "include_isolates": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    node_ids = {node["data"]["id"] for node in payload["elements"]["nodes"]}
    assert "b" in node_ids
    assert payload["view"] == "focus"


def test_memory_graph_supports_overview_mode() -> None:
    vector_store = MagicMock()
    vector_store.list_entries.return_value = [
        {"id": "m1", "text": "one", "metadata": {"session_id": "s1", "user_id": "u1"}},
        {"id": "m2", "text": "two", "metadata": {"session_id": "s1", "user_id": "u1"}},
        {
            "id": "m3",
            "text": "three",
            "metadata": {"session_id": "s2", "user_id": "u2"},
        },
    ]

    memory_routes.set_dependencies(vector_store=vector_store, lessons_store=MagicMock())
    client = _build_client(memory_routes.router)

    response = client.get(
        "/api/v1/memory/graph", params={"view": "overview", "limit_nodes": 2}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["view"] == "overview"
    assert payload["stats"]["nodes"] <= 2


def test_memory_graph_supports_focus_mode() -> None:
    vector_store = MagicMock()
    vector_store.list_entries.return_value = [
        {"id": "m1", "text": "one", "metadata": {"session_id": "s1", "user_id": "u1"}},
        {"id": "m2", "text": "two", "metadata": {"session_id": "s1", "user_id": "u1"}},
        {
            "id": "m3",
            "text": "three",
            "metadata": {"session_id": "s2", "user_id": "u2"},
        },
    ]

    memory_routes.set_dependencies(vector_store=vector_store, lessons_store=MagicMock())
    client = _build_client(memory_routes.router)

    response = client.get(
        "/api/v1/memory/graph",
        params={
            "view": "focus",
            "seed_id": "m1",
            "max_hops": 1,
            "include_isolates": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    node_ids = {node["data"]["id"] for node in payload["elements"]["nodes"]}
    assert "m1" in node_ids
    assert payload["view"] == "focus"
