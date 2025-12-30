"""Testy API grafu knowledge (limit + mock fallback)."""

import networkx as nx
from fastapi.testclient import TestClient

from venom_core.api.routes import knowledge as knowledge_routes
from venom_core.main import app


def test_knowledge_graph_returns_mock_when_empty():
    """Pusty graf powinien zwrócić mock data zamiast błędu."""
    graph_store = type("Store", (), {"graph": nx.Graph()})()
    knowledge_routes.set_dependencies(graph_store, None)

    resp = TestClient(app).get("/api/v1/knowledge/graph?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("mock") is True
    assert "elements" in data


def test_knowledge_graph_respects_limit_and_filters_edges():
    """Limit powinien obcinać węzły i powiązane krawędzie."""
    g = nx.Graph()
    g.add_node("a", type="file", path="a.py")
    g.add_node("b", type="file", path="b.py")
    g.add_node("c", type="file", path="c.py")
    g.add_edge("a", "b", type="IMPORTS")
    g.add_edge("b", "c", type="IMPORTS")
    graph_store = type("Store", (), {"graph": g})()
    knowledge_routes.set_dependencies(graph_store, None)

    resp = TestClient(app).get("/api/v1/knowledge/graph?limit=2")
    assert resp.status_code == 200
    data = resp.json()
    elements = data["elements"]
    assert len(elements["nodes"]) == 2  # obcięte do limitu
    assert len(elements["edges"]) == 1  # krawędź tylko dla dozwolonych węzłów
    assert data.get("mock") is not True
