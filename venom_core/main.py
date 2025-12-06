# venom/main.py
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from venom_core.config import SETTINGS
from venom_core.core.models import TaskRequest, TaskResponse, VenomTask
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.memory.vector_store import VectorStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Inicjalizacja StateManager i Orchestrator
state_manager = StateManager(state_file_path=SETTINGS.STATE_FILE_PATH)
orchestrator = Orchestrator(state_manager)

# Inicjalizacja VectorStore dla API
vector_store = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządzanie cyklem życia aplikacji."""
    global vector_store
    
    # Startup
    # Utwórz katalog workspace jeśli nie istnieje
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT)
    workspace_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Workspace directory: {workspace_path.resolve()}")

    # Utwórz katalog memory jeśli nie istnieje
    memory_path = Path(SETTINGS.MEMORY_ROOT)
    memory_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Memory directory: {memory_path.resolve()}")

    # Inicjalizuj VectorStore
    try:
        vector_store = VectorStore()
        logger.info("VectorStore zainicjalizowany")
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować VectorStore: {e}")
        vector_store = None

    yield
    # Shutdown - czeka na zakończenie zapisów stanu
    logger.info("Zamykanie aplikacji...")
    await state_manager.shutdown()
    logger.info("Aplikacja zamknięta")


app = FastAPI(title="Venom Core", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    """Prosty endpoint zdrowia – do sprawdzenia, czy Venom żyje."""
    return {"status": "ok", "component": "venom-core"}


@app.post("/api/v1/tasks", response_model=TaskResponse, status_code=201)
async def create_task(request: TaskRequest):
    """
    Tworzy nowe zadanie i uruchamia je w tle.

    Args:
        request: Żądanie z treścią zadania

    Returns:
        Odpowiedź z ID zadania i statusem

    Raises:
        HTTPException: 400 przy błędnym body, 500 przy błędzie wewnętrznym
    """
    try:
        response = await orchestrator.submit_task(request)
        return response
    except Exception as e:
        logger.exception("Błąd podczas tworzenia zadania")
        raise HTTPException(
            status_code=500, detail="Błąd wewnętrzny podczas tworzenia zadania"
        ) from e


@app.get("/api/v1/tasks/{task_id}", response_model=VenomTask)
async def get_task(task_id: UUID):
    """
    Pobiera szczegóły zadania po ID.

    Args:
        task_id: UUID zadania

    Returns:
        Szczegóły zadania

    Raises:
        HTTPException: 404 jeśli zadanie nie istnieje
    """
    task = state_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Zadanie {task_id} nie istnieje")
    return task


@app.get("/api/v1/tasks", response_model=list[VenomTask])
async def get_all_tasks():
    """
    Pobiera listę wszystkich zadań.

    Returns:
        Lista wszystkich zadań w systemie
    """
    return state_manager.get_all_tasks()


# --- Memory API Endpoints ---


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


@app.post("/api/v1/memory/ingest", response_model=MemoryIngestResponse, status_code=201)
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
    if vector_store is None:
        raise HTTPException(
            status_code=503,
            detail="VectorStore nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        )

    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Tekst nie może być pusty")

        # Zapisz do pamięci
        metadata = {"category": request.category}
        result = vector_store.upsert(
            text=request.text,
            metadata=metadata,
            collection_name=request.collection,
            chunk_text=True,
        )

        logger.info(f"Ingestion pomyślny: {result['chunks_count']} fragmentów do '{request.collection}'")

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
        raise HTTPException(
            status_code=500, detail=f"Błąd wewnętrzny: {str(e)}"
        ) from e


@app.post("/api/v1/memory/search")
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
    if vector_store is None:
        raise HTTPException(
            status_code=503,
            detail="VectorStore nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        )

    try:
        if not request.query or not request.query.strip():
            raise HTTPException(status_code=400, detail="Zapytanie nie może być puste")

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

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Błąd podczas wyszukiwania w pamięci")
        raise HTTPException(
            status_code=500, detail=f"Błąd wewnętrzny: {str(e)}"
        ) from e
