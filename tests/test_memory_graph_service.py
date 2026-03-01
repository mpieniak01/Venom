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


@pytest.mark.asyncio
async def test_memory_graph_low_level_helpers_and_branches() -> None:
    assert svc.normalize_lessons_for_graph(None, allow_fallback=False, limit=5) == []
    assert svc.normalize_lessons_for_graph("bad", allow_fallback=True, limit=5) == []

    lesson_obj = SimpleNamespace(id="a1", lesson_id="b1")
    assert svc.extract_lesson_id("x", lesson_obj) == "a1"
    assert svc.extract_lesson_id("x", {"lesson_id": "b2"}) == "b2"
    assert svc.extract_lesson_id("fallback", object()) == "fallback"

    class _ToDict:
        def to_dict(self):
            return {"id": "k1"}

    assert svc.to_lesson_dict({"id": "1"}) == {"id": "1"}
    assert svc.to_lesson_dict(_ToDict()) == {"id": "k1"}
    assert svc.to_lesson_dict(42) is None

    mapping = svc.normalize_lessons_mapping({"d1": {"title": "t"}}, limit=2)
    assert mapping[0]["id"] == "d1"
    lst = svc.normalize_lessons_list(
        [SimpleNamespace(x=1)], allow_fallback=False, limit=1
    )
    assert lst == []
    lst2 = svc.normalize_lessons_list(
        [SimpleNamespace(x=1)], allow_fallback=True, limit=1
    )
    assert lst2[0]["x"] == 1

    assert svc.entry_id({"text": "abc"}, {})[:4] == "mem-"
    assert svc.coerce_lesson_to_dict(SimpleNamespace(a=1))["a"] == 1

    async def _ret():
        return "ok"

    assert await svc.resolve_maybe_await(_ret()) == "ok"
    assert await svc.resolve_maybe_await("raw") == "raw"


def test_memory_graph_lessons_store_and_error_paths() -> None:
    store_with_attr = SimpleNamespace(lessons={"x": {"id": "x"}})
    assert svc.get_raw_lessons_for_graph(store_with_attr, 10) == {"x": {"id": "x"}}
    assert svc.get_raw_lessons_for_graph(SimpleNamespace(), 10) == []

    warns: list[str] = []
    nodes, edges = svc.collect_lesson_graph(
        SimpleNamespace(
            get_all_lessons=lambda limit: (_ for _ in ()).throw(RuntimeError("boom"))
        ),
        10,
        allow_fallback=True,
        logger=SimpleNamespace(warning=lambda msg, *_a, **_kw: warns.append(msg)),
    )
    assert nodes == []
    assert edges == []
    assert warns
