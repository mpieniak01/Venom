"""Moduł: routes/strategy - Endpointy API dla strategii (roadmap, campaign)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["strategy"])


class RoadmapCreateRequest(BaseModel):
    """Request dla utworzenia roadmapy."""

    vision: str


# Dependencies - będą ustawione w main.py
_orchestrator = None


def set_dependencies(orchestrator):
    """Ustaw zależności dla routera."""
    global _orchestrator
    _orchestrator = orchestrator


@router.get("/api/roadmap")
async def get_roadmap():
    """
    Pobiera aktualną roadmapę projektu.

    Returns:
        Roadmapa z Vision, Milestones, Tasks i KPI

    Raises:
        HTTPException: 503 jeśli orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        goal_store = _orchestrator.task_dispatcher.goal_store

        # Vision
        vision = goal_store.get_vision()
        vision_data = None
        if vision:
            vision_data = {
                "title": vision.title,
                "description": vision.description,
                "status": vision.status.value,
                "progress": vision.get_progress(),
            }

        # Milestones
        milestones = goal_store.get_milestones()
        milestones_data = []
        for milestone in milestones:
            # Tasks dla milestone
            tasks = goal_store.get_tasks(parent_id=milestone.goal_id)
            tasks_data = [
                {
                    "title": t.title,
                    "description": t.description,
                    "status": t.status.value,
                    "priority": t.priority,
                }
                for t in tasks
            ]

            milestones_data.append(
                {
                    "title": milestone.title,
                    "description": milestone.description,
                    "status": milestone.status.value,
                    "progress": milestone.get_progress(),
                    "priority": milestone.priority,
                    "tasks": tasks_data,
                }
            )

        # KPIs
        completed_milestones = [m for m in milestones if m.status.value == "COMPLETED"]
        all_tasks_list = []
        for m in milestones:
            all_tasks_list.extend(goal_store.get_tasks(parent_id=m.goal_id))
        completed_tasks = [t for t in all_tasks_list if t.status.value == "COMPLETED"]

        completion_rate = 0.0
        if milestones:
            completion_rate = (len(completed_milestones) / len(milestones)) * 100

        kpis = {
            "completion_rate": completion_rate,
            "milestones_completed": len(completed_milestones),
            "milestones_total": len(milestones),
            "tasks_completed": len(completed_tasks),
            "tasks_total": len(all_tasks_list),
        }

        # Full report
        report = goal_store.generate_roadmap_report()

        return {
            "status": "success",
            "vision": vision_data,
            "milestones": milestones_data,
            "kpis": kpis,
            "report": report,
        }

    except Exception as e:
        logger.exception("Błąd podczas pobierania roadmapy")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/api/roadmap/create")
async def create_roadmap(request: RoadmapCreateRequest):
    """
    Tworzy roadmapę na podstawie wizji użytkownika.

    Args:
        request: Vision text

    Returns:
        Potwierdzenie utworzenia roadmapy

    Raises:
        HTTPException: 503 jeśli orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        executive_agent = _orchestrator.task_dispatcher.executive_agent
        roadmap_result = await executive_agent.create_roadmap(request.vision)

        return {
            "status": "success",
            "message": "Roadmapa utworzona",
            "roadmap": roadmap_result,
        }

    except Exception as e:
        logger.exception("Błąd podczas tworzenia roadmapy")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/api/roadmap/status")
async def get_roadmap_status():
    """
    Generuje raport statusu wykonawczy.

    Returns:
        Raport z analizą Executive

    Raises:
        HTTPException: 503 jeśli orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        executive_agent = _orchestrator.task_dispatcher.executive_agent
        report = await executive_agent.generate_status_report()

        return {"status": "success", "report": report}

    except Exception as e:
        logger.exception("Błąd podczas generowania raportu statusu")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/api/campaign/start")
async def start_campaign():
    """
    Uruchamia Tryb Kampanii (autonomiczna realizacja roadmapy).

    Returns:
        Potwierdzenie rozpoczęcia kampanii

    Raises:
        HTTPException: 503 jeśli orchestrator nie jest dostępny
    """
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator nie jest dostępny")

    try:
        # Wywołaj tryb kampanii przez orchestrator
        result = await _orchestrator.execute_campaign_mode(
            goal_store=_orchestrator.task_dispatcher.goal_store
        )

        return {
            "status": "success",
            "message": "Campaign Mode uruchomiony",
            "result": result,
        }

    except Exception as e:
        logger.exception("Błąd podczas uruchamiania Campaign Mode")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
