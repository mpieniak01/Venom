"""Moduł: routes/models - Endpointy API dla zarządzania modelami AI."""

import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, validator

from venom_core.core.model_manager import DEFAULT_MODEL_SIZE_GB
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])

# Dependencies - będą ustawione w main.py
_model_manager = None


class ModelInstallRequest(BaseModel):
    """Request do instalacji modelu."""

    name: str

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError('Nazwa modelu musi mieć 1-100 znaków')
        if not re.match(r'^[\w\-.:]+$', v):
            raise ValueError('Nazwa modelu zawiera niedozwolone znaki')
        return v


class ModelSwitchRequest(BaseModel):
    """Request do zmiany aktywnego modelu."""

    name: str
    role: Optional[str] = None  # Opcjonalnie: dla jakiej roli (np. "reasoning", "creative")

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError('Nazwa modelu musi mieć 1-100 znaków')
        if not re.match(r'^[\w\-.:]+$', v):
            raise ValueError('Nazwa modelu zawiera niedozwolone znaki')
        return v


def set_dependencies(model_manager):
    """Ustaw zależności dla routera."""
    global _model_manager
    _model_manager = model_manager


@router.get("/models")
async def list_models():
    """
    Zwraca listę modeli wraz z ich statusem.

    Returns:
        Lista modeli z metadanymi

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        models = await _model_manager.list_local_models()
        return {
            "success": True,
            "models": models,
            "count": len(models),
        }
    except Exception as e:
        logger.error(f"Błąd podczas listowania modeli: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/install")
async def install_model(request: ModelInstallRequest, background_tasks: BackgroundTasks):
    """
    Uruchamia pobieranie modelu w tle.

    Args:
        request: Żądanie z nazwą modelu
        background_tasks: Mechanizm zadań w tle FastAPI

    Returns:
        Status rozpoczęcia pobierania

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
        HTTPException: 400 jeśli brak miejsca na dysku (Resource Guard)
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    # Sprawdź Resource Guard przed rozpoczęciem
    if not _model_manager.check_storage_quota(additional_size_gb=DEFAULT_MODEL_SIZE_GB):
        raise HTTPException(
            status_code=400,
            detail="Brak miejsca na dysku. Usuń nieużywane modele lub zwiększ limit.",
        )

    try:

        async def pull_task():
            """Zadanie w tle - pobieranie modelu."""
            logger.info(f"Rozpoczynam pobieranie modelu w tle: {request.name}")
            success = await _model_manager.pull_model(request.name)
            if success:
                logger.info(f"✅ Model {request.name} pobrany pomyślnie")
            else:
                logger.error(f"❌ Nie udało się pobrać modelu {request.name}")

        # Dodaj zadanie do tła
        background_tasks.add_task(pull_task)

        return {
            "success": True,
            "message": f"Pobieranie modelu {request.name} rozpoczęte w tle",
            "model_name": request.name,
        }
    except Exception as e:
        logger.error(f"Błąd podczas inicjalizacji pobierania modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/switch")
async def switch_model(request: ModelSwitchRequest):
    """
    Zmienia aktywny model dla określonej roli.

    Args:
        request: Żądanie z nazwą modelu i opcjonalną rolą

    Returns:
        Status zmiany modelu

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
        HTTPException: 404 jeśli model nie istnieje
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        # Sprawdź czy model istnieje
        models = await _model_manager.list_local_models()
        model_exists = any(m["name"] == request.name for m in models)

        if not model_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Model {request.name} nie znaleziony",
            )

        # Aktywuj model (używając istniejącej metody activate_version)
        # Jeśli model nie jest zarejestrowany jako wersja, zarejestruj go
        if request.name not in _model_manager.versions:
            _model_manager.register_version(
                version_id=request.name,
                base_model=request.name,
            )

        success = _model_manager.activate_version(request.name)

        if success:
            return {
                "success": True,
                "message": f"Model {request.name} został aktywowany",
                "active_model": request.name,
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Nie udało się aktywować modelu",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas zmiany modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.delete("/models/{model_name}")
async def delete_model(model_name: str):
    """
    Usuwa model z dysku.

    Args:
        model_name: Nazwa modelu do usunięcia

    Returns:
        Status usunięcia

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
        HTTPException: 400 jeśli model jest aktywny (Safety Check) lub nieprawidłowa nazwa
        HTTPException: 404 jeśli model nie istnieje
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    # Walidacja nazwy modelu
    if not model_name or len(model_name) > 100 or not re.match(r'^[\w\-.:]+$', model_name):
        raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa modelu")

    try:
        success = await _model_manager.delete_model(model_name)

        if success:
            return {
                "success": True,
                "message": f"Model {model_name} został usunięty",
            }
        else:
            # Sprawdź czy to problem z aktywnym modelem
            if (
                _model_manager.active_version
                and model_name == _model_manager.active_version
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Nie można usunąć aktywnego modelu. Najpierw zmień model.",
                )
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_name} nie znaleziony lub nie można usunąć",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas usuwania modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/usage")
async def get_models_usage():
    """
    Zwraca metryki użycia: zajętość dysku (GB) oraz użycie VRAM.

    Returns:
        Słownik z metrykami

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        metrics = await _model_manager.get_usage_metrics()
        return {
            "success": True,
            "usage": metrics,
        }
    except Exception as e:
        logger.error(f"Błąd podczas pobierania metryk: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/unload-all")
async def unload_all_models():
    """
    Panic Button - wymusza zwolnienie pamięci VRAM/RAM.

    Returns:
        Status operacji

    Raises:
        HTTPException: 503 jeśli ModelManager nie jest dostępny
    """
    if _model_manager is None:
        raise HTTPException(status_code=503, detail="ModelManager nie jest dostępny")

    try:
        success = await _model_manager.unload_all()

        if success:
            return {
                "success": True,
                "message": "Wszystkie zasoby modeli zostały zwolnione",
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Nie udało się zwolnić zasobów",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas zwalniania zasobów: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")
