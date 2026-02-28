from __future__ import annotations

from types import SimpleNamespace

import pytest

from venom_core.services import knowledge_graph_service as svc


class _Graph:
    def __init__(self):
        self._nodes = [
            ("n1", {"type": "file", "path": "a.py"}),
            ("n2", {"type": "class", "name": "Agent", "file": "agents/a.py"}),
            ("n3", {"type": "function", "name": "run"}),
        ]
        self._edges = [
            ("n1", "n2", {"type": "USES"}),
            ("n2", "n3", {"type": "CALLS"}),
        ]

    def nodes(self, data: bool = False):
        return self._nodes

    def edges(self, data: bool = False):
        return self._edges


def test_normalize_graph_file_path() -> None:
    assert svc.normalize_graph_file_path(" src\\main.py ") == "src/main.py"
    with pytest.raises(ValueError):
        svc.normalize_graph_file_path("../etc/passwd")


def test_graph_builders_and_counter() -> None:
    store = SimpleNamespace(graph=_Graph())
    nodes = svc.build_graph_nodes(store, limit=10)
    edges = svc.build_graph_edges(store, {"n1", "n2", "n3"})

    assert len(nodes) == 3
    assert nodes[1]["data"]["type"] == "agent"
    assert len(edges) == 2
    assert edges[0]["data"]["label"] == "USES"

    svc.increment_graph_view_counter("overview")
    snap = svc.graph_view_counter_snapshot()
    assert snap["overview"] >= 1
