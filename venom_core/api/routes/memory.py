"""Moduł: routes/memory - Endpointy API dla pamięci wektorowej."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from venom_core.api.dependencies import get_lessons_store
from venom_core.memory.lessons_store import LessonsStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


# Modele
class MemoryIngestRequest(BaseModel):
    """Model żądania ingestion do pamięci."""

    text: str
    category: str = "general"
    collection: str = "default"


class MemoryIngestResponse(BaseModel):
    """Model odpowiedzi po ingestion."""

    status: str
    message: str
    chunks_count: int = 0


class MemorySearchRequest(BaseModel):
    """Model żądania wyszukiwania w pamięci."""

    query: str
    limit: int = 3
    collection: str = "default"


# Dependency - będzie ustawione w main.py
_vector_store = None


def set_dependencies(vector_store):
    """Ustaw zależności dla routera."""
    global _vector_store
    _vector_store = vector_store


@router.post("/ingest", response_model=MemoryIngestResponse, status_code=201)
async def ingest_to_memory(request: MemoryIngestRequest):
    """
    Zapisuje tekst do pamięci wektorowej.

    Args:
        request: Żądanie z tekstem do zapamiętania

    Returns:
        Potwierdzenie zapisu z liczbą fragmentów

    Raises:
        HTTPException: 503 jeśli VectorStore nie jest dostępny, 400 przy błędnych danych
    """
    if _vector_store is None:
        raise HTTPException(
            status_code=503,
            detail="VectorStore nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        )

    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Tekst nie może być pusty")

        # Zapisz do pamięci
        metadata = {"category": request.category}
        result = _vector_store.upsert(
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

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Błąd podczas ingestion do pamięci")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/search")
async def search_memory(request: MemorySearchRequest):
    """
    Wyszukuje informacje w pamięci wektorowej.

    Args:
        request: Żądanie z zapytaniem

    Returns:
        Wyniki wyszukiwania

    Raises:
        HTTPException: 503 jeśli VectorStore nie jest dostępny, 400 przy błędnych danych
    """
    if _vector_store is None:
        raise HTTPException(
            status_code=503,
            detail="VectorStore nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        )

    try:
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Zapytanie nie może być puste")

        results = _vector_store.search(
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

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Błąd podczas wyszukiwania w pamięci")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# ============================================
# Pruning API - Knowledge Hygiene Suite
# ============================================


@router.delete("/lessons/prune/latest")
async def prune_latest_lessons(
    count: int = Query(..., ge=1, description="Liczba najnowszych lekcji do usunięcia"),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """
    Usuwa n najnowszych lekcji z magazynu.

    Args:
        count: Liczba lekcji do usunięcia
        lessons_store: Instancja LessonsStore (dependency injection)

    Returns:
        Liczba usuniętych lekcji

    Raises:
        HTTPException: 503 jeśli LessonsStore nie jest dostępny
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
    start: str = Query(
        ..., description="Data początkowa w formacie ISO 8601 (np. 2024-01-01T00:00:00)"
    ),
    end: str = Query(
        ..., description="Data końcowa w formacie ISO 8601 (np. 2024-01-31T23:59:59)"
    ),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """
    Usuwa lekcje z podanego zakresu czasu.

    Args:
        start: Data początkowa (ISO 8601)
        end: Data końcowa (ISO 8601)
        lessons_store: Instancja LessonsStore (dependency injection)

    Returns:
        Liczba usuniętych lekcji

    Raises:
        HTTPException: 400 przy błędnym formacie daty, 503 jeśli LessonsStore niedostępny
    """
    try:
        # Parsuj daty ISO 8601
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Błędny format daty. Użyj ISO 8601 (np. 2024-01-01T00:00:00): {str(e)}",
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
    tag: str = Query(..., description="Tag do wyszukania i usunięcia"),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """
    Usuwa lekcje zawierające dany tag.

    Args:
        tag: Tag do wyszukania
        lessons_store: Instancja LessonsStore (dependency injection)

    Returns:
        Liczba usuniętych lekcji

    Raises:
        HTTPException: 503 jeśli LessonsStore nie jest dostępny
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
    force: bool = Query(
        False, description="Wymagane potwierdzenie dla operacji nuklearnej"
    ),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """
    Czyści całą bazę lekcji (opcja nuklearna).

    Args:
        force: Musi być ustawione na True dla potwierdzenia
        lessons_store: Instancja LessonsStore (dependency injection)

    Returns:
        Potwierdzenie operacji

    Raises:
        HTTPException: 400 jeśli brak potwierdzenia, 503 jeśli LessonsStore niedostępny
    """
    if not force:
        raise HTTPException(
            status_code=400,
            detail="Operacja wymaga potwierdzenia. Ustaw parametr force=true",
        )

    try:
        lesson_count = len(lessons_store.lessons)
        success = lessons_store.clear_all()

        logger.warning(f"💣 PURGE: Wyczyszczono całą bazę lekcji ({lesson_count} lekcji)")

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
