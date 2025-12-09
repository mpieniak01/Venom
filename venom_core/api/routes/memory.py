"""Moduł: routes/memory - Endpointy API dla pamięci wektorowej."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
