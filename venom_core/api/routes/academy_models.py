"""Thin API facade for Academy model and adapter operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from venom_core.api.schemas.academy import AdapterInfo
from venom_core.config import SETTINGS
from venom_core.services.academy import adapter_audit_service as _audit_service
from venom_core.services.academy import (
    adapter_management_service as _management_service,
)
from venom_core.services.academy import adapter_metadata_service as _metadata_service
from venom_core.services.academy import adapter_runtime_service as _runtime_service
from venom_core.services.academy import trainable_catalog_service as _catalog_service
from venom_core.services.academy.adapter_metadata_service import (
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
assess_runtime_base_model_compatibility = (
    _catalog_service.assess_runtime_base_model_compatibility
)
build_model_label = _catalog_service.build_model_label
classify_model_cost_tier = _catalog_service.classify_model_cost_tier
classify_model_source_type = _catalog_service.classify_model_source_type
collect_default_trainable_models = _catalog_service.collect_default_trainable_models
collect_local_trainable_models = _catalog_service.collect_local_trainable_models
discover_available_runtime_targets = _catalog_service.discover_available_runtime_targets
discover_runtime_model_families = _catalog_service.discover_runtime_model_families
get_default_trainable_models_catalog = (
    _catalog_service.get_default_trainable_models_catalog
)
get_model_non_trainable_reason = _catalog_service.get_model_non_trainable_reason
is_model_trainable = _catalog_service.is_model_trainable
resolve_model_priority_bucket = _catalog_service.resolve_model_priority_bucket
resolve_recommended_runtime = _catalog_service.resolve_recommended_runtime
resolve_effective_training_base_model = (
    _catalog_service.resolve_effective_training_base_model
)
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
) -> str:
    return _runtime_service._resolve_runtime_for_adapter_deploy(runtime_id)


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
    return _management_service.list_adapters(
        mgr=mgr,
        settings_obj=_resolve_settings_for_call(),
    )


def purge_legacy_adapters(
    *,
    mgr: Any,
    apply: bool = False,
    include_active: bool = False,
) -> Dict[str, Any]:
    """Purge legacy adapters without canonical metadata."""
    return _management_service.purge_legacy_adapters(
        mgr=mgr,
        settings_obj=_resolve_settings_for_call(),
        apply=apply,
        include_active=include_active,
    )


def activate_adapter(
    mgr: Any,
    adapter_id: str,
    *,
    runtime_id: str | None = None,
    model_id: str | None = None,
    deploy_to_chat_runtime: bool = False,
) -> Dict[str, Any]:
    """Activate adapter in model manager, returning API payload."""
    settings_obj = _resolve_settings_for_call()
    runtime_deploy_deps = _management_service.RuntimeDeployDependencies(
        canonical_runtime_model_id_fn=_canonical_runtime_model_id,
        require_trusted_adapter_base_model_fn=_require_trusted_adapter_base_model,
        settings_obj=settings_obj,
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
    return _management_service.activate_adapter(
        mgr=mgr,
        adapter_id=adapter_id,
        runtime_id=runtime_id,
        model_id=model_id,
        deploy_to_chat_runtime=deploy_to_chat_runtime,
        settings_obj=settings_obj,
        runtime_deploy_deps=runtime_deploy_deps,
    )


def deactivate_adapter(
    mgr: Any,
    *,
    deploy_to_chat_runtime: bool = False,
) -> Dict[str, Any]:
    """Deactivate active adapter in model manager."""
    return _management_service.deactivate_adapter(
        mgr=mgr,
        deploy_to_chat_runtime=deploy_to_chat_runtime,
        rollback_chat_runtime_after_adapter_deactivation_fn=_rollback_chat_runtime_after_adapter_deactivation,
    )
