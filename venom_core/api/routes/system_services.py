"""Moduł: routes/system_services - Endpointy usług systemowych."""

from fastapi import APIRouter, HTTPException

from venom_core.api.routes import system_deps
from venom_core.utils.logger import get_logger
from venom_core.utils.ttl_cache import TTLCache

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])

_services_cache = TTLCache[dict](ttl_seconds=2.0)


@router.get(
    "/system/services",
    responses={
        503: {"description": "ServiceMonitor nie jest dostępny"},
        500: {"description": "Błąd wewnętrzny podczas pobierania listy usług"},
    },
)
async def get_all_services():
    """
    Zwraca listę wszystkich monitorowanych usług.
    """
    service_monitor = system_deps.get_service_monitor()
    if service_monitor is None:
        raise HTTPException(status_code=503, detail="ServiceMonitor nie jest dostępny")

    try:
        cached = _services_cache.get()
        if cached is not None:
            return cached
        await service_monitor.check_health()
        services = service_monitor.get_all_services()

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

        payload = {
            "status": "success",
            "services": services_data,
            "count": len(services),
        }
        _services_cache.set(payload)
        return payload

    except Exception as e:
        logger.exception("Błąd podczas pobierania listy usług")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get(
    "/system/services/{service_name}",
    responses={
        503: {"description": "ServiceMonitor nie jest dostępny"},
        404: {"description": "Usługa o podanej nazwie nie istnieje"},
        500: {"description": "Błąd wewnętrzny podczas pobierania statusu usługi"},
    },
)
def get_service_status(service_name: str):
    """
    Zwraca szczegółowy status konkretnej usługi.
    """
    service_monitor = system_deps.get_service_monitor()
    if service_monitor is None:
        raise HTTPException(status_code=503, detail="ServiceMonitor nie jest dostępny")

    try:
        cached = _services_cache.get()
        if cached is not None:
            services = cached.get("services", [])
            services = [s for s in services if s.get("name") == service_name]
            if not services:
                raise HTTPException(
                    status_code=404, detail=f"Usługa {service_name} nie istnieje"
                )
            return {"status": "success", "service": services[0]}

        services = service_monitor.get_all_services()
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
        logger.exception("Błąd podczas sprawdzania statusu usługi %s", service_name)
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
