"""Moduł: routes/system - Endpointy API dla systemu (metrics, scheduler, services)."""

from fastapi import APIRouter, HTTPException

from venom_core.core.metrics import metrics_collector
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

# Dependencies - będą ustawione w main.py
_background_scheduler = None
_service_monitor = None


def set_dependencies(background_scheduler, service_monitor):
    """Ustaw zależności dla routera."""
    global _background_scheduler, _service_monitor
    _background_scheduler = background_scheduler
    _service_monitor = service_monitor


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
