"""Moduł: routes/knowledge - Endpointy API dla graph i lessons."""

from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from venom_core.api.dependencies import (
    get_graph_store,
    get_lessons_store,
    get_session_store,
    get_vector_store,
)
from venom_core.api.routes.graph_view_utils import apply_graph_view
from venom_core.api.routes.permission_denied_contract import (
    raise_permission_denied_http,
)
from venom_core.api.schemas.knowledge import LearningToggleRequest
from venom_core.config import SETTINGS
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.memory.lessons_store import LessonsStore
from venom_core.services.config_manager import config_manager
from venom_core.services.knowledge_context_service import (
    build_knowledge_context_map as _build_knowledge_context_map,
)
from venom_core.services.knowledge_graph_service import (
    build_graph_edges as _build_graph_edges,
)
from venom_core.services.knowledge_graph_service import (
    build_graph_nodes as _build_graph_nodes,
)
from venom_core.services.knowledge_graph_service import (
    graph_view_counter_snapshot as _graph_view_counter_snapshot,
)
from venom_core.services.knowledge_graph_service import (
    increment_graph_view_counter as _increment_graph_view_counter,
)
from venom_core.services.knowledge_graph_service import (
    normalize_graph_file_path as _normalize_graph_file_path_service,
)
from venom_core.services.knowledge_lessons_service import (
    dedupe_lessons as _dedupe_lessons_service,
)
from venom_core.services.knowledge_lessons_service import (
    parse_iso_range as _parse_iso_range_service,
)
from venom_core.services.knowledge_lessons_service import (
    prune_latest_lessons as _prune_latest_lessons_service,
)
from venom_core.services.knowledge_lessons_service import (
    prune_lessons_by_range as _prune_lessons_by_range_service,
)
from venom_core.services.knowledge_lessons_service import (
    prune_lessons_by_tag as _prune_lessons_by_tag_service,
)
from venom_core.services.knowledge_lessons_service import (
    prune_lessons_by_ttl as _prune_lessons_by_ttl_service,
)
from venom_core.services.knowledge_lessons_service import (
    purge_all_lessons as _purge_all_lessons_service,
)
from venom_core.services.knowledge_route_service import (
    KnowledgeContextMapV1,
    ensure_data_mutation_allowed,
)
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


def _enforce_mutation_allowed(operation_name: str) -> None:
    try:
        ensure_data_mutation_allowed(operation_name)
    except PermissionError as e:
        raise_permission_denied_http(e, operation=operation_name)


def _normalize_graph_file_path(file_path: str) -> str:
    try:
        return _normalize_graph_file_path_service(file_path)
    except ValueError:
        raise HTTPException(status_code=400, detail=INVALID_FILE_PATH_DETAIL)


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
        return _build_knowledge_context_map(
            session_id=session_id,
            session_store=session_store,
            lessons_store=lessons_store,
            vector_store=vector_store,
            limit=limit,
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
    except PermissionError as e:
        raise_permission_denied_http(e, operation="knowledge.graph.summary")
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
    except PermissionError as e:
        raise_permission_denied_http(e, operation="knowledge.graph.file_info")
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
    except PermissionError as e:
        raise_permission_denied_http(e, operation="knowledge.graph.impact")
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
    except PermissionError as e:
        raise_permission_denied_http(e, operation="knowledge.graph.scan")
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
    except PermissionError as e:
        raise_permission_denied_http(e, operation="knowledge.lessons.list")
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
    except PermissionError as e:
        raise_permission_denied_http(e, operation="knowledge.lessons.stats")
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
    _enforce_mutation_allowed("knowledge.lessons.prune_latest")
    try:
        return _prune_latest_lessons_service(
            lessons_store=lessons_store,
            count=count,
            logger=logger,
        )
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
    _enforce_mutation_allowed("knowledge.lessons.prune_range")
    try:
        start_dt, end_dt = _parse_iso_range_service(start=start, end=end)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Błędny format daty. Użyj ISO 8601: {str(e)}",
        ) from e

    try:
        return _prune_lessons_by_range_service(
            lessons_store=lessons_store,
            start=start,
            end=end,
            start_dt=start_dt,
            end_dt=end_dt,
            logger=logger,
        )
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
    _enforce_mutation_allowed("knowledge.lessons.prune_tag")
    try:
        return _prune_lessons_by_tag_service(
            lessons_store=lessons_store,
            tag=tag,
            logger=logger,
        )
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

    _enforce_mutation_allowed("knowledge.lessons.purge")
    try:
        return _purge_all_lessons_service(
            lessons_store=lessons_store,
            logger=logger,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
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
    _enforce_mutation_allowed("knowledge.lessons.prune_ttl")
    try:
        return _prune_lessons_by_ttl_service(
            lessons_store=lessons_store,
            days=days,
        )
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
    _enforce_mutation_allowed("knowledge.lessons.dedupe")
    try:
        return _dedupe_lessons_service(lessons_store=lessons_store)
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
