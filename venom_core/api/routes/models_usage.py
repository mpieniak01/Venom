"""Endpointy zwiazane z metrykami i unloadingiem modeli."""

from fastapi import APIRouter, HTTPException

from venom_core.api.routes.models_dependencies import get_model_manager
from venom_core.utils.logger import get_logger
from venom_core.utils.ttl_cache import TTLCache

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])

# Cache dla metryk użycia modeli (5 sekund TTL)
_models_usage_cache = TTLCache[dict](ttl_seconds=5.0)


@router.get("/models/usage")
async def get_models_usage():
    """
    Zwraca metryki uzycia: zajetosc dysku (GB) oraz uzycie VRAM.
    """
    cached = _models_usage_cache.get()
    if cached is not None:
        return cached

    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        metrics = await model_manager.get_usage_metrics()
        res = {"success": True, "usage": metrics}
        _models_usage_cache.set(res)
        return res
    except Exception as exc:
        logger.error(f"Błąd podczas pobierania metryk: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.post("/models/unload-all")
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
