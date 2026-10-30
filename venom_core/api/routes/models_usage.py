"""Endpointy zwiazane z metrykami i unloadingiem modeli."""

from fastapi import APIRouter, HTTPException

from venom_core.api.routes.models_dependencies import get_model_manager
from venom_core.utils.async_snapshot_cache import AsyncSnapshotCache
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])

# UI telemetry only: admission checks must not read this cache.
_models_usage_cache = AsyncSnapshotCache[dict](ttl_seconds=5.0, timeout_seconds=2.0)


@router.get(
    "/models/usage",
    responses={
        503: {"description": "ModelManager nie jest dostępny"},
        500: {"description": "Błąd serwera podczas pobierania metryk modeli"},
    },
)
async def get_models_usage():
    """
    Zwraca metryki uzycia: zajetosc dysku (GB) oraz uzycie VRAM.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:

        async def collect():
            return {"success": True, "usage": await model_manager.get_usage_metrics()}

        snapshot = await _models_usage_cache.get_or_refresh(
            collect, owner=model_manager
        )
        return {
            **snapshot.value,
            "telemetry": {
                "sample_age_seconds": round(snapshot.age_seconds, 3),
                "stale": snapshot.stale,
                "refreshing": snapshot.refreshing,
                "refresh_failed": snapshot.refresh_failed,
            },
        }
    except TimeoutError as exc:
        raise HTTPException(
            status_code=503, detail={"reason_code": "MODELS_USAGE_TIMEOUT"}
        ) from exc
    except Exception as exc:
        logger.error(f"Błąd podczas pobierania metryk: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.post(
    "/models/unload-all",
    responses={
        503: {"description": "ModelManager nie jest dostępny"},
        500: {"description": "Błąd serwera podczas zwalniania zasobów modeli"},
    },
)
async def unload_all_models():
    """
    Panic Button - wymusza zwolnienie pamieci VRAM/RAM.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        success = await model_manager.unload_all()
        if success:
            # Unieważnij cache, aby UI od razu pokazało 0 VRAM
            _models_usage_cache.clear()
            return {
                "success": True,
                "message": "Wszystkie zasoby modeli zostały zwolnione",
            }
        raise HTTPException(status_code=500, detail="Nie udało się zwolnić zasobów")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas zwalniania zasobów: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")
