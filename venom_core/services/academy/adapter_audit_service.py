"""Adapter compatibility validation and audit service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .adapter_metadata_service import (
    ADAPTER_BASE_MODEL_MISMATCH,
    ADAPTER_BASE_MODEL_UNKNOWN,
    ADAPTER_METADATA_INCOMPLETE,
    ADAPTER_METADATA_INCONSISTENT,
    _assert_runtime_model_available,
    _assess_adapter_base_model,
    _require_trusted_adapter_base_model,
)
from .adapter_runtime_service import (
    _require_existing_adapter_artifact,
    _resolve_adapter_dir,
)
from .trainable_catalog_service import (
    _canonical_runtime_model_id,
    _resolve_local_runtime_id,
    list_trainable_models,
)

ADAPTER_RUNTIME_INCOMPATIBLE = "ADAPTER_RUNTIME_INCOMPATIBLE"
_RUNTIME_ADAPTER_MODEL_PREFIX = "venom-adapter-"
_RUNTIME_ADAPTER_OWNS_MODEL_CONTRACT = {"onnx"}


def _get_settings() -> Any:
    from venom_core.config import SETTINGS

    return SETTINGS


def _empty_adapters_audit_payload() -> Dict[str, Any]:
    return {
        "count": 0,
        "adapters": [],
        "summary": {
            "compatible": 0,
            "blocked_unknown_base": 0,
            "blocked_mismatch": 0,
        },
    }


def _resolve_active_adapter_id(mgr: Any) -> str:
    if not mgr:
        return ""
    active_info = mgr.get_active_adapter_info()
    if not isinstance(active_info, dict):
        return ""
    return str(active_info.get("adapter_id") or "").strip()


def _evaluate_adapter_audit_status(
    *,
    assessment: Dict[str, Any],
    base_model: str,
    runtime_local_id: str | None,
    selected_model: str,
    selected_model_canonical: str,
) -> tuple[str, str | None, str]:
    reason_code = str(assessment.get("reason_code") or "").strip() or None
    category = "compatible"
    message = "Adapter metadata is consistent"

    if not bool(assessment.get("trusted")):
        if reason_code == ADAPTER_METADATA_INCONSISTENT:
            return (
                "blocked_mismatch",
                reason_code,
                str(assessment.get("reason") or "Inconsistent adapter metadata"),
            )
        return (
            "blocked_unknown_base",
            reason_code or ADAPTER_METADATA_INCOMPLETE or ADAPTER_BASE_MODEL_UNKNOWN,
            str(assessment.get("reason") or "Reliable base_model metadata is missing"),
        )

    if runtime_local_id and selected_model_canonical:
        # Runtime adapter exports are specialized runtime models; for audit purposes
        # they are treated as compatible with adapter selection flow.
        if selected_model.lower().startswith(_RUNTIME_ADAPTER_MODEL_PREFIX):
            return category, reason_code, message
        base_canonical = _canonical_runtime_model_id(base_model)
        if base_canonical and base_canonical != selected_model_canonical:
            return (
                "blocked_mismatch",
                ADAPTER_BASE_MODEL_MISMATCH,
                "Adapter base model does not match selected runtime model "
                f"('{selected_model}')",
            )
    return category, reason_code, message


def _build_adapter_audit_item(
    *,
    training_dir: Path,
    adapter_path: Path,
    assessment: Dict[str, Any],
    base_model: str,
    category: str,
    reason_code: str | None,
    message: str,
    active_adapter_id: str,
) -> Dict[str, Any]:
    return {
        "adapter_id": training_dir.name,
        "adapter_path": str(adapter_path),
        "base_model": base_model,
        "canonical_base_model": str(assessment.get("canonical_base_model") or ""),
        "trusted_metadata": bool(assessment.get("trusted")),
        "category": category,
        "reason_code": reason_code,
        "message": message,
        "is_active": training_dir.name == active_adapter_id,
        "sources": list(assessment.get("sources") or []),
        "manual_repair_hint": (
            "Fill adapter metadata with a single consistent base_model and rerun audit"
            if category != "compatible"
            else None
        ),
    }


async def validate_adapter_runtime_compatibility(
    *,
    mgr: Any,
    adapter_id: str,
    runtime_id: str,
    model_id: str | None = None,
    settings_obj: Any | None = None,
    list_trainable_models_fn: Any = list_trainable_models,
) -> None:
    """Validate that adapter base model can run on selected inference runtime."""
    settings = settings_obj or _get_settings()
    runtime_local_id = _resolve_local_runtime_id(runtime_id.strip().lower())
    if not runtime_id.strip():
        return
    if runtime_local_id is None:
        raise ValueError(
            "Academy adapter supports only local runtimes (ollama/vllm/onnx); "
            f"got '{runtime_id}'."
        )

    from venom_core.services.academy import adapter_runtime_service as _runtime_service

    models_dir = _runtime_service._resolve_academy_models_dir(settings_obj=settings)
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    _require_existing_adapter_artifact(adapter_dir=adapter_dir)
    base_model = _require_trusted_adapter_base_model(
        adapter_dir=adapter_dir,
    ).strip()
    if not base_model:
        return

    trainable_models = await list_trainable_models_fn(mgr=mgr)
    trainable_by_model = {item.model_id.lower(): item for item in trainable_models}
    trainable_info = trainable_by_model.get(base_model.lower())
    if trainable_info is None:
        return

    runtime_compatibility = dict(trainable_info.runtime_compatibility or {})
    if not runtime_compatibility:
        return

    if runtime_compatibility.get(runtime_local_id):
        await _assert_selected_runtime_model_compatible_with_adapter_base(
            mgr=mgr,
            runtime_local_id=runtime_local_id,
            model_id=model_id,
            adapter_id=adapter_id,
            base_model=base_model,
        )
        return

    compatible_runtimes = sorted(
        runtime
        for runtime, is_supported in runtime_compatibility.items()
        if is_supported
    )
    if compatible_runtimes:
        supported_hint = ", ".join(compatible_runtimes)
        raise ValueError(
            f"{ADAPTER_RUNTIME_INCOMPATIBLE}: Adapter is incompatible with selected runtime "
            f"'{runtime_local_id}'. Compatible runtimes: {supported_hint}."
        )
    raise ValueError(
        f"{ADAPTER_RUNTIME_INCOMPATIBLE}: Adapter does not expose compatible local runtimes for activation."
    )


async def _assert_selected_runtime_model_compatible_with_adapter_base(
    *,
    mgr: Any,
    runtime_local_id: str,
    model_id: str | None,
    adapter_id: str,
    base_model: str,
) -> None:
    selected_model = str(model_id or "").strip()
    if not selected_model:
        return
    if runtime_local_id in _RUNTIME_ADAPTER_OWNS_MODEL_CONTRACT:
        # For ONNX deploy pipeline, adapter activation performs merge/export and
        # produces dedicated runtime model artifact. The transient selector model
        # should not block activation if runtime itself is compatible.
        return

    await _assert_runtime_model_available(
        mgr=mgr,
        runtime_id=runtime_local_id,
        model_id=selected_model,
    )

    adapter_runtime_model = f"venom-adapter-{adapter_id}".lower()
    selected_canonical = _canonical_runtime_model_id(selected_model)
    base_canonical = _canonical_runtime_model_id(base_model)
    if selected_model.lower() == adapter_runtime_model:
        return
    if selected_model.lower().startswith(_RUNTIME_ADAPTER_MODEL_PREFIX):
        return
    if selected_canonical == base_canonical:
        return

    raise ValueError(
        f"{ADAPTER_BASE_MODEL_MISMATCH}: Adapter base model does not match selected runtime model. "
        f"Selected model: '{selected_model}', adapter base model: '{base_model}'."
    )


def audit_adapters(
    *,
    mgr: Any,
    runtime_id: str | None = None,
    model_id: str | None = None,
    settings_obj: Any | None = None,
) -> Dict[str, Any]:
    """Preflight audit for historical adapters metadata confidence and compatibility."""
    settings = settings_obj or _get_settings()
    models_dir = Path(settings.ACADEMY_MODELS_DIR)
    if not models_dir.exists():
        return _empty_adapters_audit_payload()

    runtime_local_id = _resolve_local_runtime_id(str(runtime_id or "").strip().lower())
    selected_model = str(model_id or "").strip()
    selected_model_canonical = _canonical_runtime_model_id(selected_model)

    active_adapter_id = _resolve_active_adapter_id(mgr)

    items: List[Dict[str, Any]] = []
    for training_dir in sorted(models_dir.iterdir(), key=lambda p: p.name):
        if not training_dir.is_dir():
            continue
        adapter_path = training_dir / "adapter"
        if not adapter_path.exists():
            continue

        assessment = _assess_adapter_base_model(adapter_dir=training_dir)
        base_model = str(assessment.get("base_model") or "").strip()
        category, reason_code, message = _evaluate_adapter_audit_status(
            assessment=assessment,
            base_model=base_model,
            runtime_local_id=runtime_local_id,
            selected_model=selected_model,
            selected_model_canonical=selected_model_canonical,
        )

        items.append(
            _build_adapter_audit_item(
                training_dir=training_dir,
                adapter_path=adapter_path,
                assessment=assessment,
                base_model=base_model,
                category=category,
                reason_code=reason_code,
                message=message,
                active_adapter_id=active_adapter_id,
            )
        )

    summary = {
        "compatible": sum(1 for item in items if item.get("category") == "compatible"),
        "blocked_unknown_base": sum(
            1 for item in items if item.get("category") == "blocked_unknown_base"
        ),
        "blocked_mismatch": sum(
            1 for item in items if item.get("category") == "blocked_mismatch"
        ),
    }

    return {
        "count": len(items),
        "adapters": items,
        "summary": summary,
        "runtime_id": runtime_local_id,
        "model_id": selected_model or None,
    }
