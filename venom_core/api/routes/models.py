"""Moduł: routes/models - Endpointy API dla zarządzania modelami AI."""

import re
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, field_validator

from venom_core.config import SETTINGS
from venom_core.core.model_manager import DEFAULT_MODEL_SIZE_GB
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])

# Dependencies - będą ustawione w main.py
_model_manager = None
_model_registry = None


class ModelInstallRequest(BaseModel):
    """Request do instalacji modelu."""

    name: str

    @field_validator("name")
    def validate_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError("Nazwa modelu musi mieć 1-100 znaków")
        if not re.match(r"^[\w\-.:]+$", v):
            raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
        return v


class ModelSwitchRequest(BaseModel):
    """Request do zmiany aktywnego modelu."""

    name: str
    role: Optional[str] = (
        None  # Opcjonalnie: dla jakiej roli (np. "reasoning", "creative")
    )

    @field_validator("name")
    def validate_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError("Nazwa modelu musi mieć 1-100 znaków")
        if not re.match(r"^[\w\-.:]+$", v):
            raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
        return v


class ModelRegistryInstallRequest(BaseModel):
    """Request do instalacji modelu przez ModelRegistry."""

    name: str
    provider: str  # "huggingface" lub "ollama"
    runtime: str = "vllm"  # "vllm" lub "ollama"

    @field_validator("name")
    def validate_name(cls, v):
        if not v or len(v) > 200:
            raise ValueError("Nazwa modelu musi mieć 1-200 znaków")
        # Allow HF model names with forward slash
        if not re.match(r"^[\w\-.:\/]+$", v):
            raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
        return v

    @field_validator("provider")
    def validate_provider(cls, v):
        if v not in ["huggingface", "ollama"]:
            raise ValueError("Provider musi być 'huggingface' lub 'ollama'")
        return v

    @field_validator("runtime")
    def validate_runtime(cls, v):
        if v not in ["vllm", "ollama"]:
            raise ValueError("Runtime musi być 'vllm' lub 'ollama'")
        return v


class ModelActivateRequest(BaseModel):
    """Request do aktywacji modelu."""

    name: str
    runtime: str

    @field_validator("name")
    def validate_name(cls, v):
        if not v or len(v) > 200:
            raise ValueError("Nazwa modelu musi mieć 1-200 znaków")
        if not re.match(r"^[\w\-.:\/]+$", v):
            raise ValueError("Nazwa modelu zawiera niedozwolone znaki")
        return v

    @field_validator("runtime")
    def validate_runtime(cls, v):
        if v not in ["vllm", "ollama"]:
            raise ValueError("Runtime musi być 'vllm' lub 'ollama'")
        return v


def set_dependencies(model_manager, model_registry=None):
    """Ustaw zależności dla routera."""
    global _model_manager, _model_registry
    _model_manager = model_manager
    _model_registry = model_registry


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
        provider_buckets: Dict[str, List[dict]] = {}

        def resolve_provider(model: dict) -> str:
            provider = model.get("provider")
            if isinstance(provider, str) and provider:
                return provider
            if model.get("source") == "ollama":
                return "ollama"
            return "vllm"

        runtime_info = get_active_llm_runtime()
        runtime_payload = runtime_info.to_payload()
        runtime_payload["status"] = "ready"
        runtime_payload["configured_models"] = {
            "local": SETTINGS.LLM_MODEL_NAME,
            "hybrid_local": getattr(SETTINGS, "HYBRID_LOCAL_MODEL", None),
            "cloud": getattr(SETTINGS, "HYBRID_CLOUD_MODEL", None),
        }

        active_names = {
            SETTINGS.LLM_MODEL_NAME,
            getattr(SETTINGS, "HYBRID_LOCAL_MODEL", None),
        }
        active_names = {name for name in active_names if name}  # usuń None
        active_names.update({Path(name).name for name in list(active_names)})

        for model in models:
            candidate_names = {model.get("name")}
            path_value = model.get("path")
            if path_value:
                candidate_names.add(Path(path_value).name)
            if any(name in active_names for name in candidate_names if name):
                model["active"] = True
                model.setdefault("source", runtime_info.provider)
            provider = resolve_provider(model)
            model.setdefault("provider", provider)
            provider_buckets.setdefault(provider, []).append(model)
        return {
            "success": True,
            "models": models,
            "count": len(models),
            "active": runtime_payload,
            "providers": provider_buckets,
        }
    except Exception as e:
        logger.error(f"Błąd podczas listowania modeli: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/install")
async def install_model(
    request: ModelInstallRequest, background_tasks: BackgroundTasks
):
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
    if (
        not model_name
        or len(model_name) > 100
        or not re.match(r"^[\w\-.:]+$", model_name)
    ):
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


# ===== Nowe endpointy ModelRegistry =====


@router.get("/models/providers")
async def list_model_providers(provider: Optional[str] = None):
    """
    Lista dostępnych modeli ze wszystkich providerów.

    Args:
        provider: Opcjonalny filtr po providerze (huggingface, ollama)

    Returns:
        Lista modeli dostępnych do instalacji

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        from venom_core.core.model_registry import ModelProvider

        provider_enum = None
        if provider:
            try:
                provider_enum = ModelProvider(provider.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Nieprawidłowy provider: {provider}"
                )

        models = await _model_registry.list_available_models(provider=provider_enum)

        return {
            "success": True,
            "models": [model.to_dict() for model in models],
            "count": len(models),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas listowania providerów: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/registry/install")
async def install_model_registry(request: ModelRegistryInstallRequest):
    """
    Instaluje model przez ModelRegistry (HuggingFace lub Ollama).

    Args:
        request: Żądanie z nazwą modelu, providerem i runtime

    Returns:
        operation_id do sprawdzania statusu instalacji

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 400 jeśli nieprawidłowe dane wejściowe
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        from venom_core.core.model_registry import ModelProvider

        provider_enum = ModelProvider(request.provider.lower())

        operation_id = await _model_registry.install_model(
            model_name=request.name,
            provider=provider_enum,
            runtime=request.runtime,
        )

        return {
            "success": True,
            "operation_id": operation_id,
            "message": f"Instalacja modelu {request.name} rozpoczęta",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Błąd podczas rozpoczynania instalacji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.delete("/models/registry/{model_name}")
async def remove_model_registry(model_name: str):
    """
    Usuwa model przez ModelRegistry.

    Args:
        model_name: Nazwa modelu do usunięcia

    Returns:
        operation_id do sprawdzania statusu usuwania

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 404 jeśli model nie znaleziony
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        operation_id = await _model_registry.remove_model(model_name)

        return {
            "success": True,
            "operation_id": operation_id,
            "message": f"Usuwanie modelu {model_name} rozpoczęte",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Błąd podczas usuwania modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/models/activate")
async def activate_model_endpoint(request: ModelActivateRequest):
    """
    Aktywuje model dla danego runtime.

    Args:
        request: Żądanie z nazwą modelu i runtime

    Returns:
        Status aktywacji

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 404 jeśli model nie znaleziony
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        success = await _model_registry.activate_model(
            model_name=request.name, runtime=request.runtime
        )

        if success:
            return {
                "success": True,
                "message": f"Model {request.name} aktywowany dla runtime {request.runtime}",
            }
        else:
            raise HTTPException(
                status_code=500, detail="Nie udało się aktywować modelu"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas aktywacji modelu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/operations")
async def list_model_operations(limit: int = 10):
    """
    Lista ostatnich operacji na modelach.

    Args:
        limit: Maksymalna liczba operacji do zwrócenia

    Returns:
        Lista operacji z ich statusami

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        operations = _model_registry.list_operations(limit=limit)

        return {
            "success": True,
            "operations": [op.to_dict() for op in operations],
            "count": len(operations),
        }
    except Exception as e:
        logger.error(f"Błąd podczas listowania operacji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/operations/{operation_id}")
async def get_operation_status_endpoint(operation_id: str):
    """
    Pobiera status operacji.

    Args:
        operation_id: ID operacji

    Returns:
        Status operacji

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 404 jeśli operacja nie znaleziona
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        operation = _model_registry.get_operation_status(operation_id)

        if operation is None:
            raise HTTPException(status_code=404, detail="Operacja nie znaleziona")

        return {
            "success": True,
            "operation": operation.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania statusu operacji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/models/{model_name}/capabilities")
async def get_model_capabilities_endpoint(model_name: str):
    """
    Pobiera capabilities modelu (wsparcie ról, templaty, etc.).

    Args:
        model_name: Nazwa modelu

    Returns:
        Capabilities modelu

    Raises:
        HTTPException: 503 jeśli ModelRegistry nie jest dostępny
        HTTPException: 404 jeśli model nie znaleziony
    """
    if _model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        capabilities = _model_registry.get_model_capabilities(model_name)

        if capabilities is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_name} nie znaleziony w manifeście",
            )

        return {
            "success": True,
            "model_name": model_name,
            "capabilities": {
                "supports_system_role": capabilities.supports_system_role,
                "supports_function_calling": capabilities.supports_function_calling,
                "allowed_roles": capabilities.allowed_roles,
                "prompt_template": capabilities.prompt_template,
                "max_context_length": capabilities.max_context_length,
                "quantization": capabilities.quantization,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania capabilities: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")
