"""Adapter listing, activation and cleanup management service for Academy."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Literal

from venom_core.api.schemas.academy import AdapterInfo
from venom_core.services.academy import adapter_metadata_service as _metadata_service
from venom_core.services.academy import adapter_runtime_service as _runtime_service
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def _coerce_metadata_status(value: Any) -> Literal["canonical", "metadata_incomplete"]:
    normalized = str(value or "").strip().lower()
    if normalized == "canonical":
        return "canonical"
    return "metadata_incomplete"


def _resolve_adapter_display_info(
    *,
    training_dir: Path,
) -> dict[str, Any]:
    metadata = _metadata_service._load_adapter_metadata(training_dir)
    metadata_version = metadata.get("metadata_version")
    metadata_complete = (
        metadata_version == _metadata_service.CANONICAL_ADAPTER_METADATA_VERSION
        and str(
            metadata.get("effective_base_model") or metadata.get("base_model") or ""
        ).strip()
        and str(metadata.get("created_at") or "").strip()
        and str(metadata.get("source_flow") or "").strip()
    )
    if not metadata_complete:
        return {
            "base_model": "unknown",
            "created_at": "unknown",
            "training_params": {},
            "target_runtime": "",
            "source_flow": "",
            "metadata_status": "metadata_incomplete",
            "metadata_reason_code": _metadata_service.ADAPTER_METADATA_INCOMPLETE,
        }

    target_runtime = (
        str(metadata.get("effective_runtime_id") or "").strip()
        or str(metadata.get("requested_runtime_id") or "").strip()
    )
    return {
        "base_model": str(
            metadata.get("effective_base_model") or metadata.get("base_model") or ""
        ).strip(),
        "created_at": str(metadata.get("created_at") or "").strip() or "unknown",
        "training_params": (
            dict(metadata.get("parameters") or {})
            if isinstance(metadata.get("parameters"), dict)
            else {}
        ),
        "target_runtime": target_runtime,
        "source_flow": str(metadata.get("source_flow") or "").strip() or None,
        "metadata_status": "canonical",
        "metadata_reason_code": None,
    }


def _is_canonical_adapter_metadata_complete(training_dir: Path) -> bool:
    metadata = _metadata_service._load_adapter_metadata(training_dir)
    metadata_version = metadata.get("metadata_version")
    return bool(
        metadata_version == _metadata_service.CANONICAL_ADAPTER_METADATA_VERSION
        and str(
            metadata.get("effective_base_model") or metadata.get("base_model") or ""
        ).strip()
        and str(metadata.get("created_at") or "").strip()
        and str(metadata.get("source_flow") or "").strip()
    )


def purge_legacy_adapters(
    *,
    mgr: Any,
    settings_obj: Any,
    apply: bool = False,
    include_active: bool = False,
) -> dict[str, Any]:
    """Remove legacy adapter directories without canonical metadata."""
    models_dir = Path(settings_obj.ACADEMY_MODELS_DIR)
    if not models_dir.exists():
        return {
            "mode": "apply" if apply else "dry-run",
            "removed": [],
            "candidates": [],
            "skipped_active": [],
        }

    active_adapter_id = _resolve_active_adapter_id(mgr)
    removed: list[str] = []
    candidates: list[str] = []
    skipped_active: list[str] = []

    for training_dir in models_dir.iterdir():
        if not training_dir.is_dir():
            continue
        adapter_path = training_dir / "adapter"
        if not adapter_path.exists():
            continue
        if _is_canonical_adapter_metadata_complete(training_dir):
            continue
        adapter_id = training_dir.name
        if active_adapter_id and adapter_id == active_adapter_id and not include_active:
            skipped_active.append(adapter_id)
            continue
        candidates.append(adapter_id)
        if not apply:
            continue
        try:
            shutil.rmtree(training_dir)
            removed.append(adapter_id)
        except Exception as exc:
            logger.warning("Failed to remove legacy adapter '%s': %s", adapter_id, exc)

    return {
        "mode": "apply" if apply else "dry-run",
        "removed": sorted(removed),
        "candidates": sorted(candidates),
        "skipped_active": sorted(skipped_active),
    }


async def list_adapters(
    *,
    mgr: Any,
    settings_obj: Any,
) -> list[AdapterInfo]:
    """List available adapters with display metadata resolved from stable sources."""
    adapters: list[AdapterInfo] = []
    models_dir = Path(settings_obj.ACADEMY_MODELS_DIR)
    if not models_dir.exists():
        return []

    active_adapter_id = _resolve_active_adapter_id(mgr)

    for training_dir in models_dir.iterdir():
        if not training_dir.is_dir():
            continue
        adapter_path = training_dir / "adapter"
        if not adapter_path.exists():
            continue
        adapters.append(
            _build_adapter_info(
                training_dir=training_dir,
                adapter_path=adapter_path,
                active_adapter_id=active_adapter_id,
            )
        )

    return adapters


def _resolve_active_adapter_id(mgr: Any) -> str | None:
    if not mgr:
        return None
    active_info = mgr.get_active_adapter_info()
    if not active_info:
        return None
    return active_info.get("adapter_id")


def _build_adapter_info(
    *,
    training_dir: Path,
    adapter_path: Path,
    active_adapter_id: str | None,
) -> AdapterInfo:
    display_info = _resolve_adapter_display_info(training_dir=training_dir)
    return AdapterInfo(
        adapter_id=training_dir.name,
        adapter_path=str(adapter_path),
        base_model=str(display_info.get("base_model") or ""),
        created_at=str(display_info.get("created_at") or "unknown"),
        training_params=dict(display_info.get("training_params") or {}),
        target_runtime=str(display_info.get("target_runtime") or "") or None,
        source_flow=str(display_info.get("source_flow") or "") or None,
        metadata_status=_coerce_metadata_status(display_info.get("metadata_status")),
        metadata_reason_code=str(display_info.get("metadata_reason_code") or "")
        or None,
        is_active=(training_dir.name == active_adapter_id),
    )


def activate_adapter(
    *,
    mgr: Any,
    adapter_id: str,
    runtime_id: str | None,
    model_id: str | None,
    deploy_to_chat_runtime: bool,
    settings_obj: Any,
    config_manager_obj: Any,
    compute_llm_config_hash_fn: Any,
    canonical_runtime_model_id_fn: Any,
    require_trusted_adapter_base_model_fn: Any,
    resolve_runtime_for_adapter_deploy_fn: Any,
    runtime_endpoint_for_hash_fn: Any,
    build_vllm_runtime_model_from_adapter_fn: Any,
    is_runtime_model_dir_fn: Any,
    restart_vllm_runtime_fn: Any,
    get_active_llm_runtime_fn: Any,
    deploy_adapter_to_vllm_runtime_fn: Any,
) -> dict[str, Any]:
    """Activate adapter in model manager and optionally deploy it to chat runtime."""
    models_dir = Path(settings_obj.ACADEMY_MODELS_DIR).resolve()
    adapter_dir = _runtime_service._resolve_adapter_dir(
        models_dir=models_dir,
        adapter_id=adapter_id,
    )
    adapter_path = (adapter_dir / "adapter").resolve()
    if not adapter_path.exists():
        raise FileNotFoundError(_metadata_service.ADAPTER_NOT_FOUND_DETAIL)
    if deploy_to_chat_runtime:
        requested_runtime = str(runtime_id or "").strip()
        requested_model = str(model_id or "").strip()
        if not requested_runtime:
            raise ValueError(
                "ADAPTER_RUNTIME_REQUIRED: Select target runtime before adapter activation."
            )
        if not requested_model:
            raise ValueError(
                "ADAPTER_RUNTIME_MODEL_REQUIRED: Select runtime model before adapter activation."
            )

    success = mgr.activate_adapter(
        adapter_id=adapter_id, adapter_path=str(adapter_path)
    )
    if not success:
        raise RuntimeError(f"Failed to activate adapter {adapter_id}")

    payload: dict[str, Any] = {
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
            canonical_runtime_model_id_fn=canonical_runtime_model_id_fn,
            require_trusted_adapter_base_model_fn=require_trusted_adapter_base_model_fn,
            settings_obj=settings_obj,
            config_manager_obj=config_manager_obj,
            compute_llm_config_hash_fn=compute_llm_config_hash_fn,
            resolve_runtime_for_adapter_deploy_fn=resolve_runtime_for_adapter_deploy_fn,
            runtime_endpoint_for_hash_fn=runtime_endpoint_for_hash_fn,
            build_vllm_runtime_model_from_adapter_fn=build_vllm_runtime_model_from_adapter_fn,
            is_runtime_model_dir_fn=is_runtime_model_dir_fn,
            restart_vllm_runtime_fn=restart_vllm_runtime_fn,
            get_active_llm_runtime_fn=get_active_llm_runtime_fn,
            deploy_adapter_to_vllm_runtime_fn=deploy_adapter_to_vllm_runtime_fn,
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
    *,
    mgr: Any,
    deploy_to_chat_runtime: bool,
    rollback_chat_runtime_after_adapter_deactivation_fn: Any,
) -> dict[str, Any]:
    """Deactivate active adapter and optionally roll back chat runtime."""
    success = mgr.deactivate_adapter()
    if not success:
        return {
            "success": False,
            "message": "No active adapter to deactivate",
        }

    payload: dict[str, Any] = {
        "success": True,
        "message": "Adapter deactivated successfully - using base model",
    }
    if deploy_to_chat_runtime:
        rollback_payload = rollback_chat_runtime_after_adapter_deactivation_fn(mgr=mgr)
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
