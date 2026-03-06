"""Adapter metadata resolution and validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set

from venom_core.utils.logger import get_logger

from .trainable_catalog_service import _canonical_runtime_model_id

logger = get_logger(__name__)

ADAPTER_BASE_MODEL_MISMATCH = "ADAPTER_BASE_MODEL_MISMATCH"
ADAPTER_BASE_MODEL_UNKNOWN = "ADAPTER_BASE_MODEL_UNKNOWN"
ADAPTER_METADATA_INCONSISTENT = "ADAPTER_METADATA_INCONSISTENT"
ADAPTER_NOT_FOUND_DETAIL = "Adapter not found"

_BASE_MODEL_CONFIDENT_SOURCES: Set[str] = {
    "metadata.base_model",
    "adapter.adapter_config.base_model_name_or_path",
    "adapter.adapter_config.base_model_name",
    "runtime_vllm.venom_runtime_vllm.base_model",
}


def _load_adapter_metadata(adapter_dir: Path) -> Dict[str, Any]:
    metadata_file = adapter_dir / "metadata.json"
    if not metadata_file.exists():
        return {}
    try:
        return json.loads(metadata_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read adapter metadata for %s: %s", adapter_dir, exc)
        return {}


def _read_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception as exc:
        logger.warning("Failed to parse JSON for %s: %s", path, exc)
    return {}


def _collect_adapter_base_model_candidates(
    *,
    adapter_dir: Path,
    default_model: str,
) -> List[Dict[str, str]]:
    metadata = _load_adapter_metadata(adapter_dir)
    candidates: List[Dict[str, str]] = []

    metadata_model = str(metadata.get("base_model") or "").strip()
    if metadata_model:
        candidates.append(
            {
                "source": "metadata.base_model",
                "model": metadata_model,
            }
        )

    adapter_config = _read_json_file(adapter_dir / "adapter" / "adapter_config.json")
    adapter_model_name_or_path = str(
        adapter_config.get("base_model_name_or_path") or ""
    ).strip()
    if adapter_model_name_or_path:
        candidates.append(
            {
                "source": "adapter.adapter_config.base_model_name_or_path",
                "model": adapter_model_name_or_path,
            }
        )
    adapter_model_name = str(adapter_config.get("base_model_name") or "").strip()
    if adapter_model_name:
        candidates.append(
            {
                "source": "adapter.adapter_config.base_model_name",
                "model": adapter_model_name,
            }
        )

    runtime_manifest = _read_json_file(
        adapter_dir / "runtime_vllm" / "venom_runtime_vllm.json"
    )
    runtime_model = str(runtime_manifest.get("base_model") or "").strip()
    if runtime_model:
        candidates.append(
            {
                "source": "runtime_vllm.venom_runtime_vllm.base_model",
                "model": runtime_model,
            }
        )

    fallback_model = default_model.strip()
    if fallback_model:
        candidates.append(
            {
                "source": "settings.ACADEMY_DEFAULT_BASE_MODEL",
                "model": fallback_model,
            }
        )
    return candidates


def _assess_adapter_base_model(
    *,
    adapter_dir: Path,
    default_model: str,
) -> Dict[str, Any]:
    candidates = _collect_adapter_base_model_candidates(
        adapter_dir=adapter_dir,
        default_model=default_model,
    )

    trusted_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("source") in _BASE_MODEL_CONFIDENT_SOURCES
        and str(candidate.get("model") or "").strip()
    ]

    if not trusted_candidates:
        fallback_model = str(default_model or "").strip()
        return {
            "base_model": fallback_model,
            "canonical_base_model": _canonical_runtime_model_id(fallback_model),
            "trusted": False,
            "reason_code": ADAPTER_BASE_MODEL_UNKNOWN,
            "reason": "Missing reliable adapter base model metadata",
            "sources": candidates,
        }

    canonical_models = {
        _canonical_runtime_model_id(str(candidate["model"]))
        for candidate in trusted_candidates
        if _canonical_runtime_model_id(str(candidate["model"]))
    }
    if len(canonical_models) > 1:
        preferred = str(trusted_candidates[0]["model"])
        return {
            "base_model": preferred,
            "canonical_base_model": _canonical_runtime_model_id(preferred),
            "trusted": False,
            "reason_code": ADAPTER_METADATA_INCONSISTENT,
            "reason": "Conflicting base model values across adapter metadata artifacts",
            "sources": candidates,
        }

    preferred_model = str(trusted_candidates[0]["model"]) if trusted_candidates else ""
    return {
        "base_model": preferred_model,
        "canonical_base_model": _canonical_runtime_model_id(preferred_model),
        "trusted": True,
        "reason_code": None,
        "reason": None,
        "sources": candidates,
    }


def _require_trusted_adapter_base_model(
    *,
    adapter_dir: Path,
    default_model: str,
) -> str:
    assessment = _assess_adapter_base_model(
        adapter_dir=adapter_dir,
        default_model=default_model,
    )
    base_model = str(assessment.get("base_model") or "").strip()
    trusted = bool(assessment.get("trusted"))
    if trusted and base_model:
        return base_model
    reason_code = str(assessment.get("reason_code") or ADAPTER_BASE_MODEL_UNKNOWN)
    reason = str(
        assessment.get("reason")
        or "Adapter base model is not reliable enough for deployment validation"
    )
    raise ValueError(f"{reason_code}: {reason}")


def _resolve_adapter_base_model(*, adapter_dir: Path, default_model: str) -> str:
    metadata = _load_adapter_metadata(adapter_dir)
    base_model = str(metadata.get("base_model") or "").strip()
    if base_model:
        return base_model
    return default_model


def _infer_local_runtime_provider(model: Dict[str, Any]) -> str:
    provider = str(model.get("provider") or "").strip().lower()
    if provider in {"ollama", "vllm", "onnx"}:
        return provider
    source = str(model.get("source") or "").strip().lower()
    if source in {"ollama", "vllm", "onnx"}:
        return source
    model_name = str(model.get("name") or "").strip().lower()
    model_path = str(model.get("path") or "").strip().lower()
    if "onnx" in model_name or "onnx" in model_path or model_path.endswith(".onnx"):
        return "onnx"
    if ":" in model_name:
        return "ollama"
    return "vllm"


async def _assert_runtime_model_available(
    *,
    mgr: Any,
    runtime_id: str,
    model_id: str,
) -> None:
    candidate = model_id.strip()
    if not candidate:
        return
    try:
        local_models = await mgr.list_local_models()
    except Exception as exc:  # pragma: no cover - defensive path
        logger.warning(
            "Failed to read local model catalog during adapter compatibility validation: %s",
            exc,
        )
        return

    runtime_models = {
        str(model.get("name") or "").strip()
        for model in local_models
        if str(model.get("name") or "").strip()
        and _infer_local_runtime_provider(model) == runtime_id
    }
    if candidate in runtime_models:
        return

    requested_canonical = _canonical_runtime_model_id(candidate)
    if requested_canonical and any(
        _canonical_runtime_model_id(name) == requested_canonical
        for name in runtime_models
    ):
        return

    available_hint = ", ".join(sorted(runtime_models)[:8]) or "none"
    raise ValueError(
        "Selected model is not available on runtime "
        f"'{runtime_id}': '{candidate}'. Available: {available_hint}."
    )
