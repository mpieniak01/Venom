"""Endpointy instalacji i wyboru modeli (local models)."""

from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException

from venom_core.api.model_schemas.model_requests import (
    ModelInstallRequest,
    ModelSwitchRequest,
)
from venom_core.api.model_schemas.model_validators import validate_model_name_basic
from venom_core.api.routes.models_dependencies import get_model_manager
from venom_core.api.routes.models_utils import resolve_model_provider, update_last_model
from venom_core.config import SETTINGS
from venom_core.core.model_manager import DEFAULT_MODEL_SIZE_GB
from venom_core.services.config_manager import config_manager
from venom_core.utils.llm_runtime import (
    compute_llm_config_hash,
    get_active_llm_runtime,
    probe_runtime_status,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])
MODEL_MANAGER_UNAVAILABLE_DETAIL = "ModelManager nie jest dostępny"


def _ensure_model_exists(models: list[dict], model_name: str) -> None:
    if any(m["name"] == model_name for m in models):
        return
    raise HTTPException(status_code=404, detail=f"Model {model_name} nie znaleziony")


def _ensure_runtime_provider_match(
    *,
    model_name: str,
    models: list[dict],
    active_provider: str,
) -> str | None:
    model_provider = resolve_model_provider(models, model_name)
    if active_provider in {"ollama", "vllm"} and model_provider:
        if model_provider != active_provider:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Model {model_name} należy do {model_provider}, "
                    f"ale aktywny runtime to {active_provider}"
                ),
            )
    return model_provider


def _ensure_registered_version(model_manager, model_name: str) -> None:
    if model_name in model_manager.versions:
        return
    model_manager.register_version(version_id=model_name, base_model=model_name)


def _update_runtime_settings(model_name: str) -> None:
    try:
        SETTINGS.LLM_MODEL_NAME = model_name
        SETTINGS.HYBRID_LOCAL_MODEL = model_name
        SETTINGS.LLM_SERVICE_TYPE = "local"
    except Exception:
        logger.warning("Nie udało się zaktualizować SETTINGS w pamięci.")


def _update_config_for_active_model(*, active_provider: str, model_name: str) -> None:
    config_manager.update_config(
        {
            "LLM_MODEL_NAME": model_name,
            "HYBRID_LOCAL_MODEL": model_name,
            "LLM_SERVICE_TYPE": "local",
        }
    )
    config_hash = compute_llm_config_hash(
        active_provider, SETTINGS.LLM_LOCAL_ENDPOINT, model_name
    )
    config_manager.update_config({"LLM_CONFIG_HASH": config_hash})
    try:
        SETTINGS.LLM_CONFIG_HASH = config_hash
    except Exception:
        logger.warning("Nie udało się zaktualizować LLM_CONFIG_HASH w SETTINGS.")


def _resolve_provider_bucket(models: List[dict]) -> Dict[str, List[dict]]:
    provider_buckets: Dict[str, List[dict]] = {}

    def resolve_provider(model: dict) -> str:
        provider = model.get("provider")
        if isinstance(provider, str) and provider:
            return provider
        if model.get("source") == "ollama":
            return "ollama"
        return "vllm"

    for model in models:
        provider = resolve_provider(model)
        model.setdefault("provider", provider)
        provider_buckets.setdefault(provider, []).append(model)

    return provider_buckets


@router.get(
    "/models",
    responses={
        503: {"description": MODEL_MANAGER_UNAVAILABLE_DETAIL},
        500: {"description": "Błąd serwera podczas listowania modeli"},
    },
)
async def list_models():
    """
    Zwraca liste modeli wraz z ich statusem.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail=MODEL_MANAGER_UNAVAILABLE_DETAIL)

    try:
        models = await model_manager.list_local_models()
        runtime_info = get_active_llm_runtime()
        runtime_status, runtime_error = await probe_runtime_status(runtime_info)
        runtime_payload = runtime_info.to_payload()
        runtime_payload["status"] = runtime_status
        if runtime_error:
            runtime_payload["error"] = runtime_error
        runtime_payload["configured_models"] = {
            "local": SETTINGS.LLM_MODEL_NAME,
            "hybrid_local": getattr(SETTINGS, "HYBRID_LOCAL_MODEL", None),
            "cloud": getattr(SETTINGS, "HYBRID_CLOUD_MODEL", None),
        }

        active_names = {
            SETTINGS.LLM_MODEL_NAME,
            getattr(SETTINGS, "HYBRID_LOCAL_MODEL", None),
        }
        active_names = {name for name in active_names if name}
        active_names.update({Path(name).name for name in active_names})

        for model in models:
            candidate_names = {model.get("name")}
            path_value = model.get("path")
            if path_value:
                candidate_names.add(Path(path_value).name)
            if any(name in active_names for name in candidate_names if name):
                model["active"] = True
                model.setdefault("source", runtime_info.provider)

        provider_buckets = _resolve_provider_bucket(models)

        return {
            "success": True,
            "models": models,
            "count": len(models),
            "active": runtime_payload,
            "providers": provider_buckets,
        }
    except Exception as exc:
        logger.error(f"Błąd podczas listowania modeli: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.post(
    "/models/install",
    responses={
        503: {"description": MODEL_MANAGER_UNAVAILABLE_DETAIL},
        400: {"description": "Brak miejsca na dysku lub nieprawidłowe dane"},
        500: {"description": "Błąd serwera podczas inicjalizacji instalacji"},
    },
)
def install_model(request: ModelInstallRequest, background_tasks: BackgroundTasks):
    """
    Uruchamia pobieranie modelu w tle.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail=MODEL_MANAGER_UNAVAILABLE_DETAIL)

    if not model_manager.check_storage_quota(additional_size_gb=DEFAULT_MODEL_SIZE_GB):
        raise HTTPException(
            status_code=400,
            detail=("Brak miejsca na dysku. Usuń nieużywane modele lub zwiększ limit."),
        )

    try:

        async def pull_task():
            logger.info(f"Rozpoczynam pobieranie modelu w tle: {request.name}")
            success = await model_manager.pull_model(request.name)
            if success:
                logger.info(f"✅ Model {request.name} pobrany pomyślnie")
            else:
                logger.error(f"❌ Nie udało się pobrać modelu {request.name}")

        background_tasks.add_task(pull_task)

        return {
            "success": True,
            "message": f"Pobieranie modelu {request.name} rozpoczęte w tle",
            "model_name": request.name,
        }
    except Exception as exc:
        logger.error(f"Błąd podczas inicjalizacji pobierania modelu: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.post(
    "/models/switch",
    responses={
        503: {"description": MODEL_MANAGER_UNAVAILABLE_DETAIL},
        404: {"description": "Model nie został znaleziony"},
        400: {"description": "Model niezgodny z aktywnym runtime"},
        500: {"description": "Błąd serwera podczas zmiany modelu"},
    },
)
async def switch_model(request: ModelSwitchRequest):
    """
    Zmienia aktywny model dla okreslonej roli.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail=MODEL_MANAGER_UNAVAILABLE_DETAIL)

    try:
        models = await model_manager.list_local_models()
        _ensure_model_exists(models, request.name)

        runtime_info = get_active_llm_runtime()
        active_provider = runtime_info.provider
        model_provider = _ensure_runtime_provider_match(
            model_name=request.name,
            models=models,
            active_provider=active_provider,
        )
        _ensure_registered_version(model_manager, request.name)

        success = model_manager.activate_version(request.name)

        if success:
            _update_runtime_settings(request.name)
            _update_config_for_active_model(
                active_provider=active_provider,
                model_name=request.name,
            )
            if model_provider:
                update_last_model(model_provider, request.name)
            return {
                "success": True,
                "message": f"Model {request.name} został aktywowany",
                "active_model": request.name,
            }

        raise HTTPException(status_code=500, detail="Nie udało się aktywować modelu")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas zmiany modelu: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.delete(
    "/models/{model_name}",
    responses={
        503: {"description": MODEL_MANAGER_UNAVAILABLE_DETAIL},
        400: {"description": "Nieprawidłowa nazwa modelu lub aktywny model"},
        404: {"description": "Model nie został znaleziony"},
        500: {"description": "Błąd serwera podczas usuwania modelu"},
    },
)
async def delete_model(model_name: str):
    """
    Usuwa model z dysku.
    """
    model_manager = get_model_manager()
    if model_manager is None:
        raise HTTPException(status_code=503, detail=MODEL_MANAGER_UNAVAILABLE_DETAIL)

    try:
        validate_model_name_basic(model_name, max_length=100)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        success = await model_manager.delete_model(model_name)
        if success:
            return {"success": True, "message": f"Model {model_name} został usunięty"}

        if model_manager.active_version and model_name == model_manager.active_version:
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
    except Exception as exc:
        logger.error(f"Błąd podczas usuwania modelu: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")
