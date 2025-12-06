# venom/main.py
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException

from venom_core.config import SETTINGS
from venom_core.core.models import TaskRequest, TaskResponse, VenomTask
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Inicjalizacja StateManager i Orchestrator
state_manager = StateManager(state_file_path=SETTINGS.STATE_FILE_PATH)
orchestrator = Orchestrator(state_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządzanie cyklem życia aplikacji."""
    # Startup
    from pathlib import Path

    # Utwórz katalog workspace jeśli nie istnieje
    workspace_path = Path(SETTINGS.WORKSPACE_ROOT)
    workspace_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Workspace directory: {workspace_path.resolve()}")

    # Utwórz katalog memory jeśli nie istnieje
    memory_path = Path(SETTINGS.MEMORY_ROOT)
    memory_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Memory directory: {memory_path.resolve()}")

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
