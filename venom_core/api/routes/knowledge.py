"""Moduł: routes/knowledge - Endpointy API dla graph i lessons."""

from collections import Counter
from datetime import datetime, timezone
from pathlib import PurePosixPath
from threading import Lock
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from venom_core.api.dependencies import (
    get_graph_store,
    get_lessons_store,
    get_session_store,
    get_vector_store,
)
from venom_core.api.routes.graph_view_utils import apply_graph_view
from venom_core.api.schemas.knowledge import LearningToggleRequest
from venom_core.config import SETTINGS
from venom_core.core.knowledge_adapters import (
    from_lesson,
    from_session_store_entry,
    from_vector_entry,
)
from venom_core.core.knowledge_contract import (
    KnowledgeContextMapV1,
    KnowledgeLinkV1,
    KnowledgeRecordV1,
)
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.memory.lessons_store import LessonsStore
from venom_core.services.config_manager import config_manager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["knowledge"])

_graph_store = None
_lessons_store = None
INTERNAL_ERROR_DETAIL = "Błąd wewnętrzny"
INVALID_FILE_PATH_DETAIL = "Nieprawidłowa ścieżka pliku"
BAD_REQUEST_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": INVALID_FILE_PATH_DETAIL},
}
INTERNAL_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": INTERNAL_ERROR_DETAIL},
}
GRAPH_FILE_ROUTE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **BAD_REQUEST_RESPONSES,
    **INTERNAL_ERROR_RESPONSES,
}
LESSONS_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    **INTERNAL_ERROR_RESPONSES,
}
LESSONS_MUTATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Nieprawidłowe parametry żądania"},
    **INTERNAL_ERROR_RESPONSES,
}

NODE_TYPE_FILE = "file"
NODE_TYPE_CLASS = "class"
NODE_TYPE_FUNCTION = "function"
NODE_TYPE_METHOD = "method"
_graph_view_counters: Counter[str] = Counter()
_graph_view_counters_lock = Lock()


def _normalize_graph_file_path(file_path: str) -> str:
    """
    Normalizuje ścieżkę pliku z URL i odrzuca niebezpieczne formaty.
    """
    normalized = file_path.strip().replace("\\", "/")
    if not normalized:
        raise HTTPException(status_code=400, detail=INVALID_FILE_PATH_DETAIL)
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise HTTPException(status_code=400, detail=INVALID_FILE_PATH_DETAIL)
    return str(path)


def _resolve_node_presentation(
    node_id: str, node_data: dict[str, Any]
) -> tuple[str, str]:
    node_type = node_data.get("type", "unknown")
    node_name = node_data.get("name", node_id)
    if node_type == NODE_TYPE_FILE:
        return "file", node_data.get("path", node_name)
    if node_type == NODE_TYPE_CLASS:
        file_path = node_data.get("file", "")
        category = (
            "agent"
            if "agents" in file_path or node_data.get("is_agent", False)
            else "class"
        )
        return category, node_name
    if node_type in (NODE_TYPE_FUNCTION, NODE_TYPE_METHOD):
        return "function", node_name
    return "file", node_name


def _build_graph_nodes(graph_store: CodeGraphStore, limit: int) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for node_id, node_data in graph_store.graph.nodes(data=True):
        category, label = _resolve_node_presentation(node_id, node_data)
        nodes.append(
            {
                "data": {
                    "id": node_id,
                    "label": label,
                    "type": category,
                    "original_type": node_data.get("type", "unknown"),
                    "properties": node_data,
                }
            }
        )
        if len(nodes) >= limit:
            break
    return nodes


def _build_graph_edges(
    graph_store: CodeGraphStore, allowed_ids: set[str]
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    edge_id = 0
    for source, target, edge_data in graph_store.graph.edges(data=True):
        if allowed_ids and (source not in allowed_ids or target not in allowed_ids):
            continue
        edge_type = edge_data.get("type", "RELATED")
        edges.append(
            {
                "data": {
                    "id": f"e{edge_id}",
                    "source": source,
                    "target": target,
                    "type": edge_type,
                    "label": edge_type,
                }
            }
        )
        edge_id += 1
    return edges


def _increment_graph_view_counter(view: str) -> None:
    with _graph_view_counters_lock:
        _graph_view_counters[view] += 1


def _graph_view_counter_snapshot() -> dict[str, int]:
    with _graph_view_counters_lock:
        return dict(_graph_view_counters)


def set_dependencies(graph_store=None, lessons_store=None):
    """Ustawia zależności i synchronizuje z api.dependencies (używane głównie w testach)."""
    global _graph_store, _lessons_store
    from venom_core.api import dependencies as api_deps

    if graph_store:
        _graph_store = graph_store
        api_deps.set_graph_store(graph_store)
    if lessons_store:
        _lessons_store = lessons_store
        api_deps.set_lessons_store(lessons_store)


@router.get("/knowledge/graph", responses=INTERNAL_ERROR_RESPONSES)
def get_knowledge_graph(
    graph_store: Annotated[CodeGraphStore, Depends(get_graph_store)],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=5000,
            description="Maksymalna liczba węzłów do zwrócenia (pozostałe są odfiltrowane)",
        ),
    ] = 500,
    view: Annotated[
        str,
        Query(
            pattern="^(overview|focus|full)$",
            description="Tryb zwracanego grafu: overview/focus/full",
        ),
    ] = "full",
    seed_id: Annotated[
        Optional[str],
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
        Optional[int],
        Query(
            ge=1,
            le=5000,
            description="Opcjonalny limit po transformacji widoku (overview/focus)",
        ),
    ] = None,
):
    """
    Zwraca graf wiedzy w formacie Cytoscape Elements JSON.

    UWAGA: Jeśli graf jest pusty, endpoint zwraca przykładowe dane (mock data)
    z flagą "mock": true w odpowiedzi.

    Format zwracany:
    {
        "elements": {
            "nodes": [{"data": {"id": "...", "label": "...", "type": "..."}}],
            "edges": [{"data": {"id": "...", "source": "...", "target": "...", "type": "..."}}]
        }
    }

    Returns:
        Graf w formacie Cytoscape

    Raises:
        HTTPException: 503 jeśli CodeGraphStore nie jest dostępny
    """
    # Jeśli graph_store nie jest dostępny lub jest pusty, zwróć mock data
    if graph_store is None or graph_store.graph.number_of_nodes() == 0:
        logger.info("Graph store pusty lub niedostępny, zwracam mock data")
        return _get_mock_knowledge_graph(
            limit=limit,
            view=view,
            seed_id=seed_id,
            max_hops=max_hops,
            include_isolates=include_isolates,
            limit_nodes=limit_nodes,
        )

    try:
        nodes = _build_graph_nodes(graph_store, limit)
        allowed_ids = {n["data"]["id"] for n in nodes}
        edges = _build_graph_edges(graph_store, allowed_ids)

        view_nodes, view_edges = apply_graph_view(
            nodes=nodes,
            edges=edges,
            view=view,
            seed_id=seed_id,
            max_hops=max_hops,
            include_isolates=include_isolates,
            limit_nodes=limit_nodes,
        )
        _increment_graph_view_counter(view)

        return {
            "status": "success",
            "view": view,
            "elements": {"nodes": view_nodes, "edges": view_edges},
            "stats": {
                "nodes": len(view_nodes),
                "edges": len(view_edges),
                "source_nodes": len(nodes),
                "source_edges": len(edges),
                "view": view,
                "max_hops": max_hops,
                "seed_id": seed_id,
                "view_requests": _graph_view_counter_snapshot(),
            },
        }

    except Exception:
        logger.exception("Błąd podczas konwersji grafu do formatu Cytoscape")
        # W przypadku błędu zwróć mock data jako fallback
        return _get_mock_knowledge_graph(
            limit=limit,
            view=view,
            seed_id=seed_id,
            max_hops=max_hops,
            include_isolates=include_isolates,
            limit_nodes=limit_nodes,
        )


def _get_mock_knowledge_graph(
    limit: int = 500,
    view: str = "full",
    seed_id: str | None = None,
    max_hops: int = 2,
    include_isolates: bool = True,
    limit_nodes: int | None = None,
):
    """
    Zwraca przykładowe dane grafu wiedzy do testowania UI.

    Args:
        limit: Maksymalna liczba węzłów do zwrócenia

    Returns:
        Mock graph w formacie Cytoscape
    """
    all_nodes = [
        {"data": {"id": "agent1", "label": "Orchestrator", "type": "agent"}},
        {"data": {"id": "agent2", "label": "Coder Agent", "type": "agent"}},
        {"data": {"id": "agent3", "label": "Tester Agent", "type": "agent"}},
        {"data": {"id": "file1", "label": "main.py", "type": "file"}},
        {"data": {"id": "file2", "label": "config.py", "type": "file"}},
        {"data": {"id": "file3", "label": "api/routes.py", "type": "file"}},
        {
            "data": {
                "id": "memory1",
                "label": "Lesson: Error Handling",
                "type": "memory",
            }
        },
        {
            "data": {
                "id": "memory2",
                "label": "Lesson: Code Quality",
                "type": "memory",
            }
        },
        {
            "data": {
                "id": "memory3",
                "label": "Lesson: Testing Strategy",
                "type": "memory",
            }
        },
        {"data": {"id": "file4", "label": "utils/logger.py", "type": "file"}},
    ]

    nodes = all_nodes[:limit]
    allowed_ids = {n["data"]["id"] for n in nodes}

    all_edges = [
        {
            "data": {
                "id": "e1",
                "source": "agent1",
                "target": "agent2",
                "type": "DELEGATES",
                "label": "DELEGATES",
            }
        },
        {
            "data": {
                "id": "e2",
                "source": "agent1",
                "target": "agent3",
                "type": "DELEGATES",
                "label": "DELEGATES",
            }
        },
        {
            "data": {
                "id": "e3",
                "source": "agent2",
                "target": "file1",
                "type": "EDITS",
                "label": "EDITS",
            }
        },
        {
            "data": {
                "id": "e4",
                "source": "agent2",
                "target": "file3",
                "type": "EDITS",
                "label": "EDITS",
            }
        },
        {
            "data": {
                "id": "e5",
                "source": "agent3",
                "target": "file2",
                "type": "READS",
                "label": "READS",
            }
        },
        {
            "data": {
                "id": "e6",
                "source": "file1",
                "target": "file2",
                "type": "IMPORTS",
                "label": "IMPORTS",
            }
        },
        {
            "data": {
                "id": "e7",
                "source": "file3",
                "target": "file4",
                "type": "IMPORTS",
                "label": "IMPORTS",
            }
        },
        {
            "data": {
                "id": "e8",
                "source": "agent2",
                "target": "memory2",
                "type": "LEARNS",
                "label": "LEARNS",
            }
        },
        {
            "data": {
                "id": "e9",
                "source": "agent1",
                "target": "memory1",
                "type": "LEARNS",
                "label": "LEARNS",
            }
        },
        {
            "data": {
                "id": "e10",
                "source": "agent3",
                "target": "memory3",
                "type": "LEARNS",
                "label": "LEARNS",
            }
        },
    ]

    edges = [
        e
        for e in all_edges
        if e["data"]["source"] in allowed_ids and e["data"]["target"] in allowed_ids
    ]
    view_nodes, view_edges = apply_graph_view(
        nodes=nodes,
        edges=edges,
        view=view,
        seed_id=seed_id,
        max_hops=max_hops,
        include_isolates=include_isolates,
        limit_nodes=limit_nodes,
    )
    _increment_graph_view_counter(view)

    return {
        "status": "success",
        "mock": True,
        "view": view,
        "elements": {"nodes": view_nodes, "edges": view_edges},
        "stats": {
            "nodes": len(view_nodes),
            "edges": len(view_edges),
            "source_nodes": len(nodes),
            "source_edges": len(edges),
            "view": view,
            "max_hops": max_hops,
            "seed_id": seed_id,
            "view_requests": _graph_view_counter_snapshot(),
        },
    }


def _read_session_records(
    session_id: str, session_store: Any
) -> list[KnowledgeRecordV1]:
    records: list[KnowledgeRecordV1] = []
    history = session_store.get_history(session_id) if session_store else []
    for entry in history or []:
        if isinstance(entry, dict):
            records.append(from_session_store_entry(session_id, entry))

    if session_store and hasattr(session_store, "get_summary_entry"):
        summary_entry = session_store.get_summary_entry(session_id)
        if isinstance(summary_entry, dict):
            summary_record = {
                "role": "summary",
                "content": summary_entry.get("content"),
                "session_id": session_id,
                "request_id": summary_entry.get("request_id"),
                "timestamp": summary_entry.get("timestamp")
                or datetime.now(timezone.utc).isoformat(),
                "knowledge_metadata": summary_entry.get("knowledge_metadata") or {},
            }
            records.append(from_session_store_entry(session_id, summary_record))
    return records


def _read_lesson_records(
    lessons_store: LessonsStore,
    session_id: str,
    related_task_ids: set[str],
    limit: int,
) -> list[KnowledgeRecordV1]:
    records: list[KnowledgeRecordV1] = []
    all_lessons = lessons_store.get_all_lessons(limit=limit)
    for lesson in all_lessons:
        lesson_record = from_lesson(lesson)
        lesson_session_id = lesson_record.session_id
        lesson_task_id = lesson_record.task_id
        if lesson_session_id == session_id or (
            lesson_task_id and lesson_task_id in related_task_ids
        ):
            records.append(lesson_record)
    return records


def _read_memory_records(
    vector_store: Any, session_id: str, limit: int
) -> list[KnowledgeRecordV1]:
    entries = vector_store.list_entries(
        limit=limit,
        metadata_filters={"session_id": session_id},
    )
    records: list[KnowledgeRecordV1] = []
    for entry in entries:
        if isinstance(entry, dict):
            records.append(from_vector_entry(entry))
    return records


def _build_context_links(
    session_id: str,
    records: list[KnowledgeRecordV1],
    related_task_ids: set[str],
) -> list[KnowledgeLinkV1]:
    links: list[KnowledgeLinkV1] = []
    session_node = f"session:{session_id}"
    for record in records:
        if record.kind.value == "lesson":
            if record.session_id == session_id:
                links.append(
                    KnowledgeLinkV1(
                        relation="session->lesson",
                        source_id=session_node,
                        target_id=record.record_id,
                    )
                )
            if record.task_id and record.task_id in related_task_ids:
                links.append(
                    KnowledgeLinkV1(
                        relation="task->lesson",
                        source_id=f"task:{record.task_id}",
                        target_id=record.record_id,
                    )
                )
        if record.kind.value == "memory_entry" and record.session_id == session_id:
            links.append(
                KnowledgeLinkV1(
                    relation="session->memory_entry",
                    source_id=session_node,
                    target_id=record.record_id,
                )
            )
    return links


@router.get(
    "/knowledge/context-map/{session_id}",
    response_model=KnowledgeContextMapV1,
    responses={
        400: {"description": "Nieprawidłowe session_id"},
        500: {"description": INTERNAL_ERROR_DETAIL},
    },
)
def get_knowledge_context_map(
    session_id: str,
    session_store: Annotated[Any, Depends(get_session_store)],
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    vector_store: Annotated[Any, Depends(get_vector_store)],
    limit: Annotated[
        int,
        Query(ge=1, le=1000, description="Maksymalna liczba rekordów na źródło"),
    ] = 300,
):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id jest wymagane")

    try:
        session_records = _read_session_records(session_id, session_store)
        related_task_ids = {
            rec.task_id
            for rec in session_records
            if rec.task_id and rec.task_id.strip()
        }
        lesson_records = _read_lesson_records(
            lessons_store=lessons_store,
            session_id=session_id,
            related_task_ids=related_task_ids,
            limit=limit,
        )
        memory_records = _read_memory_records(vector_store, session_id, limit)

        records = session_records + lesson_records + memory_records
        links = _build_context_links(session_id, records, related_task_ids)

        return KnowledgeContextMapV1(
            session_id=session_id, records=records, links=links
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Błąd podczas budowy knowledge context map")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from exc


@router.get("/graph/summary", responses=INTERNAL_ERROR_RESPONSES)
def get_graph_summary(
    graph_store: Annotated[CodeGraphStore, Depends(get_graph_store)],
):
    """
    Zwraca podsumowanie grafu kodu.

    Returns:
        Statystyki grafu z następującą strukturą:
        - summary: Główny obiekt zawierający pełne dane (nodes, edges, last_updated, total_nodes, total_edges)
        - nodes, edges, lastUpdated: Pola na głównym poziomie dla kompatybilności wstecznej (camelCase)

        Uwaga: Pola na głównym poziomie (nodes, edges, lastUpdated) są duplikatami danych
        z obiektu summary i służą wyłącznie dla kompatybilności wstecznej z istniejącymi klientami.
        Nowy kod powinien używać danych z obiektu summary.

    Raises:
        HTTPException: 503 jeśli CodeGraphStore nie jest dostępny
    """
    try:
        summary = graph_store.get_graph_summary()
        nodes = summary.get("total_nodes")
        edges = summary.get("total_edges")
        last_updated = None
        try:
            if graph_store.graph_file.exists():
                last_updated = datetime.fromtimestamp(
                    graph_store.graph_file.stat().st_mtime, tz=timezone.utc
                ).isoformat()
        except Exception as e:
            logger.debug("Nie można odczytać statystyk pliku grafu: %s", e)
            last_updated = None

        summary_payload = {
            **summary,
            "nodes": nodes,
            "edges": edges,
            "last_updated": last_updated,
        }

        return {
            "status": "success",
            "summary": summary_payload,
            "nodes": nodes,
            "edges": edges,
            "lastUpdated": last_updated,
        }
    except Exception as e:
        logger.exception("Błąd podczas pobierania podsumowania grafu")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from e


@router.get("/graph/file/{file_path:path}", responses=GRAPH_FILE_ROUTE_RESPONSES)
def get_file_graph_info(
    file_path: str, graph_store: Annotated[CodeGraphStore, Depends(get_graph_store)]
):
    """
    Zwraca informacje o pliku w grafie.

    Args:
        file_path: Ścieżka do pliku

    Returns:
        Informacje o pliku

    Raises:
        HTTPException: 503 jeśli CodeGraphStore nie jest dostępny, 404 jeśli plik nie istnieje
    """
    normalized_path = _normalize_graph_file_path(file_path)
    try:
        info = graph_store.get_file_info(normalized_path)
        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"Plik '{normalized_path}' nie istnieje w grafie",
            )
        return {"status": "success", "file_info": info}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Błąd podczas pobierania informacji o pliku z grafu")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from e


@router.get("/graph/impact/{file_path:path}", responses=GRAPH_FILE_ROUTE_RESPONSES)
def get_impact_analysis(
    file_path: str, graph_store: Annotated[CodeGraphStore, Depends(get_graph_store)]
):
    """
    Analizuje wpływ zmian w pliku.

    Args:
        file_path: Ścieżka do pliku

    Returns:
        Analiza wpływu

    Raises:
        HTTPException: 503 jeśli CodeGraphStore nie jest dostępny, 404 jeśli plik nie istnieje
    """
    normalized_path = _normalize_graph_file_path(file_path)
    try:
        impact = graph_store.get_impact_analysis(normalized_path)
        if impact is None or "error" in impact:
            raise HTTPException(
                status_code=404,
                detail=f"Plik '{normalized_path}' nie istnieje w grafie",
            )
        return {"status": "success", "impact": impact}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Błąd podczas analizy wpływu pliku w grafie")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from e


@router.post("/graph/scan", responses=INTERNAL_ERROR_RESPONSES)
def trigger_graph_scan(
    graph_store: Annotated[CodeGraphStore, Depends(get_graph_store)],
):
    """
    Uruchamia skanowanie grafu kodu.

    Returns:
        Potwierdzenie uruchomienia skanowania

    Raises:
        HTTPException: 503 jeśli CodeGraphStore nie jest dostępny
    """
    try:
        stats = graph_store.scan_workspace()
        if isinstance(stats, dict) and "error" in stats:
            raise HTTPException(
                status_code=500, detail=f"Błąd podczas skanowania: {stats['error']}"
            )
        return {
            "status": "success",
            "message": "Skanowanie grafu zostało uruchomione",
            "stats": stats,
        }
    except Exception as e:
        logger.exception("Błąd podczas uruchamiania skanowania grafu")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_DETAIL) from e


@router.get("/lessons", responses=LESSONS_READ_RESPONSES)
def get_lessons(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    limit: int = 10,
    tags: Optional[str] = None,
):
    """
    Pobiera listę lekcji.

    Args:
        limit: Maksymalna liczba lekcji do zwrócenia
        tags: Opcjonalne tagi do filtrowania (oddzielone przecinkami)

    Returns:
        Lista lekcji

    Raises:
        HTTPException: 503 jeśli LessonsStore nie jest dostępny
    """
    try:
        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            lessons = lessons_store.get_lessons_by_tags(tag_list)
        else:
            lessons = lessons_store.get_all_lessons(limit=limit)

        # Konwertuj do dict
        lessons_data = [lesson.to_dict() for lesson in lessons]

        return {
            "status": "success",
            "count": len(lessons_data),
            "lessons": lessons_data,
        }
    except Exception as e:
        logger.exception("Błąd podczas pobierania lekcji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/lessons/stats", responses=LESSONS_READ_RESPONSES)
def get_lessons_stats(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
):
    """
    Zwraca statystyki magazynu lekcji.

    Returns:
        Statystyki lekcji

    Raises:
        HTTPException: 503 jeśli LessonsStore nie jest dostępny
    """
    try:
        stats = lessons_store.get_statistics()
        return {"status": "success", "stats": stats}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statystyk lekcji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# --- Lesson Management Endpoints (moved from memory.py) ---


@router.delete("/lessons/prune/latest", responses=LESSONS_MUTATION_RESPONSES)
def prune_latest_lessons(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    count: Annotated[
        int,
        Query(..., ge=1, description="Liczba najnowszych lekcji do usunięcia"),
    ],
):
    """
    Usuwa n najnowszych lekcji z magazynu.
    """
    try:
        deleted = lessons_store.delete_last_n(count)
        logger.info(f"Pruning: Usunięto {deleted} najnowszych lekcji")
        return {
            "status": "success",
            "message": f"Usunięto {deleted} najnowszych lekcji",
            "deleted": deleted,
        }
    except Exception as e:
        logger.exception("Błąd podczas usuwania najnowszych lekcji")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas usuwania lekcji: {str(e)}"
        ) from e


@router.delete("/lessons/prune/range", responses=LESSONS_MUTATION_RESPONSES)
def prune_lessons_by_range(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    start: Annotated[
        str,
        Query(
            ...,
            description="Data początkowa w formacie ISO 8601 (np. 2024-01-01T00:00:00)",
        ),
    ],
    end: Annotated[
        str,
        Query(
            ...,
            description="Data końcowa w formacie ISO 8601 (np. 2024-01-31T23:59:59)",
        ),
    ],
):
    """
    Usuwa lekcje z podanego zakresu czasu.
    """
    try:
        # Parsuj daty ISO 8601 (obsługa 'Z' suffix)
        # Workaround for Python < 3.11 which doesn't handle 'Z' suffix in fromisoformat
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Błędny format daty. Użyj ISO 8601: {str(e)}",
        ) from e

    try:
        deleted = lessons_store.delete_by_time_range(start_dt, end_dt)
        logger.info(f"Pruning: Usunięto {deleted} lekcji z zakresu {start} - {end}")
        return {
            "status": "success",
            "message": f"Usunięto {deleted} lekcji z zakresu {start} - {end}",
            "deleted": deleted,
            "start": start,
            "end": end,
        }
    except Exception as e:
        logger.exception("Błąd podczas usuwania lekcji po zakresie czasu")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas usuwania lekcji: {str(e)}"
        ) from e


@router.delete("/lessons/prune/tag", responses=LESSONS_MUTATION_RESPONSES)
def prune_lessons_by_tag(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    tag: Annotated[str, Query(..., description="Tag do wyszukania i usunięcia")],
):
    """
    Usuwa lekcje zawierające dany tag.
    """
    try:
        deleted = lessons_store.delete_by_tag(tag)
        logger.info(f"Pruning: Usunięto {deleted} lekcji z tagiem '{tag}'")
        return {
            "status": "success",
            "message": f"Usunięto {deleted} lekcji z tagiem '{tag}'",
            "deleted": deleted,
            "tag": tag,
        }
    except Exception as e:
        logger.exception("Błąd podczas usuwania lekcji po tagu")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas usuwania lekcji: {str(e)}"
        ) from e


@router.delete("/lessons/purge", responses=LESSONS_MUTATION_RESPONSES)
def purge_all_lessons(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    force: Annotated[
        bool, Query(description="Wymagane potwierdzenie dla operacji nuklearnej")
    ] = False,
):
    """
    Czyści całą bazę lekcji (opcja nuklearna).
    """
    if not force:
        raise HTTPException(
            status_code=400,
            detail="Operacja wymaga potwierdzenia. Ustaw parametr force=true",
        )

    try:
        lesson_count = len(lessons_store.lessons)
        success = lessons_store.clear_all()
        if not success:
            raise HTTPException(
                status_code=500, detail="Nie udało się wyczyścić bazy lekcji"
            )
        logger.warning(
            f"💣 PURGE: Wyczyszczono całą bazę lekcji ({lesson_count} lekcji)"
        )
        return {
            "status": "success",
            "message": f"💣 Wyczyszczono całą bazę lekcji ({lesson_count} lekcji)",
            "deleted": lesson_count,
        }
    except Exception as e:
        logger.exception("Błąd podczas czyszczenia bazy lekcji")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas czyszczenia bazy: {str(e)}"
        ) from e


@router.delete("/lessons/prune/ttl", responses=LESSONS_MUTATION_RESPONSES)
def prune_lessons_by_ttl(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    days: Annotated[int, Query(..., ge=1, description="Liczba dni retencji (TTL)")],
):
    """Usuwa lekcje starsze niż TTL w dniach."""
    try:
        deleted = lessons_store.prune_by_ttl(days)
        return {
            "status": "success",
            "message": f"Usunięto {deleted} lekcji starszych niż {days} dni",
            "deleted": deleted,
            "days": days,
        }
    except Exception as e:
        logger.exception("Błąd podczas usuwania lekcji po TTL")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas usuwania lekcji: {str(e)}"
        ) from e


@router.post("/lessons/dedupe", responses=INTERNAL_ERROR_RESPONSES)
def dedupe_lessons(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
):
    """Deduplikuje lekcje na podstawie podpisu treści."""
    try:
        removed = lessons_store.dedupe_lessons()
        return {
            "status": "success",
            "message": f"Usunięto {removed} zduplikowanych lekcji",
            "removed": removed,
        }
    except Exception as e:
        logger.exception("Błąd podczas deduplikacji lekcji")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas deduplikacji lekcji: {str(e)}"
        ) from e


@router.get("/lessons/learning/status", responses=LESSONS_READ_RESPONSES)
def get_learning_status():
    """Zwraca status globalnego zapisu lekcji."""
    return {"status": "success", "enabled": SETTINGS.ENABLE_META_LEARNING}


@router.post("/lessons/learning/toggle", responses=INTERNAL_ERROR_RESPONSES)
def toggle_learning(request: LearningToggleRequest):
    """Włącza/wyłącza globalny zapis lekcji."""
    try:
        SETTINGS.ENABLE_META_LEARNING = request.enabled
        config_manager.update_config({"ENABLE_META_LEARNING": request.enabled})
        return {
            "status": "success",
            "enabled": SETTINGS.ENABLE_META_LEARNING,
        }
    except Exception as e:
        logger.exception("Błąd podczas zmiany stanu uczenia")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas zmiany stanu: {str(e)}"
        ) from e
