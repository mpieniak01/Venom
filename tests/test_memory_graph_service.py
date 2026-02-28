from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from venom_core.services import memory_graph_service as svc


def test_ingest_helpers_and_errors() -> None:
    req = SimpleNamespace(
        category="fact",
        session_id="s1",
        user_id="u1",
        memory_type="fact",
        scope="session",
        topic="t",
        timestamp="2026-01-01T00:00:00Z",
        pinned=True,
    )
    meta = svc.build_ingest_metadata(req)
    assert meta["category"] == "fact"
    assert meta["retention_scope"] == "session"

    with pytest.raises(ValueError):
        svc.require_nonempty("", "bad")

    logger = SimpleNamespace(exception=lambda *_args, **_kwargs: None)
    with pytest.raises(HTTPException) as exc:
        svc.raise_memory_http_error(RuntimeError("boom"), context="x", logger=logger)
    assert exc.value.status_code == 500


def test_graph_helpers_nodes_edges_and_counters() -> None:
    filters = svc.build_memory_graph_filters("s1", True)
    assert filters == {"session_id": "s1", "pinned": True}

    node = svc.build_memory_node(
        {"id": "1", "text": "hello", "metadata": {"session_id": "s1", "user_id": "u1"}}
    )
    assert node["data"]["id"] == "1"

    sessions: dict[str, dict] = {}
    users: dict[str, dict] = {}
    svc.ensure_session_node(sessions, "s1")
    svc.ensure_user_node(users, "u1")
    edges = svc.build_relation_edges("1", "s1", "u1")
    assert sessions and users and len(edges) == 2

    svc.increment_memory_view_counter("overview")
    snap = svc.memory_view_counter_snapshot()
    assert snap["overview"] >= 1


def test_lesson_collection_and_flow_edges() -> None:
    class _Lessons:
        def get_all_lessons(self, limit: int):
            return [
                {"id": "l1", "title": "Lesson", "timestamp": "2026-01-01T00:00:00Z"}
            ]

    logger = SimpleNamespace(warning=lambda *_args, **_kwargs: None)
    nodes, edges = svc.collect_lesson_graph(
        _Lessons(), 10, allow_fallback=False, logger=logger, default_user_id="u1"
    )
    assert len(nodes) == 1
    assert len(edges) == 1

    flow_edges: list[dict] = []
    svc.append_flow_edges(
        [
            {"data": {"id": "a", "meta": {"timestamp": "2026-01-01T00:00:00Z"}}},
            {"data": {"id": "b", "meta": {"timestamp": "2026-01-01T00:00:01Z"}}},
        ],
        flow_edges,
    )
    assert flow_edges and flow_edges[0]["data"]["source"] == "a"


def test_build_memory_graph_payload() -> None:
    class _Vector:
        def list_entries(self, limit: int, metadata_filters: dict[str, object]):
            assert metadata_filters == {"session_id": "s1"}
            return [
                {
                    "id": "m1",
                    "text": "hello",
                    "metadata": {
                        "session_id": "s1",
                        "user_id": "u1",
                        "timestamp": "2026-01-01T00:00:00Z",
                    },
                }
            ][:limit]

    logger = SimpleNamespace(warning=lambda *_args, **_kwargs: None)
    payload = svc.build_memory_graph_payload(
        vector_store=_Vector(),
        lessons_store=None,
        options=svc.MemoryGraphPayloadOptions(
            limit=10,
            session_id="s1",
            only_pinned=False,
            include_lessons=False,
            mode="flow",
            view="full",
            seed_id=None,
            max_hops=2,
            include_isolates=True,
            limit_nodes=None,
        ),
        apply_graph_view_fn=lambda **kwargs: (kwargs["nodes"], kwargs["edges"]),
        allow_lessons_fallback=False,
        logger=logger,
    )
    assert payload["status"] == "success"
    assert payload["stats"]["source_nodes"] >= 3
    assert payload["stats"]["source_edges"] >= 2
