"""Logika aktywacji/runtime dla ModelRegistry."""

from pathlib import Path
from typing import Any

from venom_core.core.model_registry_types import ModelMetadata, ModelProvider
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def activate_model(registry: Any, model_name: str, runtime: str) -> bool:
    """
    Aktywuje model dla danego runtime (prosty update konfiguracji).

    Returns:
        True jeśli sukces
    """
    logger.info(f"Aktywacja modelu {model_name} dla runtime {runtime}")

    if not await ensure_model_metadata_for_activation(registry, model_name, runtime):
        return False

    meta = registry.manifest.get(model_name)
    if not meta:
        logger.error("Brak metadanych modelu %s po aktywacji", model_name)
        return False

    try:
        settings = apply_model_activation_config(registry, model_name, runtime, meta)
        await restart_runtime_after_activation(runtime, settings)
    except Exception as e:
        logger.warning(
            f"Nie udało się zaktualizować SETTINGS/config dla {model_name}: {e}"
        )
        return False

    logger.info(f"Model {model_name} aktywowany (runtime={runtime})")
    return True


async def ensure_model_metadata_for_activation(
    registry: Any, model_name: str, runtime: str
) -> bool:
    if model_name in registry.manifest:
        return True
    if runtime != "ollama":
        logger.error(f"Model {model_name} nie znaleziony w manifeście")
        return False
    provider = registry.providers.get(ModelProvider.OLLAMA)
    if not provider:
        logger.error("Provider Ollama niedostępny")
        return False
    try:
        metadata = await provider.get_model_info(model_name)
        if not metadata:
            logger.error(f"Model {model_name} nie znaleziony w Ollama")
            return False
        registry.manifest[model_name] = metadata
        registry._save_manifest()
        return True
    except Exception as exc:
        logger.warning(
            f"Nie udało się pobrać metadanych modelu Ollama {model_name}: {exc}"
        )
        return False


def apply_model_activation_config(
    registry: Any, model_name: str, runtime: str, meta: ModelMetadata
):
    from venom_core.config import SETTINGS
    from venom_core.services.config_manager import config_manager

    updates = {
        "LLM_MODEL_NAME": model_name,
        "ACTIVE_LLM_SERVER": runtime,
    }
    if runtime == "vllm":
        apply_vllm_activation_updates(model_name, meta, updates, SETTINGS)
    if runtime == "ollama":
        updates["LAST_MODEL_OLLAMA"] = model_name

    config_manager.update_config(updates)
    SETTINGS.LLM_MODEL_NAME = model_name
    SETTINGS.ACTIVE_LLM_SERVER = runtime
    if runtime == "ollama":
        safe_setattr(SETTINGS, "LAST_MODEL_OLLAMA", model_name)
    if runtime == "vllm":
        safe_setattr(SETTINGS, "LAST_MODEL_VLLM", model_name)
    return SETTINGS


def apply_vllm_activation_updates(*args: Any) -> None:
    if len(args) == 4:
        model_name, meta, updates, settings = args
    elif len(args) == 5:
        _, model_name, meta, updates, settings = args
    else:
        raise TypeError(
            "apply_vllm_activation_updates expects 4 args "
            "(model_name, meta, updates, settings) or legacy 5 args"
        )

    template_value = ""
    local_path = meta.local_path or model_name
    template_candidate = Path(local_path) / "chat_template.jinja"
    if not template_candidate.is_absolute():
        template_candidate = Path(settings.REPO_ROOT) / template_candidate
    if template_candidate.exists():
        template_value = str(template_candidate)
    updates.update(
        {
            "VLLM_MODEL_PATH": local_path,
            "VLLM_SERVED_MODEL_NAME": model_name,
            "VLLM_CHAT_TEMPLATE": template_value,
            "LAST_MODEL_VLLM": model_name,
        }
    )
    settings.VLLM_MODEL_PATH = local_path
    settings.VLLM_SERVED_MODEL_NAME = model_name
    safe_setattr(settings, "VLLM_CHAT_TEMPLATE", template_value)


def safe_setattr(target: Any, attr: str, value: Any) -> None:
    try:
        setattr(target, attr, value)
    except Exception as exc:
        logger.debug(
            "Nie udało się ustawić atrybutu %s na obiekcie %r: %s",
            attr,
            target,
            exc,
        )


async def restart_runtime_after_activation(runtime: str, settings: Any) -> None:
    try:
        from venom_core.core.llm_server_controller import LlmServerController

        controller = LlmServerController(settings)
        if controller.has_server(runtime):
            result = await controller.run_action(runtime, "restart")
            if not result.ok:
                logger.warning(
                    "Restart %s po aktywacji modelu nie powiódł się: %s",
                    runtime,
                    result.stderr,
                )
    except Exception as exc:
        logger.warning("Nie udało się wykonać restartu %s: %s", runtime, exc)
