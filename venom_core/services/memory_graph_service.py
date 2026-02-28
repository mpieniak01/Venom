"""Memory graph and ingestion helper services extracted from API router."""

from __future__ import annotations

import inspect
from collections import Counter
from threading import Lock
from typing import Any, Callable

from fastapi import HTTPException

from venom_core.core.knowledge_contract import KnowledgeKind
from venom_core.core.knowledge_ttl import compute_expires_at, resolve_ttl_days
from venom_core.memory.lessons_store import LessonsStore
from venom_core.utils.helpers import get_utc_now_iso

DEFAULT_USER_ID = "user_default"
_memory_graph_view_counters: Counter[str] = Counter()
_memory_graph_view_counters_lock = Lock()


def require_nonempty(value: str, detail: str) -> None:
    if not value or not value.strip():
        raise HTTPException(status_code=400, detail=detail)


def build_ingest_metadata(request: Any) -> dict[str, object]:
    metadata: dict[str, object] = {"category": request.category}
    optional_fields: list[tuple[str, object | None]] = [
        ("session_id", request.session_id),
        ("user_id", request.user_id),
        ("type", request.memory_type),
        ("scope", request.scope),
        ("topic", request.topic),
        ("timestamp", request.timestamp),
    ]
    for key, value in optional_fields:
        if value:
            metadata[key] = value
    if request.pinned is not None:
        metadata["pinned"] = bool(request.pinned)

    scope = str(request.scope or ("session" if request.session_id else "global"))
    created_at = str(request.timestamp or get_utc_now_iso())
    ttl_days = resolve_ttl_days(KnowledgeKind.MEMORY_ENTRY, scope)
    metadata.update(
        {
            "knowledge_contract_version": "v1",
            "provenance_source": "vector_store",
            "provenance_request_id": None,
            "provenance_intent": None,
            "retention_scope": scope,
            "timestamp": created_at,
            "retention_expires_at": compute_expires_at(created_at, ttl_days),
        }
    )
    return metadata


def raise_memory_http_error(exc: Exception, *, context: str, logger: Any) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.exception("Błąd podczas %s", context)
    raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(exc)}") from exc


def normalize_lessons_for_graph(
    raw_lessons: object,
    allow_fallback: bool,
    limit: int,
) -> list[dict[str, object]]:
    if not raw_lessons:
        return []
    if isinstance(raw_lessons, dict):
        return normalize_lessons_mapping(raw_lessons, limit=limit)
    if isinstance(raw_lessons, list):
        return normalize_lessons_list(
            raw_lessons, allow_fallback=allow_fallback, limit=limit
        )
    return []


def extract_lesson_id(default_id: object, lesson_data: object) -> object:
    if hasattr(lesson_data, "id"):
        return lesson_data.id
    if isinstance(lesson_data, dict) and "id" in lesson_data:
        return lesson_data["id"]
    if hasattr(lesson_data, "lesson_id"):
        return lesson_data.lesson_id
    if isinstance(lesson_data, dict) and "lesson_id" in lesson_data:
        return lesson_data["lesson_id"]
    return default_id


def to_lesson_dict(lesson_data: object) -> dict[str, object] | None:
    if isinstance(lesson_data, dict):
        return dict(lesson_data)
    if hasattr(lesson_data, "to_dict"):
        raw = lesson_data.to_dict()
        if isinstance(raw, dict):
            return dict(raw)
        return None
    if hasattr(lesson_data, "__dict__"):
        return dict(vars(lesson_data))
    return None


def normalize_lessons_mapping(
    raw_lessons: dict[object, object], limit: int
) -> list[dict[str, object]]:
    lessons: list[dict[str, object]] = []
    for default_id, lesson_data in list(raw_lessons.items())[:limit]:
        normalized = to_lesson_dict(lesson_data)
        if normalized is None:
            continue
        normalized["id"] = extract_lesson_id(default_id, lesson_data)
        lessons.append(normalized)
    return lessons


def normalize_lessons_list(
    raw_lessons: list[object], allow_fallback: bool, limit: int
) -> list[dict[str, object]]:
    lessons: list[dict[str, object]] = []
    for entry in raw_lessons[:limit]:
        if isinstance(entry, dict):
            lessons.append(dict(entry))
            continue
        if not allow_fallback:
            continue
        normalized = to_lesson_dict(entry)
        if normalized is not None:
            lessons.append(normalized)
    return lessons


def build_memory_graph_filters(session_id: str, only_pinned: bool) -> dict[str, object]:
    filters: dict[str, object] = {}
    if session_id:
        filters["session_id"] = session_id
    if only_pinned:
        filters["pinned"] = True
    return filters


def increment_memory_view_counter(view: str) -> None:
    with _memory_graph_view_counters_lock:
        _memory_graph_view_counters[view] += 1


def memory_view_counter_snapshot() -> dict[str, int]:
    with _memory_graph_view_counters_lock:
        return dict(_memory_graph_view_counters)


def entry_id(entry: dict[str, Any], meta: dict[str, Any]) -> str:
    raw_id = entry.get("id") or meta.get("id") or meta.get("uuid") or meta.get("pk")
    if raw_id:
        return str(raw_id)
    return f"mem-{abs(hash(entry.get('text', '')))}"


def build_memory_node(
    entry: dict[str, Any], default_user_id: str = DEFAULT_USER_ID
) -> dict[str, Any]:
    meta = entry.get("metadata") or {}
    eid = entry_id(entry, meta)
    label = meta.get("title") or (entry.get("text") or "")[:80] or eid
    sess = meta.get("session_id")
    user = meta.get("user_id") or default_user_id
    node_payload: dict[str, Any] = {
        "data": {
            "id": eid,
            "label": label,
            "type": "memory",
            "memory_kind": meta.get("type") or "fact",
            "session_id": sess,
            "user_id": user,
            "scope": meta.get("scope") or ("session" if sess else "global"),
            "pinned": bool(meta.get("pinned")),
            "topic": meta.get("topic"),
            "meta": meta,
        }
    }
    if "x" in meta and "y" in meta:
        node_payload["position"] = {"x": meta.get("x"), "y": meta.get("y")}
    return node_payload


async def resolve_maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def ensure_session_node(
    session_nodes: dict[str, dict[str, Any]], session_id: str | None
) -> None:
    if not session_id or session_id in session_nodes:
        return
    session_nodes[session_id] = {
        "data": {
            "id": f"session:{session_id}",
            "label": session_id,
            "type": "memory",
            "memory_kind": "session",
            "session_id": session_id,
        }
    }


def ensure_user_node(
    user_nodes: dict[str, dict[str, Any]], user_id: str | None
) -> None:
    if not user_id or user_id in user_nodes:
        return
    user_nodes[user_id] = {
        "data": {
            "id": f"user:{user_id}",
            "label": user_id,
            "type": "memory",
            "memory_kind": "user",
            "user_id": user_id,
        }
    }


def build_relation_edges(
    node_id: str, session_id: str | None, user_id: str | None
) -> list[dict[str, Any]]:
    relation_edges: list[dict[str, Any]] = []
    if session_id:
        relation_edges.append(
            {
                "data": {
                    "id": f"edge:{session_id}->{node_id}",
                    "source": f"session:{session_id}",
                    "target": node_id,
                    "label": "session",
                    "type": "memory",
                }
            }
        )
    if user_id:
        relation_edges.append(
            {
                "data": {
                    "id": f"edge:{user_id}->{node_id}",
                    "source": f"user:{user_id}",
                    "target": node_id,
                    "label": "user",
                    "type": "memory",
                }
            }
        )
    return relation_edges


def get_raw_lessons_for_graph(
    lessons_store: LessonsStore, limit: int
) -> list[Any] | dict[str, Any]:
    if hasattr(lessons_store, "get_all_lessons"):
        return lessons_store.get_all_lessons(limit=limit)
    if hasattr(lessons_store, "lessons"):
        return lessons_store.lessons
    return []


def coerce_lesson_to_dict(raw_lesson: Any) -> dict[str, Any]:
    if isinstance(raw_lesson, dict):
        return raw_lesson
    if hasattr(raw_lesson, "to_dict"):
        return raw_lesson.to_dict()
    if hasattr(raw_lesson, "__dict__"):
        return vars(raw_lesson)
    return {}


def collect_lesson_graph(
    lessons_store: LessonsStore | None,
    limit: int,
    *,
    allow_fallback: bool,
    logger: Any,
    default_user_id: str = DEFAULT_USER_ID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lesson_nodes: list[dict[str, Any]] = []
    lesson_edges: list[dict[str, Any]] = []
    if not lessons_store:
        return lesson_nodes, lesson_edges
    try:
        raw_lessons = get_raw_lessons_for_graph(lessons_store, limit)
        lessons = normalize_lessons_for_graph(
            raw_lessons, allow_fallback=allow_fallback, limit=limit
        )

        for raw_lesson in lessons:
            lesson_data = coerce_lesson_to_dict(raw_lesson)
            raw_id = lesson_data.get("id") or lesson_data.get("lesson_id")
            lesson_id = str(raw_id) if raw_id is not None else ""
            if not lesson_id:
                continue
            label = lesson_data.get("title") or lesson_id
            lesson_nodes.append(
                {
                    "data": {
                        "id": f"lesson:{lesson_id}",
                        "label": label,
                        "type": "memory",
                        "memory_kind": "lesson",
                        "lesson_id": lesson_id,
                        "meta": {
                            "tags": lesson_data.get("tags"),
                            "timestamp": lesson_data.get("timestamp"),
                        },
                    }
                }
            )
            lesson_edges.append(
                {
                    "data": {
                        "id": f"edge:lesson:{lesson_id}->user:{default_user_id}",
                        "source": f"lesson:{lesson_id}",
                        "target": f"user:{default_user_id}",
                        "label": "lesson",
                        "type": "lesson",
                    }
                }
            )
    except Exception as exc:  # pragma: no cover
        logger.warning(f"Nie udało się pobrać lekcji do grafu: {exc}")
    return lesson_nodes, lesson_edges


def append_flow_edges(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    try:

        def _flow_timestamp(node: dict[str, Any]) -> str:
            meta_value = node.get("data", {}).get("meta")
            meta = meta_value if isinstance(meta_value, dict) else {}
            return str(meta.get("timestamp", ""))

        entries_for_flow = sorted(nodes, key=_flow_timestamp)
    except Exception:
        entries_for_flow = nodes

    for idx in range(len(entries_for_flow) - 1):
        src = entries_for_flow[idx]["data"]["id"]
        tgt = entries_for_flow[idx + 1]["data"]["id"]
        edges.append(
            {
                "data": {
                    "id": f"flow:{src}->{tgt}",
                    "source": src,
                    "target": tgt,
                    "label": "next",
                    "type": "flow",
                }
            }
        )


def build_memory_graph_payload(
    *,
    vector_store: Any,
    lessons_store: LessonsStore | None,
    limit: int,
    session_id: str,
    only_pinned: bool,
    include_lessons: bool,
    mode: str,
    view: str,
    seed_id: str | None,
    max_hops: int,
    include_isolates: bool,
    limit_nodes: int | None,
    apply_graph_view_fn: Callable[
        ..., tuple[list[dict[str, Any]], list[dict[str, Any]]]
    ],
    allow_lessons_fallback: bool,
    logger: Any,
    default_user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    filters = build_memory_graph_filters(session_id, only_pinned)
    entries = vector_store.list_entries(limit=limit, metadata_filters=filters)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    session_nodes: dict[str, dict[str, Any]] = {}
    user_nodes: dict[str, dict[str, Any]] = {}

    for entry in entries:
        node_payload = build_memory_node(entry, default_user_id=default_user_id)
        nodes.append(node_payload)
        node_data = node_payload["data"]
        node_id = str(node_data["id"])
        sess_raw = node_data.get("session_id")
        user_raw = node_data.get("user_id")
        sess = sess_raw if isinstance(sess_raw, str) else None
        user = user_raw if isinstance(user_raw, str) else None
        ensure_session_node(session_nodes, sess)
        ensure_user_node(user_nodes, user)
        edges.extend(build_relation_edges(node_id, sess, user))

    lesson_nodes: list[dict[str, Any]] = []
    lesson_edges: list[dict[str, Any]] = []
    if include_lessons:
        lesson_nodes, lesson_edges = collect_lesson_graph(
            lessons_store,
            limit,
            allow_fallback=allow_lessons_fallback,
            logger=logger,
            default_user_id=default_user_id,
        )

    all_nodes = (
        list(session_nodes.values()) + list(user_nodes.values()) + nodes + lesson_nodes
    )
    all_edges = edges + lesson_edges

    if mode == "flow":
        append_flow_edges(nodes, all_edges)

    source_nodes = len(all_nodes)
    source_edges = len(all_edges)
    view_nodes, view_edges = apply_graph_view_fn(
        nodes=all_nodes,
        edges=all_edges,
        view=view,
        seed_id=seed_id,
        max_hops=max_hops,
        include_isolates=include_isolates,
        limit_nodes=limit_nodes,
    )
    increment_memory_view_counter(view)

    return {
        "status": "success",
        "view": view,
        "elements": {"nodes": view_nodes, "edges": view_edges},
        "stats": {
            "nodes": len(view_nodes),
            "edges": len(view_edges),
            "source_nodes": source_nodes,
            "source_edges": source_edges,
            "view": view,
            "max_hops": max_hops,
            "seed_id": seed_id,
            "view_requests": memory_view_counter_snapshot(),
        },
    }
