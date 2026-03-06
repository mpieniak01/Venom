"""Thin API facade for Academy model and adapter operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import anyio

from venom_core.api.schemas.academy import AdapterInfo
from venom_core.services.academy import adapter_audit_service as _audit_service
from venom_core.services.academy import adapter_runtime_service as _runtime_service
from venom_core.services.academy.adapter_metadata_service import (
    ADAPTER_NOT_FOUND_DETAIL,
    _require_trusted_adapter_base_model,
)
from venom_core.services.academy.trainable_catalog_service import (
    _canonical_runtime_model_id,
    _resolve_local_runtime_id,
    list_trainable_models,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Patch points retained for compatibility with existing tests.
config_manager = _runtime_service.config_manager
compute_llm_config_hash = _runtime_service.compute_llm_config_hash
get_active_llm_runtime = _runtime_service.get_active_llm_runtime


def _get_settings() -> Any:
    from venom_core.config import SETTINGS

    return SETTINGS


SETTINGS = _get_settings()
_INITIAL_SETTINGS = SETTINGS


def _resolve_settings_for_call() -> Any:
    from venom_core.config import SETTINGS as config_settings

    current = globals().get("SETTINGS", config_settings)
    if current is not _INITIAL_SETTINGS:
        return current
    return config_settings


def _resolve_repo_root() -> Path:
    original_get_settings = _runtime_service._get_settings
    _runtime_service._get_settings = _resolve_settings_for_call
    try:
        return _runtime_service._resolve_repo_root()
    finally:
        _runtime_service._get_settings = original_get_settings


def _resolve_local_runtime_model_path_by_name(*, mgr: Any, model_name: str) -> str:
    original_get_settings = _runtime_service._get_settings
    _runtime_service._get_settings = _resolve_settings_for_call
    try:
        return _runtime_service._resolve_local_runtime_model_path_by_name(
            mgr=mgr,
            model_name=model_name,
        )
    finally:
        _runtime_service._get_settings = original_get_settings


def _restart_vllm_runtime() -> None:
    original_resolve_repo_root = _runtime_service._resolve_repo_root
    original_get_settings = _runtime_service._get_settings
    _runtime_service._resolve_repo_root = _resolve_repo_root
    _runtime_service._get_settings = _resolve_settings_for_call
    try:
        return _runtime_service._restart_vllm_runtime()
    finally:
        _runtime_service._resolve_repo_root = original_resolve_repo_root
        _runtime_service._get_settings = original_get_settings


def _runtime_endpoint_for_hash(runtime_id: str) -> str | None:
    original_get_settings = _runtime_service._get_settings
    _runtime_service._get_settings = _resolve_settings_for_call
    try:
        return _runtime_service._runtime_endpoint_for_hash(runtime_id)
    finally:
        _runtime_service._get_settings = original_get_settings


def _resolve_runtime_for_adapter_deploy(runtime_id: str | None) -> str:
    original_get_settings = _runtime_service._get_settings
    _runtime_service._get_settings = _resolve_settings_for_call
    _runtime_service.get_active_llm_runtime = get_active_llm_runtime
    try:
        return _runtime_service._resolve_runtime_for_adapter_deploy(runtime_id)
    finally:
        _runtime_service._get_settings = original_get_settings


def _is_runtime_model_dir(path: Path) -> bool:
    return _runtime_service._is_runtime_model_dir(path)


def _build_vllm_runtime_model_from_adapter(
    *, adapter_dir: Path, base_model: str
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
    original_build = _runtime_service._build_vllm_runtime_model_from_adapter
    original_restart = _runtime_service._restart_vllm_runtime
    original_hash = _runtime_service.compute_llm_config_hash
    original_config_manager = _runtime_service.config_manager
    original_get_settings = _runtime_service._get_settings
    _runtime_service._build_vllm_runtime_model_from_adapter = (
        _build_vllm_runtime_model_from_adapter
    )
    _runtime_service._restart_vllm_runtime = _restart_vllm_runtime
    _runtime_service.compute_llm_config_hash = compute_llm_config_hash
    _runtime_service.config_manager = config_manager
    _runtime_service._get_settings = _resolve_settings_for_call
    try:
        return _runtime_service._deploy_adapter_to_vllm_runtime(adapter_id=adapter_id)
    finally:
        _runtime_service._build_vllm_runtime_model_from_adapter = original_build
        _runtime_service._restart_vllm_runtime = original_restart
        _runtime_service.compute_llm_config_hash = original_hash
        _runtime_service.config_manager = original_config_manager
        _runtime_service._get_settings = original_get_settings


def _rollback_chat_runtime_after_adapter_deactivation(*, mgr: Any) -> Dict[str, Any]:
    original_active_runtime = _runtime_service.get_active_llm_runtime
    original_hash = _runtime_service.compute_llm_config_hash
    original_config_manager = _runtime_service.config_manager
    original_resolve_local = _runtime_service._resolve_local_runtime_model_path_by_name
    original_restart = _runtime_service._restart_vllm_runtime
    original_get_settings = _runtime_service._get_settings
    _runtime_service.get_active_llm_runtime = get_active_llm_runtime
    _runtime_service.compute_llm_config_hash = compute_llm_config_hash
    _runtime_service.config_manager = config_manager
    _runtime_service._resolve_local_runtime_model_path_by_name = (
        _resolve_local_runtime_model_path_by_name
    )
    _runtime_service._restart_vllm_runtime = _restart_vllm_runtime
    _runtime_service._get_settings = _resolve_settings_for_call
    try:
        return _runtime_service._rollback_chat_runtime_after_adapter_deactivation(
            mgr=mgr
        )
    finally:
        _runtime_service.get_active_llm_runtime = original_active_runtime
        _runtime_service.compute_llm_config_hash = original_hash
        _runtime_service.config_manager = original_config_manager
        _runtime_service._resolve_local_runtime_model_path_by_name = (
            original_resolve_local
        )
        _runtime_service._restart_vllm_runtime = original_restart
        _runtime_service._get_settings = original_get_settings


def audit_adapters(
    *,
    mgr: Any,
    runtime_id: str | None = None,
    model_id: str | None = None,
) -> Dict[str, Any]:
    original_get_settings = _audit_service._get_settings
    _audit_service._get_settings = _resolve_settings_for_call
    try:
        return _audit_service.audit_adapters(
            mgr=mgr, runtime_id=runtime_id, model_id=model_id
        )
    finally:
        _audit_service._get_settings = original_get_settings


async def validate_adapter_runtime_compatibility(
    *,
    mgr: Any,
    adapter_id: str,
    runtime_id: str,
    model_id: str | None = None,
) -> None:
    original_get_settings = _audit_service._get_settings
    original_list_trainable_models = _audit_service.list_trainable_models
    _audit_service._get_settings = _resolve_settings_for_call
    _audit_service.list_trainable_models = list_trainable_models
    try:
        return await _audit_service.validate_adapter_runtime_compatibility(
            mgr=mgr,
            adapter_id=adapter_id,
            runtime_id=runtime_id,
            model_id=model_id,
        )
    finally:
        _audit_service._get_settings = original_get_settings
        _audit_service.list_trainable_models = original_list_trainable_models


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
                    "base_model",
                    settings.ACADEMY_DEFAULT_BASE_MODEL,
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
        runtime_candidate = _resolve_runtime_for_adapter_deploy(runtime_id)
        runtime_local_id = _resolve_local_runtime_id(runtime_candidate)
        if runtime_local_id is None:
            deploy_payload = {
                "deployed": False,
                "reason": f"runtime_not_local:{runtime_candidate}",
                "runtime_id": runtime_candidate,
            }
        elif runtime_local_id == "onnx":
            deploy_payload = {
                "deployed": False,
                "reason": f"runtime_not_supported:{runtime_local_id}",
                "runtime_id": runtime_local_id,
            }
        elif runtime_local_id == "vllm":
            deploy_payload = _deploy_adapter_to_vllm_runtime(adapter_id=adapter_id)
        else:
            original_config_manager = _runtime_service.config_manager
            original_get_settings = _runtime_service._get_settings
            _runtime_service.config_manager = config_manager
            _runtime_service._get_settings = _resolve_settings_for_call
            try:
                deploy_payload = _runtime_service._deploy_adapter_to_chat_runtime(
                    mgr=mgr,
                    adapter_id=adapter_id,
                    runtime_id=runtime_id,
                    model_id=model_id,
                    canonical_runtime_model_id_fn=_canonical_runtime_model_id,
                    require_trusted_adapter_base_model_fn=_require_trusted_adapter_base_model,
                )
            finally:
                _runtime_service.config_manager = original_config_manager
                _runtime_service._get_settings = original_get_settings
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
