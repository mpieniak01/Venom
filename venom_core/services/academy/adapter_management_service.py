"""Adapter listing and activation management service for Academy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from venom_core.api.schemas.academy import AdapterInfo
from venom_core.services.academy import adapter_metadata_service as _metadata_service
from venom_core.services.academy import adapter_runtime_service as _runtime_service
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                records.append(payload)
    except Exception as exc:
        logger.warning("Failed to read JSONL records from %s: %s", path, exc)
    return records


def _load_self_learning_run_snapshot(
    *,
    repo_root: Path,
    adapter_id: str,
) -> dict[str, Any]:
    prefix = "self_learning_"
    if not adapter_id.startswith(prefix):
        return {}
    run_id = adapter_id[len(prefix) :].strip()
    if not run_id:
        return {}
    runs_file = repo_root / "data" / "academy" / "self_learning" / "runs.jsonl"
    matches = [
        record
        for record in _load_jsonl_records(runs_file)
        if str(record.get("run_id") or "").strip() == run_id
    ]
    return matches[-1] if matches else {}


def _resolve_adapter_display_info(
    *,
    repo_root: Path,
    training_dir: Path,
    default_model: str,
) -> dict[str, Any]:
    metadata = _metadata_service._load_adapter_metadata(training_dir)
    base_model_assessment = _metadata_service._assess_adapter_base_model(
        adapter_dir=training_dir,
        default_model=default_model,
    )
    run_snapshot = _load_self_learning_run_snapshot(
        repo_root=repo_root,
        adapter_id=training_dir.name,
    )
    llm_config = run_snapshot.get("llm_config")
    run_training_params = llm_config if isinstance(llm_config, dict) else {}
    metadata_params = metadata.get("parameters")
    training_params = (
        metadata_params
        if isinstance(metadata_params, dict) and metadata_params
        else run_training_params
    )
    created_at = (
        str(metadata.get("created_at") or "").strip()
        or str(run_snapshot.get("created_at") or "").strip()
    )
    if not created_at:
        created_at = "unknown"
    base_model = str(base_model_assessment.get("base_model") or "").strip()
    return {
        "base_model": base_model or default_model,
        "created_at": created_at,
        "training_params": training_params if isinstance(training_params, dict) else {},
    }


async def list_adapters(
    *,
    mgr: Any,
    settings_obj: Any,
    repo_root: Path,
) -> list[AdapterInfo]:
    """List available adapters with display metadata resolved from stable sources."""
    adapters: list[AdapterInfo] = []
    models_dir = Path(settings_obj.ACADEMY_MODELS_DIR)
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
        display_info = _resolve_adapter_display_info(
            repo_root=repo_root,
            training_dir=training_dir,
            default_model=settings_obj.ACADEMY_DEFAULT_BASE_MODEL,
        )
        adapters.append(
            AdapterInfo(
                adapter_id=training_dir.name,
                adapter_path=str(adapter_path),
                base_model=str(display_info.get("base_model") or ""),
                created_at=str(display_info.get("created_at") or "unknown"),
                training_params=dict(display_info.get("training_params") or {}),
                is_active=(training_dir.name == active_adapter_id),
            )
        )

    return adapters


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
