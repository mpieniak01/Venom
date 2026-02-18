"""Moduł: routes/memory - Endpointy API dla pamięci wektorowej."""

import inspect
from collections import Counter, deque
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from venom_core.api.dependencies import (
    get_lessons_store,
    get_session_store,
    get_state_manager,
    get_vector_store,
    is_testing_mode,
)
from venom_core.api.schemas.memory import (
    CacheFlushResponse,
    GlobalMemoryClearResponse,
    LearningStatusResponse,
    LearningToggleRequest,
    LessonsMutationResponse,
    MemoryEntryMutationResponse,
    MemoryGraphResponse,
    MemoryIngestRequest,
    MemoryIngestResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    SessionMemoryClearResponse,
    SessionMemoryResponse,
)
from venom_core.core.knowledge_contract import KnowledgeKind
from venom_core.core.knowledge_ttl import compute_expires_at, resolve_ttl_days
from venom_core.memory.lessons_store import LessonsStore
from venom_core.services.config_manager import config_manager as _config_manager
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
DEFAULT_USER_ID = "user_default"

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])

# Back-compat for tests that patch memory_routes.config_manager
config_manager = _config_manager

INTERNAL_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny"},
}
LESSONS_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    **INTERNAL_ERROR_RESPONSES,
}
LESSONS_MUTATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Nieprawidłowe parametry żądania"},
    **INTERNAL_ERROR_RESPONSES,
}

# Globalne referencje dla testów
_vector_store = None
_state_manager = None
_lessons_store = None
_memory_graph_view_counters: Counter[str] = Counter()


def set_dependencies(
    vector_store=None, state_manager=None, lessons_store=None, session_store=None
):
    """Ustawia zależności i synchronizuje z api.dependencies (używane głównie w testach)."""
    global _vector_store, _state_manager, _lessons_store
    from venom_core.api import dependencies as api_deps

    if vector_store:
        _vector_store = vector_store
        api_deps.set_vector_store(vector_store)
    if state_manager:
        _state_manager = state_manager
        api_deps.set_state_manager(state_manager)
    if lessons_store:
        _lessons_store = lessons_store
        api_deps.set_lessons_store(lessons_store)
    if session_store:
        api_deps.set_session_store(session_store)


def _ensure_vector_store():
    """Pomocnik do pobierania vector store (używany w testach)."""
    from venom_core.api.dependencies import get_vector_store
    from venom_core.memory.vector_store import VectorStore

    try:
        return get_vector_store()
    except Exception:
        if _vector_store:
            return _vector_store
        # W teście, jeśli nikt jeszcze nie ustawiał, stwórz nową instancję
        # (EmbeddingService i tak użyje cache'u)
        return VectorStore()


def _require_nonempty(value: str, detail: str) -> None:
    if not value or not value.strip():
        raise HTTPException(status_code=400, detail=detail)


def _build_ingest_metadata(request: "MemoryIngestRequest") -> dict[str, object]:
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


def _raise_memory_http_error(exc: Exception, *, context: str) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.exception("Błąd podczas %s", context)
    raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(exc)}") from exc


def _normalize_lessons_for_graph(
    raw_lessons: object,
    allow_fallback: bool,
    limit: int,
) -> list[dict[str, object]]:
    if not raw_lessons:
        return []
    if isinstance(raw_lessons, dict):
        return _normalize_lessons_mapping(raw_lessons, limit=limit)
    if isinstance(raw_lessons, list):
        return _normalize_lessons_list(
            raw_lessons, allow_fallback=allow_fallback, limit=limit
        )
    return []


def _extract_lesson_id(default_id: object, lesson_data: object) -> object:
    if hasattr(lesson_data, "id"):
        return lesson_data.id
    if isinstance(lesson_data, dict) and "id" in lesson_data:
        return lesson_data["id"]
    if hasattr(lesson_data, "lesson_id"):
        return lesson_data.lesson_id
    if isinstance(lesson_data, dict) and "lesson_id" in lesson_data:
        return lesson_data["lesson_id"]
    return default_id


def _to_lesson_dict(lesson_data: object) -> dict[str, object] | None:
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


def _normalize_lessons_mapping(
    raw_lessons: dict[object, object], limit: int
) -> list[dict[str, object]]:
    lessons: list[dict[str, object]] = []
    for default_id, lesson_data in list(raw_lessons.items())[:limit]:
        normalized = _to_lesson_dict(lesson_data)
        if normalized is None:
            continue
        normalized["id"] = _extract_lesson_id(default_id, lesson_data)
        lessons.append(normalized)
    return lessons


def _normalize_lessons_list(
    raw_lessons: list[object], allow_fallback: bool, limit: int
) -> list[dict[str, object]]:
    lessons: list[dict[str, object]] = []
    for entry in raw_lessons[:limit]:
        if isinstance(entry, dict):
            lessons.append(dict(entry))
            continue
        if not allow_fallback:
            continue
        normalized = _to_lesson_dict(entry)
        if normalized is not None:
            lessons.append(normalized)
    return lessons


def _build_memory_graph_filters(
    session_id: str, only_pinned: bool
) -> dict[str, object]:
    filters: dict[str, object] = {}
    if session_id:
        filters["session_id"] = session_id
    if only_pinned:
        filters["pinned"] = True
    return filters


def _node_id(node: dict[str, Any]) -> str:
    return str(node.get("data", {}).get("id", ""))


def _edge_nodes(edge: dict[str, Any]) -> tuple[str, str]:
    data = edge.get("data", {})
    return str(data.get("source", "")), str(data.get("target", ""))


def _focus_node_ids(
    edges: list[dict[str, Any]], seed_id: str, max_hops: int
) -> set[str]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        source, target = _edge_nodes(edge)
        if not source or not target:
            continue
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
    visited: set[str] = {seed_id}
    queue: deque[tuple[str, int]] = deque([(seed_id, 0)])
    while queue:
        node_id, hops = queue.popleft()
        if hops >= max_hops:
            continue
        for neighbour in adjacency.get(node_id, set()):
            if neighbour in visited:
                continue
            visited.add(neighbour)
            queue.append((neighbour, hops + 1))
    return visited


def _remove_isolates(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    connected: set[str] = set()
    for edge in edges:
        source, target = _edge_nodes(edge)
        if source:
            connected.add(source)
        if target:
            connected.add(target)
    filtered_nodes = [node for node in nodes if _node_id(node) in connected]
    allowed = {_node_id(node) for node in filtered_nodes}
    filtered_edges = [
        edge
        for edge in edges
        if _edge_nodes(edge)[0] in allowed and _edge_nodes(edge)[1] in allowed
    ]
    return filtered_nodes, filtered_edges


def _apply_memory_view(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    view: str,
    seed_id: str | None,
    max_hops: int,
    include_isolates: bool,
    limit_nodes: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current_nodes = list(nodes)
    current_edges = list(edges)

    if view == "overview":
        cap = limit_nodes if limit_nodes is not None else min(len(current_nodes), 200)
        current_nodes = current_nodes[:cap]
        allowed = {_node_id(node) for node in current_nodes}
        current_edges = [
            edge
            for edge in current_edges
            if _edge_nodes(edge)[0] in allowed and _edge_nodes(edge)[1] in allowed
        ]
    elif view == "focus" and current_nodes:
        resolved_seed = seed_id or _node_id(current_nodes[0])
        focus_ids = _focus_node_ids(current_edges, resolved_seed, max_hops)
        current_nodes = [node for node in current_nodes if _node_id(node) in focus_ids]
        allowed = {_node_id(node) for node in current_nodes}
        current_edges = [
            edge
            for edge in current_edges
            if _edge_nodes(edge)[0] in allowed and _edge_nodes(edge)[1] in allowed
        ]
        if limit_nodes is not None and limit_nodes > 0:
            current_nodes = current_nodes[:limit_nodes]
            allowed = {_node_id(node) for node in current_nodes}
            current_edges = [
                edge
                for edge in current_edges
                if _edge_nodes(edge)[0] in allowed and _edge_nodes(edge)[1] in allowed
            ]

    if not include_isolates:
        current_nodes, current_edges = _remove_isolates(current_nodes, current_edges)

    return current_nodes, current_edges


def _entry_id(entry: dict[str, Any], meta: dict[str, Any]) -> str:
    raw_id = entry.get("id") or meta.get("id") or meta.get("uuid") or meta.get("pk")
    if raw_id:
        return str(raw_id)
    return f"mem-{abs(hash(entry.get('text', '')))}"


def _build_memory_node(entry: dict[str, Any]) -> dict[str, Any]:
    meta = entry.get("metadata") or {}
    eid = _entry_id(entry, meta)
    label = meta.get("title") or (entry.get("text") or "")[:80] or eid
    sess = meta.get("session_id")
    user = meta.get("user_id") or DEFAULT_USER_ID
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


async def _resolve_maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _ensure_session_node(
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


def _ensure_user_node(
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


def _build_relation_edges(
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


def _collect_lesson_graph(
    lessons_store: LessonsStore | None, limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lesson_nodes: list[dict[str, Any]] = []
    lesson_edges: list[dict[str, Any]] = []
    if not lessons_store:
        return lesson_nodes, lesson_edges
    try:
        raw_lessons = _get_raw_lessons_for_graph(lessons_store, limit)
        lessons = _normalize_lessons_for_graph(
            raw_lessons, allow_fallback=is_testing_mode(), limit=limit
        )

        for raw_lesson in lessons:
            lesson_data = _coerce_lesson_to_dict(raw_lesson)
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
                        "id": f"edge:lesson:{lesson_id}->user:{DEFAULT_USER_ID}",
                        "source": f"lesson:{lesson_id}",
                        "target": f"user:{DEFAULT_USER_ID}",
                        "label": "lesson",
                        "type": "lesson",
                    }
                }
            )
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się pobrać lekcji do grafu: {e}")
    return lesson_nodes, lesson_edges


def _get_raw_lessons_for_graph(
    lessons_store: LessonsStore, limit: int
) -> list[Any] | dict[str, Any]:
    if hasattr(lessons_store, "get_all_lessons"):
        return lessons_store.get_all_lessons(limit=limit)
    if hasattr(lessons_store, "lessons"):
        return lessons_store.lessons
    return []


def _coerce_lesson_to_dict(raw_lesson: Any) -> dict[str, Any]:
    if isinstance(raw_lesson, dict):
        return raw_lesson
    if hasattr(raw_lesson, "to_dict"):
        return raw_lesson.to_dict()
    if hasattr(raw_lesson, "__dict__"):
        return vars(raw_lesson)
    return {}


def _append_flow_edges(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> None:
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


# Modele i Stałe
DEFAULT_USER_ID = "user_default"


@router.post(
    "/ingest",
    response_model=MemoryIngestResponse,
    status_code=201,
    responses={
        400: {"description": "Nieprawidłowe dane wejściowe"},
        500: {"description": "Błąd wewnętrzny podczas zapisu do pamięci"},
    },
)
def ingest_to_memory(
    request: MemoryIngestRequest,
    vector_store: Annotated[Any, Depends(get_vector_store)],
):
    """
    Zapisuje tekst do pamięci wektorowej.

    Args:
        request: Żądanie z tekstem do zapamiętania

    Returns:
        Potwierdzenie zapisu z liczbą fragmentów

    Raises:
        HTTPException: 503 jeśli VectorStore nie jest dostępny, 400 przy błędnych danych
    """
    try:
        _require_nonempty(request.text, "Tekst nie może być pusty")
        metadata = _build_ingest_metadata(request)
        result = vector_store.upsert(
            text=request.text,
            metadata=metadata,
            collection_name=request.collection,
            chunk_text=True,
        )

        logger.info(
            f"Ingestion pomyślny: {result['chunks_count']} fragmentów do '{request.collection}'"
        )

        return MemoryIngestResponse(
            status="success",
            message=result["message"],
            chunks_count=result["chunks_count"],
        )

    except Exception as exc:
        _raise_memory_http_error(exc, context="ingestion do pamięci")


@router.post(
    "/search",
    response_model=MemorySearchResponse,
    responses={
        400: {"description": "Nieprawidłowe zapytanie"},
        500: {"description": "Błąd wewnętrzny podczas wyszukiwania"},
    },
)
def search_memory(
    request: MemorySearchRequest,
    vector_store: Annotated[Any, Depends(get_vector_store)],
):
    """
    Wyszukuje informacje w pamięci wektorowej.

    Args:
        request: Żądanie z zapytaniem

    Returns:
        Wyniki wyszukiwania

    Raises:
        HTTPException: 503 jeśli VectorStore nie jest dostępny, 400 przy błędnych danych
    """
    try:
        _require_nonempty(
            request.query,
            "Zapytanie nie może być puste (pusty prompt niedozwolony)",
        )

        results = vector_store.search(
            query=request.query,
            limit=request.limit,
            collection_name=request.collection,
        )

        logger.info(
            f"Wyszukiwanie w pamięci: znaleziono {len(results)} wyników dla '{request.query[:50]}...'"
        )

        return {
            "status": "success",
            "query": request.query,
            "results": results,
            "count": len(results),
        }

    except Exception as exc:
        _raise_memory_http_error(exc, context="wyszukiwania w pamięci")


@router.delete(
    "/session/{session_id}",
    response_model=SessionMemoryClearResponse,
    responses={
        400: {"description": "Brak wymaganego session_id"},
    },
)
def clear_session_memory(
    session_id: str,
    vector_store: Annotated[Any, Depends(get_vector_store)],
    state_manager: Annotated[Any, Depends(get_state_manager)],
    session_store: Annotated[Any, Depends(get_session_store)],
):
    """
    Czyści pamięć sesyjną: wektory z tagiem session_id oraz historię/streszczenia w StateManager.
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id jest wymagane")

    deleted_vectors = 0
    try:
        deleted_vectors = vector_store.delete_by_metadata({"session_id": session_id})
        deleted_vectors += vector_store.delete_session(session_id)
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się usunąć wpisów sesyjnych z pamięci: {e}")

    cleared_tasks = 0
    if state_manager:
        cleared_tasks = state_manager.clear_session_context(session_id)
    if session_store:
        session_store.clear_session(session_id)

    return {
        "status": "success",
        "session_id": session_id,
        "deleted_vectors": deleted_vectors,
        "cleared_tasks": cleared_tasks,
        "message": "Pamięć sesji wyczyszczona",
    }


@router.get(
    "/session/{session_id}",
    response_model=SessionMemoryResponse,
    responses={
        400: {"description": "Brak wymaganego session_id"},
        503: {"description": "SessionStore nie jest dostępny"},
    },
)
def get_session_memory(
    session_id: str,
    session_store: Annotated[Any, Depends(get_session_store)],
):
    """Zwraca historię i streszczenie sesji z SessionStore."""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id jest wymagane")
    if not session_store:
        raise HTTPException(status_code=503, detail="SessionStore nie jest dostępny")

    history = session_store.get_history(session_id)
    summary = session_store.get_summary(session_id)
    return {
        "status": "success",
        "session_id": session_id,
        "history": history,
        "summary": summary,
        "count": len(history),
    }


@router.delete(
    "/global",
    response_model=GlobalMemoryClearResponse,
    responses={
        500: {"description": "Błąd podczas czyszczenia pamięci globalnej"},
    },
)
def clear_global_memory(vector_store: Annotated[Any, Depends(get_vector_store)]):
    """
    Czyści pamięć globalną (preferencje/fakty globalne użytkownika).
    """
    try:
        deleted = vector_store.delete_by_metadata({"user_id": DEFAULT_USER_ID})
        # Jeśli nie znaleziono nic do usunięcia (np. stare wpisy bez metadanych user_id),
        # wyczyść całą kolekcję, aby użytkownik faktycznie widział pustą pamięć.
        if not deleted:
            deleted += vector_store.wipe_collection()
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się usunąć pamięci globalnej: {e}")
        raise HTTPException(
            status_code=500, detail="Błąd czyszczenia pamięci globalnej"
        ) from e

    return {
        "status": "success",
        "deleted_vectors": deleted,
        "message": "Pamięć globalna wyczyszczona",
    }


@router.get(
    "/graph",
    response_model=MemoryGraphResponse,
    responses=INTERNAL_ERROR_RESPONSES,
)
def memory_graph(
    vector_store: Annotated[Any, Depends(get_vector_store)],
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    session_id: Annotated[
        str, Query(description="Opcjonalny filtr po session_id")
    ] = "",
    only_pinned: Annotated[
        bool, Query(description="Zwracaj tylko wpisy z meta pinned=true")
    ] = False,
    include_lessons: Annotated[
        bool, Query(description="Czy dołączyć lekcje z LessonsStore")
    ] = False,
    mode: Annotated[
        str, Query(description="Tryb grafu: default lub flow (sekwencja)")
    ] = "default",
    view: Annotated[
        str,
        Query(
            pattern="^(overview|focus|full)$",
            description="Tryb zwracanego grafu: overview/focus/full",
        ),
    ] = "full",
    seed_id: Annotated[
        str | None,
        Query(description="Opcjonalny seed node id dla widoku focus"),
    ] = None,
    max_hops: Annotated[
        int,
        Query(ge=1, le=6, description="Maksymalna głębokość dla widoku focus"),
    ] = 2,
    include_isolates: Annotated[
        bool,
        Query(description="Czy zachować węzły bez krawędzi"),
    ] = True,
    limit_nodes: Annotated[
        int | None,
        Query(
            ge=1,
            le=5000,
            description="Opcjonalny limit po transformacji widoku (overview/focus)",
        ),
    ] = None,
):
    """
    Zwraca uproszczony graf pamięci (węzły/krawędzie) do wizualizacji w /brain.
    """
    _ = vector_store  # Ensure it is used
    filters = _build_memory_graph_filters(session_id, only_pinned)
    entries = vector_store.list_entries(limit=limit, metadata_filters=filters)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    session_nodes: dict[str, dict[str, Any]] = {}
    user_nodes: dict[str, dict[str, Any]] = {}

    for entry in entries:
        node_payload = _build_memory_node(entry)
        nodes.append(node_payload)
        node_data = node_payload["data"]
        node_id = str(node_data["id"])
        sess = node_data.get("session_id")
        user = node_data.get("user_id")
        _ensure_session_node(session_nodes, sess if isinstance(sess, str) else None)
        _ensure_user_node(user_nodes, user if isinstance(user, str) else None)
        edges.extend(
            _build_relation_edges(
                node_id,
                sess if isinstance(sess, str) else None,
                user if isinstance(user, str) else None,
            )
        )

    lesson_nodes: list[dict[str, Any]] = []
    lesson_edges: list[dict[str, Any]] = []
    if include_lessons:
        lesson_nodes, lesson_edges = _collect_lesson_graph(lessons_store, limit)

    all_nodes = (
        list(session_nodes.values()) + list(user_nodes.values()) + nodes + lesson_nodes
    )
    all_edges = edges + lesson_edges

    if mode == "flow":
        # Dodaj krawędzie sekwencyjne (prosty tok) wg metadanej timestamp, fallback: kolejność entries
        _append_flow_edges(nodes, all_edges)

    source_nodes = len(all_nodes)
    source_edges = len(all_edges)
    view_nodes, view_edges = _apply_memory_view(
        nodes=all_nodes,
        edges=all_edges,
        view=view,
        seed_id=seed_id,
        max_hops=max_hops,
        include_isolates=include_isolates,
        limit_nodes=limit_nodes,
    )
    _memory_graph_view_counters[view] += 1

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
            "view_requests": dict(_memory_graph_view_counters),
        },
    }


@router.post(
    "/entry/{entry_id}/pin",
    response_model=MemoryEntryMutationResponse,
    responses={
        404: {"description": "Nie znaleziono wpisu pamięci"},
        500: {"description": "Błąd aktualizacji wpisu pamięci"},
    },
)
def pin_memory_entry(
    entry_id: str,
    vector_store: Annotated[Any, Depends(get_vector_store)],
    pinned: Annotated[bool, Query(description="Czy oznaczyć pinned")] = True,
):
    """
    Ustawia flagę pinned dla wpisu pamięci (w oparciu o LanceDB).
    """
    try:
        ok = vector_store.update_metadata(entry_id, {"pinned": bool(pinned)})
        if not ok:
            raise HTTPException(status_code=404, detail="Nie znaleziono wpisu pamięci")
        return {"status": "success", "entry_id": entry_id, "pinned": bool(pinned)}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się zaktualizować wpisu pamięci: {e}")
        raise HTTPException(
            status_code=500, detail="Błąd aktualizacji wpisu pamięci"
        ) from e


@router.delete(
    "/entry/{entry_id}",
    response_model=MemoryEntryMutationResponse,
    responses={
        404: {"description": "Nie znaleziono wpisu do usunięcia"},
        500: {"description": "Błąd usuwania wpisu pamięci"},
    },
)
def delete_memory_entry(
    entry_id: str,
    vector_store: Annotated[Any, Depends(get_vector_store)],
):
    """
    Usuwa wpis pamięci (oraz wszystkie jego fragmenty).
    """
    try:
        deleted = vector_store.delete_entry(entry_id)
        if deleted == 0:
            raise HTTPException(
                status_code=404, detail="Nie znaleziono wpisu do usunięcia"
            )
        return {"status": "success", "entry_id": entry_id, "deleted": deleted}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się usunąć wpisu pamięci: {e}")
        raise HTTPException(
            status_code=500, detail="Błąd usuwania wpisu pamięci"
        ) from e


# ============================================
# Pruning API - Knowledge Hygiene Suite
# ============================================


@router.delete(
    "/cache/semantic",
    response_model=CacheFlushResponse,
    responses={
        500: {"description": "Błąd podczas czyszczenia Semantic Cache"},
    },
)
def flush_semantic_cache():
    """
    Czyści Semantic Cache (kolekcja hidden_prompts).
    Usuwa wszystkie zapamiętane pary prompt-odpowiedź używane do semantycznego cache'owania.
    """
    try:
        from venom_core.core.orchestrator.constants import (
            SEMANTIC_CACHE_COLLECTION_NAME,
        )

        # Używamy wipe_collection na konkretnej kolekcji
        # Metoda wipe_collection w VectorStore domyślnie czyści self.collection_name,
        # więc musimy upewnić się, że działamy na odpowiedniej.
        # VectorStore.wipe_collection() często czyści *aktualną*.
        # Bezpieczniej będzie użyć delete_by_metadata(filter={}) na tej kolekcji lub delete_collection.
        # Sprawdźmy implementation VectorStore.wipe_collection...
        # Wg routes/memory.py: vector_store.wipe_collection()
        # Ale semantic cache to INNA kolekcja niż 'default'.
        # VectorStore inicjalizuje się z default collection.
        # Żeby wyczyścić semantic cache, musimy tymczasowo zmienić kolekcję lub użyć dedykowanej metody.
        # VectorStore pozwala na upsert z collection_name, a search z collection_name, ale wipe_collection?
        # Zobaczmy czy w memory.py jest coś co zmienia kolekcję.
        # Nie widać.
        # Zróbmy to bezpiecznie: delete_by_metadata({}) na kolekcji cache.
        # UWAGA: VectorStore API może nie wspierać collection_name w delete_by_metadata.
        # W takim razie zainicjalizujmy VectorStore explicite dla tej kolekcji.
        from venom_core.memory.vector_store import VectorStore

        cache_store = VectorStore(collection_name=SEMANTIC_CACHE_COLLECTION_NAME)
        deleted = (
            cache_store.wipe_collection()
        )  # To powinno zadziałać na 'hidden_prompts'

        logger.warning(f"🧹 FLUSH: Wyczyszczono Semantic Cache ({deleted} wpisów)")

        return {
            "status": "success",
            "message": f"Wyczyszczono Semantic Cache ({deleted} wpisów)",
            "deleted": deleted,
        }

    except Exception as e:
        logger.exception("Błąd podczas czyszczenia Semantic Cache")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas czyszczenia cache: {str(e)}"
        ) from e


# ============================================
# Pruning API - Knowledge Hygiene Suite
# (Aliases for backward compatibility)
# ============================================


@router.delete(
    "/lessons/prune/latest",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def prune_latest_lessons(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    count: Annotated[
        int, Query(ge=1, description="Liczba najnowszych lekcji do usunięcia")
    ],
):
    """Alias dla knowledge/lessons/prune/latest"""
    from venom_core.api.routes.knowledge import prune_latest_lessons as knowledge_prune

    result = knowledge_prune(count=count, lessons_store=lessons_store)
    return await _resolve_maybe_await(result)


@router.delete(
    "/lessons/prune/range",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def prune_lessons_by_range(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    start: Annotated[str, Query(description="Data początkowa")],
    end: Annotated[str, Query(description="Data końcowa")],
):
    """Alias dla knowledge/lessons/prune/range"""
    from venom_core.api.routes.knowledge import (
        prune_lessons_by_range as knowledge_prune,
    )

    result = knowledge_prune(start=start, end=end, lessons_store=lessons_store)
    return await _resolve_maybe_await(result)


@router.delete(
    "/lessons/prune/tag",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def prune_lessons_by_tag(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    tag: Annotated[str, Query(description="Tag do usunięcia")],
):
    """Alias dla knowledge/lessons/prune/tag"""
    from venom_core.api.routes.knowledge import prune_lessons_by_tag as knowledge_prune

    result = knowledge_prune(tag=tag, lessons_store=lessons_store)
    return await _resolve_maybe_await(result)


@router.delete(
    "/lessons/prune/ttl",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def prune_lessons_by_ttl(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    days: Annotated[int, Query(ge=1, description="Dni retencji")],
):
    """Alias dla knowledge/lessons/prune/ttl"""
    from venom_core.api.routes.knowledge import prune_lessons_by_ttl as knowledge_prune

    result = knowledge_prune(days=days, lessons_store=lessons_store)
    return await _resolve_maybe_await(result)


@router.delete(
    "/lessons/purge",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def purge_all_lessons(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    force: Annotated[
        bool, Query(description="Wymagane potwierdzenie dla operacji nuklearnej")
    ] = False,
):
    """Alias dla knowledge/lessons/purge"""
    from venom_core.api.routes.knowledge import purge_all_lessons as knowledge_purge

    result = knowledge_purge(force=force, lessons_store=lessons_store)
    return await _resolve_maybe_await(result)


@router.get(
    "/lessons/learning/status",
    response_model=LearningStatusResponse,
    responses=LESSONS_READ_RESPONSES,
)
async def get_learning_status():
    """Alias dla knowledge/lessons/learning/status"""
    from venom_core.api.routes.knowledge import get_learning_status as knowledge_status

    return await _resolve_maybe_await(knowledge_status())


@router.post(
    "/lessons/learning/toggle",
    response_model=LearningStatusResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def toggle_learning(request: LearningToggleRequest):
    """Alias dla knowledge/lessons/learning/toggle"""
    from venom_core.api.routes.knowledge import (
        LearningToggleRequest as KnowledgeRequest,
    )
    from venom_core.api.routes.knowledge import toggle_learning as knowledge_toggle

    result = knowledge_toggle(KnowledgeRequest(enabled=request.enabled))
    return await _resolve_maybe_await(result)
