"""Moduł: routes/system - Endpointy API dla systemu (metrics, scheduler, services)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from venom_core.core.metrics import metrics_collector
from venom_core.core.permission_guard import permission_guard
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

# Dependencies - będą ustawione w main.py
_background_scheduler = None
_service_monitor = None
_state_manager = None  # Nowa zależność dla Cost Guard


class CostModeRequest(BaseModel):
    """Request do zmiany trybu kosztowego."""

    enable: bool


class CostModeResponse(BaseModel):
    """Response z informacją o trybie kosztowym."""

    enabled: bool
    provider: str


def set_dependencies(background_scheduler, service_monitor, state_manager=None):
    """Ustaw zależności dla routera."""
    global _background_scheduler, _service_monitor, _state_manager
    _background_scheduler = background_scheduler
    _service_monitor = service_monitor
    _state_manager = state_manager


@router.get("/metrics")
async def get_metrics():
    """
    Zwraca metryki systemowe.

    Returns:
        Słownik z metrykami wydajności i użycia

    Raises:
        HTTPException: 503 jeśli MetricsCollector nie jest dostępny
    """
    if metrics_collector is None:
        raise HTTPException(status_code=503, detail="Metrics collector not initialized")
    return metrics_collector.get_metrics()


@router.get("/scheduler/status")
async def get_scheduler_status():
    """
    Zwraca status schedulera zadań w tle.

    Returns:
        Status schedulera

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if _background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        status = _background_scheduler.get_status()
        return {"status": "success", "scheduler": status}
    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu schedulera")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/scheduler/jobs")
async def get_scheduler_jobs():
    """
    Zwraca listę zadań w tle.

    Returns:
        Lista zadań

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if _background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        jobs = _background_scheduler.get_jobs()
        return {"status": "success", "jobs": jobs, "count": len(jobs)}
    except Exception as e:
        logger.exception("Błąd podczas pobierania listy zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/scheduler/pause")
async def pause_scheduler():
    """
    Wstrzymuje wszystkie zadania w tle.

    Returns:
        Potwierdzenie wstrzymania

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if _background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        await _background_scheduler.pause_all_jobs()
        return {"status": "success", "message": "All background jobs paused"}
    except Exception as e:
        logger.exception("Błąd podczas wstrzymywania zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/scheduler/resume")
async def resume_scheduler():
    """
    Wznawia wszystkie zadania w tle.

    Returns:
        Potwierdzenie wznowienia

    Raises:
        HTTPException: 503 jeśli scheduler nie jest dostępny
    """
    if _background_scheduler is None:
        raise HTTPException(
            status_code=503, detail="BackgroundScheduler nie jest dostępny"
        )

    try:
        await _background_scheduler.resume_all_jobs()
        return {"status": "success", "message": "All background jobs resumed"}
    except Exception as e:
        logger.exception("Błąd podczas wznawiania zadań")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/system/services")
async def get_all_services():
    """
    Zwraca listę wszystkich monitorowanych usług.

    Returns:
        Lista usług z ich statusami

    Raises:
        HTTPException: 503 jeśli ServiceMonitor nie jest dostępny
    """
    if _service_monitor is None:
        raise HTTPException(status_code=503, detail="ServiceMonitor nie jest dostępny")

    try:
        services = _service_monitor.get_all_services()

        services_data = [
            {
                "name": service.name,
                "type": service.service_type,
                "status": service.status.value,
                "latency_ms": service.latency_ms,
                "last_check": service.last_check,
                "is_critical": service.is_critical,
            }
            for service in services
        ]

        return {"status": "success", "services": services_data, "count": len(services)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy usług")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/system/services/{service_name}")
async def get_service_status(service_name: str):
    """
    Zwraca szczegółowy status konkretnej usługi.

    Args:
        service_name: Nazwa usługi

    Returns:
        Szczegółowy status usługi

    Raises:
        HTTPException: 404 jeśli usługa nie istnieje, 503 jeśli ServiceMonitor nie jest dostępny
    """
    if _service_monitor is None:
        raise HTTPException(status_code=503, detail="ServiceMonitor nie jest dostępny")

    try:
        services = _service_monitor.get_all_services()
        services = [s for s in services if s.name == service_name]

        if not services:
            raise HTTPException(
                status_code=404, detail=f"Usługa '{service_name}' nie znaleziona"
            )

        service = services[0]

        return {
            "status": "success",
            "service": {
                "name": service.name,
                "type": service.service_type,
                "status": service.status.value,
                "latency_ms": service.latency_ms,
                "last_check": service.last_check,
                "is_critical": service.is_critical,
                "error_message": service.error_message,
                "description": service.description,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas sprawdzania statusu usługi {service_name}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# ========================================
# Global Cost Guard Endpoints
# ========================================


@router.get("/system/cost-mode", response_model=CostModeResponse)
async def get_cost_mode():
    """
    Zwraca aktualny stan Global Cost Guard.

    Returns:
        Informacja czy tryb płatny jest włączony i jaki provider jest używany

    Raises:
        HTTPException: 503 jeśli StateManager nie jest dostępny
    """
    if _state_manager is None:
        raise HTTPException(
            status_code=503, detail="StateManager nie jest dostępny (Cost Guard)"
        )

    try:
        from venom_core.config import SETTINGS

        enabled = _state_manager.is_paid_mode_enabled()
        provider = (
            "hybrid" if SETTINGS.AI_MODE == "HYBRID" else SETTINGS.AI_MODE.lower()
        )

        return CostModeResponse(enabled=enabled, provider=provider)

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Cost Guard")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/system/cost-mode")
async def set_cost_mode(request: CostModeRequest):
    """
    Ustawia tryb kosztowy (Eco/Pro).

    Args:
        request: Żądanie z flagą enable (True = Pro Mode, False = Eco Mode)

    Returns:
        Potwierdzenie zmiany trybu

    Raises:
        HTTPException: 503 jeśli StateManager nie jest dostępny
    """
    if _state_manager is None:
        raise HTTPException(
            status_code=503, detail="StateManager nie jest dostępny (Cost Guard)"
        )

    try:
        if request.enable:
            _state_manager.enable_paid_mode()
            logger.warning(
                "🔓 Paid Mode ENABLED przez API - użytkownik zaakceptował koszty"
            )
            return {
                "status": "success",
                "message": "Paid Mode (Pro) włączony - dostęp do Cloud API otwarty",
                "enabled": True,
            }
        else:
            _state_manager.disable_paid_mode()
            logger.info("🔒 Paid Mode DISABLED przez API - tryb Eco aktywny")
            return {
                "status": "success",
                "message": "Paid Mode (Pro) wyłączony - tylko lokalne modele",
                "enabled": False,
            }

    except Exception as e:
        logger.exception("Błąd podczas zmiany trybu kosztowego")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


# ========================================
# AutonomyGate Endpoints
# ========================================


class AutonomyLevelRequest(BaseModel):
    """Request do zmiany poziomu autonomii."""

    level: int


class AutonomyLevelResponse(BaseModel):
    """Response z informacją o poziomie autonomii."""

    current_level: int
    current_level_name: str
    color: str
    color_name: str
    description: str
    permissions: dict
    risk_level: str


@router.get("/system/autonomy", response_model=AutonomyLevelResponse)
async def get_autonomy_level():
    """
    Zwraca aktualny poziom autonomii AutonomyGate.

    Returns:
        Informacje o aktualnym poziomie autonomii

    Raises:
        HTTPException: 500 jeśli wystąpi błąd
    """
    try:
        current_level = permission_guard.get_current_level()
        level_info = permission_guard.get_level_info(current_level)

        if not level_info:
            raise HTTPException(
                status_code=500, detail="Nie można pobrać informacji o poziomie"
            )

        return AutonomyLevelResponse(
            current_level=current_level,
            current_level_name=level_info.name,
            color=level_info.color,
            color_name=level_info.color_name,
            description=level_info.description,
            permissions=level_info.permissions,
            risk_level=level_info.risk_level,
        )

    except Exception as e:
        logger.exception("Błąd podczas pobierania poziomu autonomii")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/system/autonomy")
async def set_autonomy_level(request: AutonomyLevelRequest):
    """
    Ustawia nowy poziom autonomii.

    Args:
        request: Żądanie z nowym poziomem (0, 10, 20, 30, 40)

    Returns:
        Potwierdzenie zmiany poziomu

    Raises:
        HTTPException: 400 jeśli poziom nieprawidłowy, 500 jeśli wystąpi błąd
    """
    try:
        success = permission_guard.set_level(request.level)

        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Nieprawidłowy poziom: {request.level}. Dostępne: 0, 10, 20, 30, 40",
            )

        level_info = permission_guard.get_level_info(request.level)

        return {
            "status": "success",
            "message": f"Poziom autonomii zmieniony na {level_info.name}",
            "level": request.level,
            "level_name": level_info.name,
            "color": level_info.color,
            "permissions": level_info.permissions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Błąd podczas zmiany poziomu autonomii")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/system/autonomy/levels")
async def get_all_autonomy_levels():
    """
    Zwraca listę wszystkich dostępnych poziomów autonomii.

    Returns:
        Lista poziomów z ich konfiguracją
    """
    try:
        levels = permission_guard.get_all_levels()

        levels_data = [
            {
                "id": level.id,
                "name": level.name,
                "description": level.description,
                "color": level.color,
                "color_name": level.color_name,
                "permissions": level.permissions,
                "risk_level": level.risk_level,
                "examples": level.examples,
            }
            for level in levels.values()
        ]

        return {"status": "success", "levels": levels_data, "count": len(levels_data)}

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy poziomów")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
