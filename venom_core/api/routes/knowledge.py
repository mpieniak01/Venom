"""Moduł: routes/knowledge - Endpointy API dla graph i lessons."""

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from venom_core.api.dependencies import get_graph_store, get_lessons_store
from venom_core.config import SETTINGS
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.memory.lessons_store import LessonsStore
from venom_core.services.config_manager import config_manager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["knowledge"])

_graph_store = None
_lessons_store = None
INTERNAL_ERROR_DETAIL = "Błąd wewnętrzny"


def _normalize_graph_file_path(file_path: str) -> str:
    """
    Normalizuje ścieżkę pliku z URL i odrzuca niebezpieczne formaty.
    """
    normalized = file_path.strip().replace("\\", "/")
    if not normalized:
        raise HTTPException(status_code=400, detail="Nieprawidłowa ścieżka pliku")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise HTTPException(status_code=400, detail="Nieprawidłowa ścieżka pliku")
    return str(path)


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


@router.get("/knowledge/graph")
async def get_knowledge_graph(
    graph_store: Annotated[CodeGraphStore, Depends(get_graph_store)],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=5000,
            description="Maksymalna liczba węzłów do zwrócenia (pozostałe są odfiltrowane)",
        ),
    ] = 500,
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
        return _get_mock_knowledge_graph(limit=limit)

    try:
        # Konwertuj NetworkX graph do formatu Cytoscape
        nodes = []
        edges = []

        # Dodaj węzły
        for node_id, node_data in graph_store.graph.nodes(data=True):
            node_type = node_data.get("type", "unknown")
            node_name = node_data.get("name", node_id)

            # Mapowanie typów na kategorie dla UI
            if node_type == "file":
                category = "file"
                label = node_data.get("path", node_name)
            elif node_type == "class":
                # Rozróżnij agentów od zwykłych klas
                file_path = node_data.get("file", "")
                if "agents" in file_path or node_data.get("is_agent", False):
                    category = "agent"
                else:
                    category = "class"
                label = node_name
            elif node_type == "function" or node_type == "method":
                # Funkcje i metody jako osobna kategoria, nie memory
                category = "function"
                label = node_name
            else:
                category = "file"
                label = node_name

            nodes.append(
                {
                    "data": {
                        "id": node_id,
                        "label": label,
                        "type": category,
                        "original_type": node_type,
                        "properties": node_data,
                    }
                }
            )
            if len(nodes) >= limit:
                break

        allowed_ids = {n["data"]["id"] for n in nodes}
        # Dodaj krawędzie
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

        return {
            "status": "success",
            "elements": {"nodes": nodes, "edges": edges},
            "stats": {"nodes": len(nodes), "edges": len(edges)},
        }

    except Exception:
        logger.exception("Błąd podczas konwersji grafu do formatu Cytoscape")
        # W przypadku błędu zwróć mock data jako fallback
        return _get_mock_knowledge_graph(limit=limit)


def _get_mock_knowledge_graph(limit: int = 500):
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

    return {
        "status": "success",
        "mock": True,
        "elements": {"nodes": nodes, "edges": edges},
        "stats": {"nodes": len(nodes), "edges": len(edges)},
    }


@router.get("/graph/summary")
async def get_graph_summary(
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


@router.get("/graph/file/{file_path:path}")
async def get_file_graph_info(
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


@router.get("/graph/impact/{file_path:path}")
async def get_impact_analysis(
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


@router.post("/graph/scan")
async def trigger_graph_scan(
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


@router.get("/lessons")
async def get_lessons(
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


@router.get("/lessons/stats")
async def get_lessons_stats(
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


@router.delete("/lessons/prune/latest")
async def prune_latest_lessons(
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


@router.delete("/lessons/prune/range")
async def prune_lessons_by_range(
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


@router.delete("/lessons/prune/tag")
async def prune_lessons_by_tag(
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


@router.delete("/lessons/purge")
async def purge_all_lessons(
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


@router.delete("/lessons/prune/ttl")
async def prune_lessons_by_ttl(
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


@router.post("/lessons/dedupe")
async def dedupe_lessons(
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


@router.get("/lessons/learning/status")
async def get_learning_status():
    """Zwraca status globalnego zapisu lekcji."""
    return {"status": "success", "enabled": SETTINGS.ENABLE_META_LEARNING}


class LearningToggleRequest(BaseModel):
    enabled: bool


@router.post("/lessons/learning/toggle")
async def toggle_learning(request: LearningToggleRequest):
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
