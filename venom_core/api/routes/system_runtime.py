"""Moduł: routes/system_runtime - Endpointy runtime controller."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from venom_core.api.routes import system_deps
from venom_core.services.runtime_controller import ServiceType, runtime_controller
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])
_background_tasks: set[asyncio.Task[Any]] = set()

RUNTIME_STATUS_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas pobierania statusu runtime"},
}
RUNTIME_PROFILE_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas aplikowania profilu runtime"},
}
RUNTIME_ACTION_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Nieprawidłowa usługa lub akcja runtime"},
    500: {"description": "Błąd wewnętrzny podczas wykonywania akcji runtime"},
}
RUNTIME_HISTORY_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny podczas pobierania historii runtime"},
}


def _track_background_task(task: asyncio.Task[Any]) -> None:
    """Przechowuje referencję do fire-and-forget tasków do czasu zakończenia."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@router.get("/runtime/status", responses=RUNTIME_STATUS_RESPONSES)
def get_runtime_status():
    """
    Zwraca status wszystkich usług Venom (backend, UI, LLM, Hive, Nexus, background tasks).
    """
    try:
        services = runtime_controller.get_all_services_status()

        services_data = [
            {
                "name": s.name,
                "service_type": s.service_type.value,
                "status": s.status.value,
                "pid": s.pid,
                "port": s.port,
                "cpu_percent": s.cpu_percent,
                "memory_mb": s.memory_mb,
                "uptime_seconds": s.uptime_seconds,
                "last_log": s.last_log,
                "error_message": s.error_message,
                "actionable": s.actionable,
            }
            for s in services
        ]

        service_monitor = system_deps.get_service_monitor()
        if service_monitor:
            try:
                # Wyzwól odświeżenie w tle (fire-and-forget), aby nie blokować requestu
                refresh_task = asyncio.create_task(service_monitor.check_health())
                _track_background_task(refresh_task)
                # Pobierz natychmiast ostatnie znane dane
                monitor_services = service_monitor.get_all_services()
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Nie udało się sprawdzić ServiceMonitor: {exc}")
                monitor_services = service_monitor.get_all_services()

            status_map = {
                "online": "running",
                "offline": "stopped",
                "degraded": "degraded",
                "unknown": "unknown",
            }
            for svc in monitor_services:
                if svc.service_type == "api":
                    continue
                if svc.name.lower() in {"local llm", "vllm", "ollama"}:
                    continue
                if any(s["name"].lower() == svc.name.lower() for s in services_data):
                    continue
                services_data.append(
                    {
                        "name": svc.name,
                        "service_type": svc.service_type,
                        "status": status_map.get(svc.status.value, "unknown"),
                        "pid": None,
                        "port": None,
                        "cpu_percent": 0.0,
                        "memory_mb": 0.0,
                        "uptime_seconds": None,
                        "last_log": None,
                        "error_message": svc.error_message,
                        "latency_ms": getattr(svc, "latency_ms", 0.0),
                        "endpoint": svc.endpoint,
                        "actionable": False,
                    }
                )

        return {
            "status": "success",
            "services": services_data,
            "count": len(services_data),
        }

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu runtime")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/runtime/profile/{profile_name}", responses=RUNTIME_PROFILE_RESPONSES)
def apply_runtime_profile(profile_name: str):
    """
    Aplikuje profil konfiguracji (full, light, llm_off).
    """
    try:
        result = runtime_controller.apply_profile(profile_name)
        return result
    except Exception as e:
        logger.exception(f"Błąd podczas aplikowania profilu {profile_name}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/runtime/{service}/{action}", responses=RUNTIME_ACTION_RESPONSES)
def runtime_service_action(service: str, action: str):
    """
    Wykonuje akcję (start/stop/restart) na wskazanej usłudze.
    """
    try:
        try:
            service_type = ServiceType(service)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Nieznana usługa: "
                    f"{service}. Dostępne: backend, ui, llm_ollama, llm_vllm, hive, nexus, background_tasks"
                ),
            )

        if action not in ["start", "stop", "restart"]:
            raise HTTPException(
                status_code=400,
                detail=f"Nieznana akcja: {action}. Dostępne: start, stop, restart",
            )

        if action == "start":
            result = runtime_controller.start_service(service_type)
        elif action == "stop":
            result = runtime_controller.stop_service(service_type)
        elif action == "restart":
            result = runtime_controller.restart_service(service_type)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas wykonywania akcji {action} na {service}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/runtime/history", responses=RUNTIME_HISTORY_RESPONSES)
def get_runtime_history(limit: int = 50):
    """
    Zwraca historię akcji runtime (start/stop/restart).
    """
    try:
        history = runtime_controller.get_history(limit=limit)
        return {"status": "success", "history": history, "count": len(history)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania historii runtime")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
