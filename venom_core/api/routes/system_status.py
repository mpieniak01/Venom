"""Moduł: routes/system_status - Endpointy statusu systemu."""

from fastapi import APIRouter, HTTPException

from venom_core.api.routes import system_deps
from venom_core.utils.boot_id import BOOT_ID
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get(
    "/system/status",
    responses={
        503: {"description": "ServiceMonitor nie jest dostępny"},
        500: {"description": "Błąd wewnętrzny podczas pobierania statusu systemu"},
    },
)
def get_system_status():
    """
    Zwraca status systemu wraz z metrykami użycia pamięci RAM i VRAM.
    """
    service_monitor = system_deps.get_service_monitor()
    if service_monitor is None:
        raise HTTPException(status_code=503, detail="ServiceMonitor nie jest dostępny")

    try:
        memory_metrics = service_monitor.get_memory_metrics()
        system_summary = service_monitor.get_summary()

        return {
            "status": "success",
            "boot_id": BOOT_ID,
            "system_healthy": system_summary["system_healthy"],
            "memory_usage_mb": memory_metrics["memory_usage_mb"],
            "memory_total_mb": memory_metrics["memory_total_mb"],
            "memory_usage_percent": memory_metrics["memory_usage_percent"],
            "vram_usage_mb": memory_metrics["vram_usage_mb"],
            "vram_total_mb": memory_metrics["vram_total_mb"],
            "vram_usage_percent": memory_metrics["vram_usage_percent"],
        }

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu systemu")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
