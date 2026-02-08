"""Endpointy operacji na modelach registry (install/remove/activate/operations)."""

from fastapi import APIRouter, HTTPException

from venom_core.api.model_schemas.model_requests import (
    ModelActivateRequest,
    ModelRegistryInstallRequest,
)
from venom_core.api.routes.models_dependencies import get_model_registry
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])
MODEL_REGISTRY_UNAVAILABLE_DETAIL = "ModelRegistry nie jest dostępny"


@router.post(
    "/models/registry/install",
    responses={
        503: {"description": MODEL_REGISTRY_UNAVAILABLE_DETAIL},
        400: {"description": "Nieprawidłowe dane wejściowe dla instalacji modelu"},
        500: {"description": "Błąd serwera podczas uruchamiania instalacji modelu"},
    },
)
async def install_model_registry(request: ModelRegistryInstallRequest):
    """
    Instaluje model przez ModelRegistry (HuggingFace lub Ollama).
    """
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail=MODEL_REGISTRY_UNAVAILABLE_DETAIL)

    try:
        from venom_core.core.model_registry import ModelProvider

        provider_enum = ModelProvider(request.provider.lower())

        logger.info(
            "Install registry model: %s provider=%s runtime=%s",
            request.name,
            request.provider,
            request.runtime,
        )
        operation_id = await model_registry.install_model(
            model_name=request.name,
            provider=provider_enum,
            runtime=request.runtime,
        )

        return {
            "success": True,
            "operation_id": operation_id,
            "message": f"Instalacja modelu {request.name} rozpoczęta",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Błąd podczas rozpoczynania instalacji: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.delete(
    "/models/registry/{model_name}",
    responses={
        503: {"description": MODEL_REGISTRY_UNAVAILABLE_DETAIL},
        404: {"description": "Model nie został znaleziony"},
        500: {"description": "Błąd serwera podczas usuwania modelu"},
    },
)
async def remove_model_registry(model_name: str):
    """
    Usuwa model przez ModelRegistry.
    """
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail=MODEL_REGISTRY_UNAVAILABLE_DETAIL)

    try:
        logger.info("Remove registry model: %s", model_name)
        operation_id = await model_registry.remove_model(model_name)

        return {
            "success": True,
            "operation_id": operation_id,
            "message": f"Usuwanie modelu {model_name} rozpoczęte",
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Błąd podczas usuwania modelu: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.post(
    "/models/activate",
    responses={
        503: {"description": MODEL_REGISTRY_UNAVAILABLE_DETAIL},
        500: {"description": "Błąd serwera podczas aktywacji modelu"},
    },
)
async def activate_model_endpoint(request: ModelActivateRequest):
    """
    Aktywuje model dla danego runtime.
    """
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail=MODEL_REGISTRY_UNAVAILABLE_DETAIL)

    try:
        logger.info("Activate model: %s runtime=%s", request.name, request.runtime)
        success = await model_registry.activate_model(
            model_name=request.name, runtime=request.runtime
        )

        if success:
            # po aktywacji spróbuj zwrócić status health runtime
            from venom_core.utils.llm_runtime import (
                get_active_llm_runtime,
                probe_runtime_status,
            )

            runtime_info = get_active_llm_runtime()
            runtime_status, runtime_error = await probe_runtime_status(runtime_info)
            return {
                "success": True,
                "message": f"Model {request.name} aktywowany dla runtime {request.runtime}",
                "runtime": runtime_info.to_payload()
                | {"status": runtime_status, "error": runtime_error},
            }
        raise HTTPException(status_code=500, detail="Nie udało się aktywować modelu")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas aktywacji modelu: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.get(
    "/models/operations",
    responses={
        503: {"description": MODEL_REGISTRY_UNAVAILABLE_DETAIL},
        500: {"description": "Błąd serwera podczas pobierania listy operacji"},
    },
)
async def list_model_operations(limit: int = 10):
    """
    Lista ostatnich operacji na modelach.
    """
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail=MODEL_REGISTRY_UNAVAILABLE_DETAIL)

    try:
        operations = model_registry.list_operations(limit=limit)

        return {
            "success": True,
            "operations": [op.to_dict() for op in operations],
            "count": len(operations),
        }
    except Exception as exc:
        logger.error(f"Błąd podczas listowania operacji: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.get(
    "/models/operations/{operation_id}",
    responses={
        503: {"description": MODEL_REGISTRY_UNAVAILABLE_DETAIL},
        404: {"description": "Operacja nie została znaleziona"},
        500: {"description": "Błąd serwera podczas pobierania statusu operacji"},
    },
)
async def get_operation_status_endpoint(operation_id: str):
    """
    Pobiera status operacji.
    """
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail=MODEL_REGISTRY_UNAVAILABLE_DETAIL)

    try:
        operation = model_registry.get_operation_status(operation_id)
        if operation is None:
            raise HTTPException(status_code=404, detail="Operacja nie znaleziona")

        return {"success": True, "operation": operation.to_dict()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas pobierania statusu operacji: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")
