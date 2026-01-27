"""Moduł: routes/knowledge - Endpointy API dla graph i lessons."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["knowledge"])

# Dependencies - będą ustawione w main.py
_graph_store = None
_lessons_store = None


def set_dependencies(graph_store, lessons_store):
    """Ustaw zależności dla routera."""
    global _graph_store, _lessons_store
    _graph_store = graph_store
    _lessons_store = lessons_store


@router.get("/knowledge/graph")
async def get_knowledge_graph(
    limit: int = Query(
        500,
        ge=1,
        le=5000,
        description="Maksymalna liczba węzłów do zwrócenia (pozostałe są odfiltrowane)",
    ),
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
    if _graph_store is None or _graph_store.graph.number_of_nodes() == 0:
        logger.info("Graph store pusty lub niedostępny, zwracam mock data")
        return _get_mock_knowledge_graph()

    try:
        # Konwertuj NetworkX graph do formatu Cytoscape
        nodes = []
        edges = []

        # Dodaj węzły
        for node_id, node_data in _graph_store.graph.nodes(data=True):
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
        for source, target, edge_data in _graph_store.graph.edges(data=True):
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
        return _get_mock_knowledge_graph()


def _get_mock_knowledge_graph():
    """
    Zwraca przykładowe dane grafu wiedzy do testowania UI.

    Returns:
        Mock graph w formacie Cytoscape
    """
    return {
        "status": "success",
        "mock": True,
        "elements": {
            "nodes": [
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
            ],
            "edges": [
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
            ],
        },
        "stats": {"nodes": 10, "edges": 10},
    }


@router.get("/graph/summary")
async def get_graph_summary():
    """
    Zwraca podsumowanie grafu kodu.

    Returns:
        Statystyki grafu

    Raises:
        HTTPException: 503 jeśli CodeGraphStore nie jest dostępny
    """
    if _graph_store is None:
        raise HTTPException(status_code=503, detail="CodeGraphStore nie jest dostępny")

    try:
        summary = _graph_store.get_graph_summary()
        nodes = summary.get("total_nodes")
        edges = summary.get("total_edges")
        last_updated = None
        try:
            if _graph_store.graph_file.exists():
                last_updated = datetime.fromtimestamp(
                    _graph_store.graph_file.stat().st_mtime, tz=timezone.utc
                ).isoformat()
        except Exception:
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
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/graph/file/{file_path:path}")
async def get_file_graph_info(file_path: str):
    """
    Zwraca informacje o pliku w grafie.

    Args:
        file_path: Ścieżka do pliku

    Returns:
        Informacje o pliku

    Raises:
        HTTPException: 503 jeśli CodeGraphStore nie jest dostępny, 404 jeśli plik nie istnieje
    """
    if _graph_store is None:
        raise HTTPException(status_code=503, detail="CodeGraphStore nie jest dostępny")

    try:
        info = _graph_store.get_file_info(file_path)
        if info is None:
            raise HTTPException(
                status_code=404, detail=f"Plik {file_path} nie istnieje w grafie"
            )
        return {"status": "success", "file_info": info}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas pobierania informacji o pliku {file_path}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/graph/impact/{file_path:path}")
async def get_impact_analysis(file_path: str):
    """
    Analizuje wpływ zmian w pliku.

    Args:
        file_path: Ścieżka do pliku

    Returns:
        Analiza wpływu

    Raises:
        HTTPException: 503 jeśli CodeGraphStore nie jest dostępny, 404 jeśli plik nie istnieje
    """
    if _graph_store is None:
        raise HTTPException(status_code=503, detail="CodeGraphStore nie jest dostępny")

    try:
        impact = _graph_store.get_impact_analysis(file_path)
        if impact is None or "error" in impact:
            raise HTTPException(
                status_code=404, detail=f"Plik {file_path} nie istnieje w grafie"
            )
        return {"status": "success", "impact": impact}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas analizy wpływu dla pliku {file_path}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/graph/scan")
async def trigger_graph_scan():
    """
    Uruchamia skanowanie grafu kodu.

    Returns:
        Potwierdzenie uruchomienia skanowania

    Raises:
        HTTPException: 503 jeśli CodeGraphStore nie jest dostępny
    """
    if _graph_store is None:
        raise HTTPException(status_code=503, detail="CodeGraphStore nie jest dostępny")

    try:
        stats = _graph_store.scan_workspace()
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
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/lessons")
async def get_lessons(limit: int = 10, tags: Optional[str] = None):
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
    if _lessons_store is None:
        raise HTTPException(status_code=503, detail="LessonsStore nie jest dostępny")

    try:
        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            lessons = _lessons_store.get_lessons_by_tags(tag_list)
        else:
            lessons = _lessons_store.get_all_lessons(limit=limit)

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
async def get_lessons_stats():
    """
    Zwraca statystyki magazynu lekcji.

    Returns:
        Statystyki lekcji

    Raises:
        HTTPException: 503 jeśli LessonsStore nie jest dostępny
    """
    if _lessons_store is None:
        raise HTTPException(status_code=503, detail="LessonsStore nie jest dostępny")

    try:
        stats = _lessons_store.get_statistics()
        return {"status": "success", "stats": stats}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statystyk lekcji")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
