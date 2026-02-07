"""Endpointy konfiguracji modeli i capabilities."""

from typing import Optional

from fastapi import APIRouter, HTTPException

from venom_core.api.model_schemas.model_requests import ModelConfigUpdateRequest
from venom_core.api.routes.models_dependencies import get_model_registry
from venom_core.api.routes.models_utils import (
    load_generation_overrides,
    read_ollama_manifest_params,
    read_vllm_generation_config,
    save_generation_overrides,
    validate_generation_params,
)
from venom_core.core import metrics as metrics_module
from venom_core.core.generation_params_adapter import GenerationParamsAdapter
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])


@router.get("/models/{model_name}/capabilities")
async def get_model_capabilities_endpoint(model_name: str):
    """Pobiera capabilities modelu (wsparcie rol, templaty, etc.)."""
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        capabilities = model_registry.get_model_capabilities(model_name)
        if capabilities is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_name} nie znaleziony w manifeście",
            )

        capabilities_dict = {
            "supports_system_role": capabilities.supports_system_role,
            "supports_function_calling": capabilities.supports_function_calling,
            "allowed_roles": capabilities.allowed_roles,
            "prompt_template": capabilities.prompt_template,
            "max_context_length": capabilities.max_context_length,
            "quantization": capabilities.quantization,
        }

        if capabilities.generation_schema:
            capabilities_dict["generation_schema"] = {
                key: param.to_dict()
                for key, param in capabilities.generation_schema.items()
            }

        return {
            "success": True,
            "model_name": model_name,
            "capabilities": capabilities_dict,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas pobierania capabilities: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.get("/models/{model_name}/config")
async def get_model_config_endpoint(model_name: str, runtime: Optional[str] = None):
    """Pobiera schemat parametrow generacji dla modelu (generation_schema)."""
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        capabilities = model_registry.get_model_capabilities(model_name)
        if capabilities is None or capabilities.generation_schema is None:
            from venom_core.core.model_registry import _create_default_generation_schema

            logger.warning("Brak schematu w manifeście, używam domyślnego")
            generation_schema = _create_default_generation_schema()
        else:
            generation_schema = capabilities.generation_schema

        schema = {key: param.to_dict() for key, param in generation_schema.items()}
        runtime_info = get_active_llm_runtime()
        runtime_key = (
            GenerationParamsAdapter.normalize_provider(runtime)
            if runtime
            else GenerationParamsAdapter.normalize_provider(runtime_info.provider)
        )
        if runtime_key == "ollama":
            manifest_params = read_ollama_manifest_params(model_name)
            mapped = {
                "temperature": manifest_params.get("temperature"),
                "top_p": manifest_params.get("top_p"),
                "top_k": manifest_params.get("top_k"),
                "repeat_penalty": manifest_params.get("repeat_penalty"),
            }
            num_predict = manifest_params.get("num_predict")
            num_ctx = manifest_params.get("num_ctx")
            if num_predict is not None:
                mapped["max_tokens"] = num_predict
            elif num_ctx is not None:
                mapped["max_tokens"] = num_ctx
            for key, value in mapped.items():
                if key in schema and value is not None:
                    schema[key]["default"] = value
        if runtime_key == "vllm":
            gen_config = read_vllm_generation_config(model_name)
            mapped = {
                "temperature": gen_config.get("temperature"),
                "top_p": gen_config.get("top_p"),
                "top_k": gen_config.get("top_k"),
                "repeat_penalty": gen_config.get("repetition_penalty"),
            }
            max_new_tokens = gen_config.get("max_new_tokens")
            if max_new_tokens is not None:
                mapped["max_tokens"] = max_new_tokens
            for key, value in mapped.items():
                if key in schema and value is not None:
                    schema[key]["default"] = value
        defaults = {key: spec.get("default") for key, spec in schema.items()}
        overrides = load_generation_overrides().get(runtime_key, {}).get(model_name, {})
        current_values = {**defaults, **overrides}

        return {
            "success": True,
            "model_name": model_name,
            "generation_schema": schema,
            "current_values": current_values,
            "runtime": runtime_key,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas pobierania config: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")


@router.post("/models/{model_name}/config")
async def update_model_config_endpoint(
    model_name: str, request: ModelConfigUpdateRequest
):
    """Aktualizuje parametry generacji dla modelu (per runtime)."""
    model_registry = get_model_registry()
    if model_registry is None:
        raise HTTPException(status_code=503, detail="ModelRegistry nie jest dostępny")

    try:
        capabilities = model_registry.get_model_capabilities(model_name)
        if capabilities and capabilities.generation_schema is not None:
            generation_schema = capabilities.generation_schema
        else:
            from venom_core.core.model_registry import _create_default_generation_schema

            logger.warning("Brak schematu w manifeście podczas zapisu, używam domyślnego")
            generation_schema = _create_default_generation_schema()

        runtime_info = get_active_llm_runtime()
        runtime_key = (
            GenerationParamsAdapter.normalize_provider(request.runtime)
            if request.runtime
            else GenerationParamsAdapter.normalize_provider(runtime_info.provider)
        )

        schema = {key: param.to_dict() for key, param in generation_schema.items()}

        if request.params:
            validated = validate_generation_params(request.params, schema)
        else:
            validated = {}

        overrides = load_generation_overrides()
        overrides.setdefault(runtime_key, {})

        if not validated:
            overrides.get(runtime_key, {}).pop(model_name, None)
        else:
            overrides[runtime_key][model_name] = validated

        update_result = save_generation_overrides(overrides)
        if not update_result.get("success"):
            raise HTTPException(status_code=500, detail=update_result.get("message"))

        logger.info(
            "Zapisano parametry generacji: model=%s runtime=%s keys=%s",
            model_name,
            runtime_key,
            list(validated.keys()),
        )
        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_model_params_update()

        return {
            "success": True,
            "model_name": model_name,
            "runtime": runtime_key,
            "params": validated,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Błąd podczas zapisu config: {exc}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(exc)}")
