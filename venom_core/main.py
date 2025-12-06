# venom/main.py
from uuid import UUID

from fastapi import FastAPI, HTTPException

from venom_core.config import SETTINGS
from venom_core.core.models import TaskRequest, TaskResponse, VenomTask
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Venom Core", version="0.1.0")

# Inicjalizacja StateManager i Orchestrator
state_manager = StateManager(state_file_path=SETTINGS.STATE_FILE_PATH)
orchestrator = Orchestrator(state_manager)


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
        logger.error(f"Błąd podczas tworzenia zadania: {e}")
        raise HTTPException(
            status_code=500, detail="Błąd wewnętrzny podczas tworzenia zadania"
        )


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
