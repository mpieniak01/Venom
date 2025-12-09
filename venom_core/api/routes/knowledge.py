"""Moduł: routes/knowledge - Endpointy API dla graph i lessons."""

from fastapi import APIRouter, HTTPException

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
        raise HTTPException(
            status_code=503, detail="CodeGraphStore nie jest dostępny"
        )

    try:
        summary = _graph_store.get_summary()
        return {"status": "success", "summary": summary}
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
        raise HTTPException(
            status_code=503, detail="CodeGraphStore nie jest dostępny"
        )

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
        raise HTTPException(
            status_code=503, detail="CodeGraphStore nie jest dostępny"
        )

    try:
        impact = _graph_store.analyze_impact(file_path)
        if impact is None:
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
        raise HTTPException(
            status_code=503, detail="CodeGraphStore nie jest dostępny"
        )

    try:
        _graph_store.scan_codebase()
        return {"status": "success", "message": "Skanowanie grafu zostało uruchomione"}
    except Exception as e:
        logger.exception("Błąd podczas uruchamiania skanowania grafu")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/lessons")
async def get_lessons(limit: int = 10, tags: str = None):
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
