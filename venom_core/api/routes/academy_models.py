"""Thin API facade for Academy model and adapter operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import anyio

from venom_core.api.schemas.academy import AdapterInfo
from venom_core.config import SETTINGS
from venom_core.services.academy import adapter_audit_service as _audit_service
from venom_core.services.academy import adapter_metadata_service as _metadata_service
from venom_core.services.academy import adapter_runtime_service as _runtime_service
from venom_core.services.academy import trainable_catalog_service as _catalog_service
from venom_core.services.academy.adapter_metadata_service import (
    ADAPTER_NOT_FOUND_DETAIL,
    _require_trusted_adapter_base_model,
)
from venom_core.services.academy.trainable_catalog_service import (
    _canonical_runtime_model_id,
    list_trainable_models,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Patch points retained for compatibility with existing tests.
config_manager = _runtime_service.config_manager
compute_llm_config_hash = _runtime_service.compute_llm_config_hash
get_active_llm_runtime = _runtime_service.get_active_llm_runtime

# Public helpers kept for backwards compatibility of academy_models module API.
ADAPTER_BASE_MODEL_MISMATCH = _metadata_service.ADAPTER_BASE_MODEL_MISMATCH
ADAPTER_BASE_MODEL_UNKNOWN = _metadata_service.ADAPTER_BASE_MODEL_UNKNOWN
ADAPTER_METADATA_INCONSISTENT = _metadata_service.ADAPTER_METADATA_INCONSISTENT
_assert_runtime_model_available = _metadata_service._assert_runtime_model_available
_infer_local_runtime_provider = _metadata_service._infer_local_runtime_provider

add_trainable_model_from_catalog = _catalog_service.add_trainable_model_from_catalog
build_model_label = _catalog_service.build_model_label
classify_model_cost_tier = _catalog_service.classify_model_cost_tier
classify_model_source_type = _catalog_service.classify_model_source_type
collect_default_trainable_models = _catalog_service.collect_default_trainable_models
collect_local_trainable_models = _catalog_service.collect_local_trainable_models
discover_available_runtime_targets = _catalog_service.discover_available_runtime_targets
ensure_default_model_visible = _catalog_service.ensure_default_model_visible
get_default_trainable_models_catalog = (
    _catalog_service.get_default_trainable_models_catalog
)
get_model_non_trainable_reason = _catalog_service.get_model_non_trainable_reason
is_model_trainable = _catalog_service.is_model_trainable
resolve_model_priority_bucket = _catalog_service.resolve_model_priority_bucket
resolve_recommended_runtime = _catalog_service.resolve_recommended_runtime
resolve_runtime_compatibility = _catalog_service.resolve_runtime_compatibility

_INITIAL_SETTINGS = SETTINGS


def _resolve_settings_for_call() -> Any:
    from venom_core.config import SETTINGS as config_settings

    current = globals().get("SETTINGS", config_settings)
    if current is not _INITIAL_SETTINGS:
        return current
    return config_settings


def _resolve_repo_root() -> Path:
    return _runtime_service._resolve_repo_root(
        settings_obj=_resolve_settings_for_call()
    )


def _resolve_local_runtime_model_path_by_name(
    *,
    mgr: Any,
    model_name: str,
    settings_obj: Any | None = None,
) -> str:
    settings = settings_obj or _resolve_settings_for_call()
    return _runtime_service._resolve_local_runtime_model_path_by_name(
        mgr=mgr,
        model_name=model_name,
        settings_obj=settings,
        resolve_repo_root_fn=lambda **_kwargs: _resolve_repo_root(),
    )


def _restart_vllm_runtime(*, settings_obj: Any | None = None) -> None:
    settings = settings_obj or _resolve_settings_for_call()
    return _runtime_service._restart_vllm_runtime(
        resolve_repo_root_fn=lambda **_kwargs: _resolve_repo_root(),
        settings_obj=settings,
    )


def _runtime_endpoint_for_hash(
    runtime_id: str,
    *,
    settings_obj: Any | None = None,
) -> str | None:
    settings = settings_obj or _resolve_settings_for_call()
    return _runtime_service._runtime_endpoint_for_hash(
        runtime_id,
        settings_obj=settings,
    )


def _resolve_runtime_for_adapter_deploy(
    runtime_id: str | None,
    *,
    get_active_llm_runtime_fn: Any | None = None,
    settings_obj: Any | None = None,
) -> str:
    settings = settings_obj or _resolve_settings_for_call()
    active_runtime_fn = get_active_llm_runtime_fn or get_active_llm_runtime
    return _runtime_service._resolve_runtime_for_adapter_deploy(
        runtime_id,
        get_active_llm_runtime_fn=active_runtime_fn,
        settings_obj=settings,
    )


def _is_runtime_model_dir(path: Path) -> bool:
    return _runtime_service._is_runtime_model_dir(path)


def _build_vllm_runtime_model_from_adapter(
    *,
    adapter_dir: Path,
    base_model: str,
) -> Path:
    return _runtime_service._build_vllm_runtime_model_from_adapter(
        adapter_dir=adapter_dir,
        base_model=base_model,
    )


def _resolve_adapter_dir(*, models_dir: Path, adapter_id: str) -> Path:
    return _runtime_service._resolve_adapter_dir(
        models_dir=models_dir, adapter_id=adapter_id
    )


def _require_existing_adapter_artifact(*, adapter_dir: Path) -> Path:
    return _runtime_service._require_existing_adapter_artifact(adapter_dir=adapter_dir)


def _deploy_adapter_to_vllm_runtime(*, adapter_id: str) -> Dict[str, Any]:
    return _runtime_service._deploy_adapter_to_vllm_runtime(
        adapter_id=adapter_id,
        settings_obj=_resolve_settings_for_call(),
        config_manager_obj=config_manager,
        compute_llm_config_hash_fn=compute_llm_config_hash,
        runtime_endpoint_for_hash_fn=_runtime_endpoint_for_hash,
        build_vllm_runtime_model_from_adapter_fn=_build_vllm_runtime_model_from_adapter,
        is_runtime_model_dir_fn=_is_runtime_model_dir,
        restart_vllm_runtime_fn=_restart_vllm_runtime,
    )


def _rollback_chat_runtime_after_adapter_deactivation(*, mgr: Any) -> Dict[str, Any]:
    return _runtime_service._rollback_chat_runtime_after_adapter_deactivation(
        mgr=mgr,
        settings_obj=_resolve_settings_for_call(),
        get_active_llm_runtime_fn=get_active_llm_runtime,
        config_manager_obj=config_manager,
        compute_llm_config_hash_fn=compute_llm_config_hash,
        runtime_endpoint_for_hash_fn=_runtime_endpoint_for_hash,
        resolve_local_runtime_model_path_by_name_fn=_resolve_local_runtime_model_path_by_name,
        restart_vllm_runtime_fn=_restart_vllm_runtime,
    )


def audit_adapters(
    *,
    mgr: Any,
    runtime_id: str | None = None,
    model_id: str | None = None,
) -> Dict[str, Any]:
    return _audit_service.audit_adapters(
        mgr=mgr,
        runtime_id=runtime_id,
        model_id=model_id,
        settings_obj=_resolve_settings_for_call(),
    )


async def validate_adapter_runtime_compatibility(
    *,
    mgr: Any,
    adapter_id: str,
    runtime_id: str,
    model_id: str | None = None,
) -> None:
    return await _audit_service.validate_adapter_runtime_compatibility(
        mgr=mgr,
        adapter_id=adapter_id,
        runtime_id=runtime_id,
        model_id=model_id,
        settings_obj=_resolve_settings_for_call(),
        list_trainable_models_fn=list_trainable_models,
    )


async def list_adapters(mgr: Any) -> List[AdapterInfo]:
    """List available local adapters and mark active one."""
    settings = _resolve_settings_for_call()
    adapters: List[AdapterInfo] = []
    models_dir = Path(settings.ACADEMY_MODELS_DIR)

    if not models_dir.exists():
        return []

    active_adapter_id = None
    if mgr:
        active_info = mgr.get_active_adapter_info()
        if active_info:
            active_adapter_id = active_info.get("adapter_id")

    for training_dir in models_dir.iterdir():
        if not training_dir.is_dir():
            continue

        adapter_path = training_dir / "adapter"
        if not adapter_path.exists():
            continue

        metadata_file = training_dir / "metadata.json"
        metadata: Dict[str, Any] = {}
        if metadata_file.exists():
            metadata_raw = await anyio.Path(metadata_file).read_text(encoding="utf-8")
            metadata = json.loads(metadata_raw)

        adapters.append(
            AdapterInfo(
                adapter_id=training_dir.name,
                adapter_path=str(adapter_path),
                base_model=metadata.get(
                    "base_model", settings.ACADEMY_DEFAULT_BASE_MODEL
                ),
                created_at=metadata.get("created_at", "unknown"),
                training_params=metadata.get("parameters", {}),
                is_active=(training_dir.name == active_adapter_id),
            )
        )

    return adapters


def activate_adapter(
    mgr: Any,
    adapter_id: str,
    *,
    runtime_id: str | None = None,
    model_id: str | None = None,
    deploy_to_chat_runtime: bool = False,
) -> Dict[str, Any]:
    """Activate adapter in model manager, returning API payload."""
    settings = _resolve_settings_for_call()
    models_dir = Path(settings.ACADEMY_MODELS_DIR).resolve()
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    adapter_path = (adapter_dir / "adapter").resolve()

    if not adapter_path.exists():
        raise FileNotFoundError(ADAPTER_NOT_FOUND_DETAIL)

    success = mgr.activate_adapter(
        adapter_id=adapter_id, adapter_path=str(adapter_path)
    )
    if not success:
        raise RuntimeError(f"Failed to activate adapter {adapter_id}")

    payload: Dict[str, Any] = {
        "success": True,
        "message": f"Adapter {adapter_id} activated successfully",
        "adapter_id": adapter_id,
        "adapter_path": str(adapter_path),
    }

    if deploy_to_chat_runtime:
        deploy_payload = _runtime_service._deploy_adapter_to_chat_runtime(
            mgr=mgr,
            adapter_id=adapter_id,
            runtime_id=runtime_id,
            model_id=model_id,
            canonical_runtime_model_id_fn=_canonical_runtime_model_id,
            require_trusted_adapter_base_model_fn=_require_trusted_adapter_base_model,
            settings_obj=settings,
            config_manager_obj=config_manager,
            compute_llm_config_hash_fn=compute_llm_config_hash,
            resolve_runtime_for_adapter_deploy_fn=_resolve_runtime_for_adapter_deploy,
            runtime_endpoint_for_hash_fn=_runtime_endpoint_for_hash,
            build_vllm_runtime_model_from_adapter_fn=_build_vllm_runtime_model_from_adapter,
            is_runtime_model_dir_fn=_is_runtime_model_dir,
            restart_vllm_runtime_fn=_restart_vllm_runtime,
            get_active_llm_runtime_fn=get_active_llm_runtime,
            deploy_adapter_to_vllm_runtime_fn=_deploy_adapter_to_vllm_runtime,
        )
        payload.update(deploy_payload)
        if deploy_payload.get("deployed"):
            payload["message"] = (
                f"Adapter {adapter_id} activated and deployed to chat runtime "
                f"({deploy_payload.get('runtime_id')}:{deploy_payload.get('chat_model')})"
            )
        else:
            payload["message"] = (
                f"Adapter {adapter_id} activated, chat runtime deploy skipped "
                f"({deploy_payload.get('reason', 'unknown')})"
            )

    logger.info("Activated adapter: %s", adapter_id)
    return payload


def deactivate_adapter(
    mgr: Any,
    *,
    deploy_to_chat_runtime: bool = False,
) -> Dict[str, Any]:
    """Deactivate active adapter in model manager."""
    success = mgr.deactivate_adapter()
    if not success:
        return {
            "success": False,
            "message": "No active adapter to deactivate",
        }

    payload: Dict[str, Any] = {
        "success": True,
        "message": "Adapter deactivated successfully - using base model",
    }
    if deploy_to_chat_runtime:
        rollback_payload = _rollback_chat_runtime_after_adapter_deactivation(mgr=mgr)
        payload.update(rollback_payload)
        if rollback_payload.get("rolled_back"):
            payload["message"] = (
                "Adapter deactivated and chat runtime rolled back "
                f"to {rollback_payload.get('chat_model')}"
            )
        else:
            payload["message"] = (
                "Adapter deactivated, chat runtime rollback skipped "
                f"({rollback_payload.get('reason', 'unknown')})"
            )

    logger.info("Adapter deactivated - rolled back to base model")
    return payload
