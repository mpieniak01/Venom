"""Trainable-model catalog helpers for Academy routes."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set

import anyio

from venom_core.api.schemas.academy import AdapterInfo, TrainableModelInfo
from venom_core.config import SETTINGS
from venom_core.services.config_manager import config_manager
from venom_core.services.system_llm_service import previous_model_key_for_server
from venom_core.utils.llm_runtime import compute_llm_config_hash, get_active_llm_runtime
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)

FREE_CLOUD_PROVIDERS = {"unsloth", "huggingface", "hf"}
PAID_CLOUD_PROVIDERS = {
    "openai",
    "azure-openai",
    "anthropic",
    "google",
    "google-gemini",
}
PAID_MODEL_MARKERS = ("gpt-", "claude", "gemini")
LOCAL_RUNTIME_PREFERENCE = ("vllm", "ollama", "onnx")
_TRAINABLE_MODEL_ALIAS_TO_CANONICAL: Dict[str, str] = {
    "gemma3:latest": "gemma-3-4b-it",
    "gemma3:4b": "gemma-3-4b-it",
    "gemma3:1b": "gemma-3-1b-it",
    "qwen2.5-coder:3b": "qwen/qwen2.5-coder-3b-instruct",
    "qwen2.5-coder:7b": "qwen/qwen2.5-coder-7b-instruct",
}
ADAPTER_BASE_MODEL_MISMATCH = "ADAPTER_BASE_MODEL_MISMATCH"
ADAPTER_BASE_MODEL_UNKNOWN = "ADAPTER_BASE_MODEL_UNKNOWN"
ADAPTER_METADATA_INCONSISTENT = "ADAPTER_METADATA_INCONSISTENT"

_BASE_MODEL_CONFIDENT_SOURCES: Set[str] = {
    "metadata.base_model",
    "adapter.adapter_config.base_model_name_or_path",
    "adapter.adapter_config.base_model_name",
    "runtime_vllm.venom_runtime_vllm.base_model",
}
type ModelSourceType = Literal["local", "cloud"]
type ModelCostTier = Literal["free", "paid", "unknown"]


def is_model_trainable(
    model_id: str,
    provider: Optional[str] = None,
    model_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True when model can be used for Academy LoRA/QLoRA training."""
    return (
        get_model_non_trainable_reason(
            model_id=model_id,
            provider=provider,
            model_metadata=model_metadata,
        )
        is None
    )


def _looks_like_hf_repo_id(model_id: str) -> bool:
    candidate = model_id.strip()
    if not candidate or " " in candidate:
        return False
    # Repository id should be a plain "org/model" handle, not a URL.
    if "://" in candidate:
        return False
    parts = [part for part in candidate.split("/") if part]
    return len(parts) == 2


def _has_hf_weights(model_dir: Path) -> bool:
    weight_patterns = (
        "model.safetensors",
        "*.safetensors",
        "pytorch_model.bin",
        "pytorch_model-*.bin",
        "pytorch_model.bin.index.json",
    )
    for pattern in weight_patterns:
        if any(model_dir.glob(pattern)):
            return True
    return False


def _resolve_model_path_from_metadata(model_metadata: Dict[str, Any]) -> Optional[Path]:
    raw_path = model_metadata.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    if raw_path.startswith("ollama://"):
        return None
    path = Path(raw_path)
    if path.exists():
        return path
    return None


def _non_trainable_reason_from_local_artifacts(
    *,
    model_id: str,
    provider_lc: str,
    model_metadata: Dict[str, Any],
) -> Optional[str]:
    if model_id.strip().lower().startswith("venom-adapter-"):
        return (
            "Runtime adapter exports are inference-only artifacts; "
            "select a base HuggingFace/Unsloth model for Academy training"
        )

    model_type = str(model_metadata.get("type") or "").lower()
    runtime = str(model_metadata.get("runtime") or "").lower()
    source = str(model_metadata.get("source") or "").lower()

    if _is_onnx_artifact(
        provider_lc=provider_lc, runtime=runtime, model_type=model_type
    ):
        return "ONNX runtime artifacts are inference-only in Academy LoRA pipeline"

    if _is_ollama_artifact(provider_lc=provider_lc, source=source):
        return (
            "Ollama runtime models are inference-focused in this pipeline; "
            "select a HuggingFace/Unsloth base model for Academy training"
        )

    model_path = _resolve_model_path_from_metadata(model_metadata)
    if model_path is None:
        if _looks_like_hf_repo_id(model_id):
            return None
        return "Model capability cannot be verified for Academy LoRA training"

    return _non_trainable_reason_from_model_path(model_path)


def _is_onnx_artifact(*, provider_lc: str, runtime: str, model_type: str) -> bool:
    return provider_lc == "onnx" or runtime == "onnx" or model_type == "onnx"


def _is_ollama_artifact(*, provider_lc: str, source: str) -> bool:
    return provider_lc == "ollama" or source == "ollama"


def _non_trainable_reason_from_model_path(model_path: Path) -> Optional[str]:
    if model_path.is_file():
        suffix = model_path.suffix.lower()
        if suffix in {".onnx", ".gguf"}:
            return f"Model artifact '{model_path.name}' is inference-only and not LoRA-trainable"
        return "Model file artifact is not a supported HuggingFace training layout"
    if not model_path.is_dir():
        return "Model path does not point to a valid local model directory"
    if not (model_path / "config.json").exists():
        return "Missing config.json in local model directory"
    if not _has_hf_weights(model_path):
        return "Missing HuggingFace weight files required for LoRA training"
    return None


def get_model_non_trainable_reason(
    model_id: str,
    provider: Optional[str] = None,
    model_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return reason why model is not trainable, or None when trainable."""
    model_id_lc = model_id.lower()
    provider_lc = (provider or "").lower()

    if provider_lc in {"openai", "azure-openai", "anthropic", "google-gemini"}:
        return "External API models do not support local Academy LoRA training"

    if provider_lc == "ollama":
        return (
            "Ollama runtime models are inference-focused in this pipeline; "
            "select a HuggingFace/Unsloth base model for Academy training"
        )

    if provider_lc == "onnx":
        return "ONNX runtime artifacts are inference-only in Academy LoRA pipeline"

    if model_metadata:
        artifact_reason = _non_trainable_reason_from_local_artifacts(
            model_id=model_id,
            provider_lc=provider_lc,
            model_metadata=model_metadata,
        )
        if artifact_reason is not None:
            return artifact_reason
        # Local model passed artifact-level capability checks.
        return None

    blocked_name_markers = ("gpt-", "claude", "gemini")
    if any(marker in model_id_lc for marker in blocked_name_markers):
        return "Model family does not support local Academy LoRA training"

    # For non-local models (e.g. remote HF/Unsloth IDs) use repository-id shape.
    if _looks_like_hf_repo_id(model_id):
        return None

    return "Model capability cannot be verified for Academy LoRA training"


def build_model_label(
    model_id: str, provider: str, source: Optional[str] = None
) -> str:
    """Build human-readable model label for Academy UI."""
    source_suffix = f" [{source}]" if source else ""
    return f"{model_id} ({provider}){source_suffix}"


def classify_model_source_type(
    *,
    provider: str,
    model_metadata: Optional[Dict[str, Any]] = None,
) -> ModelSourceType:
    """Classify training execution location for Academy picker contract."""
    provider_lc = provider.strip().lower()
    if provider_lc in PAID_CLOUD_PROVIDERS:
        return "cloud"

    training_runtime = ""
    if model_metadata:
        training_runtime = str(model_metadata.get("training_runtime") or "").lower()
    if training_runtime in {"api-cloud", "cloud-api"}:
        return "cloud"

    model_id_lc = str(model_metadata.get("name") if model_metadata else "").lower()
    if any(marker in model_id_lc for marker in PAID_MODEL_MARKERS):
        return "cloud"
    return "local"


def classify_model_cost_tier(
    *, source_type: ModelSourceType, provider: str, model_id: str
) -> ModelCostTier:
    """Classify training-cost tier with safe defaults."""
    if source_type == "local":
        return "free"

    provider_lc = provider.strip().lower()
    model_id_lc = model_id.lower()
    if provider_lc in FREE_CLOUD_PROVIDERS:
        return "free"
    if provider_lc in PAID_CLOUD_PROVIDERS:
        return "paid"
    if any(marker in model_id_lc for marker in PAID_MODEL_MARKERS):
        return "paid"
    return "unknown"


def resolve_model_priority_bucket(
    *,
    source_type: ModelSourceType,
    cost_tier: ModelCostTier,
    installed_local: bool,
) -> int:
    """Return deterministic priority bucket for local-first Academy UX."""
    if source_type == "local" and installed_local:
        return 0
    if source_type == "local":
        return 1
    if cost_tier == "free":
        return 2
    if cost_tier == "unknown":
        return 3
    return 4


def _canonical_local_runtime_id(value: str) -> Optional[str]:
    normalized = value.strip().lower()
    if normalized in {"vllm", "ollama", "onnx"}:
        return normalized
    return None


def discover_available_runtime_targets(local_models: List[Dict[str, Any]]) -> List[str]:
    """Discover runtime targets from actually available local model stack."""
    discovered: Set[str] = set()
    for model in local_models:
        candidates = (
            str(model.get("runtime") or ""),
            str(model.get("provider") or ""),
            str(model.get("source") or ""),
        )
        for candidate in candidates:
            runtime_id = _canonical_local_runtime_id(candidate)
            if runtime_id:
                discovered.add(runtime_id)
    ordered = [runtime for runtime in LOCAL_RUNTIME_PREFERENCE if runtime in discovered]
    return ordered


def resolve_runtime_compatibility(
    *,
    provider: str,
    available_runtime_ids: List[str],
    model_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, bool]:
    """Resolve where trained model+adapter can be served for inference."""
    compatibility: Dict[str, bool] = dict.fromkeys(available_runtime_ids, False)
    if not compatibility:
        return compatibility

    provider_lc = provider.strip().lower()
    runtime_hint = ""
    if model_metadata:
        runtime_hint = str(model_metadata.get("runtime") or "").strip().lower()

    preferred: Set[str] = set()
    runtime_hint_id = _canonical_local_runtime_id(runtime_hint)
    provider_hint_id = _canonical_local_runtime_id(provider_lc)

    if runtime_hint_id:
        preferred.add(runtime_hint_id)
    if provider_hint_id:
        preferred.add(provider_hint_id)

    # For HF/Unsloth trainable families, vLLM is primary, but Ollama is also a valid
    # deployment runtime for adapters in current contract (external training + runtime deploy).
    if not preferred and provider_lc in {
        "unsloth",
        "huggingface",
        "hf",
        "config",
        "unknown",
    }:
        if "vllm" in compatibility:
            preferred.add("vllm")
        if "ollama" in compatibility:
            preferred.add("ollama")

    for runtime_id in preferred:
        if runtime_id in compatibility:
            compatibility[runtime_id] = True

    return compatibility


def resolve_recommended_runtime(
    runtime_compatibility: Dict[str, bool],
) -> Optional[str]:
    """Resolve primary runtime from compatibility map."""
    for runtime in LOCAL_RUNTIME_PREFERENCE:
        if runtime_compatibility.get(runtime):
            return runtime
    for runtime in sorted(runtime_compatibility):
        if runtime_compatibility.get(runtime):
            return runtime
    return None


def get_default_trainable_models_catalog(
    available_runtime_ids: List[str],
) -> List[TrainableModelInfo]:
    """Return default fallback catalog for trainable models."""
    default_runtime_compatibility = resolve_runtime_compatibility(
        provider="huggingface",
        available_runtime_ids=available_runtime_ids,
    )
    default_recommended_runtime = resolve_recommended_runtime(
        default_runtime_compatibility
    )
    return [
        TrainableModelInfo(
            model_id="unsloth/Phi-3-mini-4k-instruct",
            label="Phi-3 Mini 4K (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=True,
            source_type="local",
            cost_tier="free",
            priority_bucket=1,
            runtime_compatibility=dict(default_runtime_compatibility),
            recommended_runtime=default_recommended_runtime,
        ),
        TrainableModelInfo(
            model_id="unsloth/Phi-3.5-mini-instruct",
            label="Phi-3.5 Mini (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=False,
            source_type="local",
            cost_tier="free",
            priority_bucket=1,
            runtime_compatibility=dict(default_runtime_compatibility),
            recommended_runtime=default_recommended_runtime,
        ),
        TrainableModelInfo(
            model_id="unsloth/Llama-3.2-1B-Instruct",
            label="Llama 3.2 1B (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=False,
            source_type="local",
            cost_tier="free",
            priority_bucket=1,
            runtime_compatibility=dict(default_runtime_compatibility),
            recommended_runtime=default_recommended_runtime,
        ),
        TrainableModelInfo(
            model_id="unsloth/Llama-3.2-3B-Instruct",
            label="Llama 3.2 3B (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=False,
            source_type="local",
            cost_tier="free",
            priority_bucket=1,
            runtime_compatibility=dict(default_runtime_compatibility),
            recommended_runtime=default_recommended_runtime,
        ),
        TrainableModelInfo(
            model_id="Qwen/Qwen2.5-Coder-3B-Instruct",
            label="Qwen2.5 Coder 3B (HuggingFace)",
            provider="huggingface",
            trainable=True,
            recommended=False,
            source_type="local",
            cost_tier="free",
            priority_bucket=1,
            runtime_compatibility=dict(default_runtime_compatibility),
            recommended_runtime=default_recommended_runtime,
        ),
        TrainableModelInfo(
            model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
            label="Qwen2.5 Coder 7B (HuggingFace)",
            provider="huggingface",
            trainable=True,
            recommended=False,
            source_type="local",
            cost_tier="free",
            priority_bucket=1,
            runtime_compatibility=dict(default_runtime_compatibility),
            recommended_runtime=default_recommended_runtime,
        ),
        TrainableModelInfo(
            model_id="google/gemma-3-4b-it",
            label="Gemma 3 4B Instruct (HuggingFace)",
            provider="huggingface",
            trainable=True,
            recommended=False,
            source_type="local",
            cost_tier="free",
            priority_bucket=1,
            runtime_compatibility=dict(default_runtime_compatibility),
            recommended_runtime=default_recommended_runtime,
        ),
    ]


def add_trainable_model_from_catalog(
    result: List[TrainableModelInfo],
    seen: set[str],
    model_id: str,
    provider: str,
    label: str,
    default_model: str,
    reason: Optional[str] = None,
    installed_local: bool = False,
    source_type: Optional[ModelSourceType] = None,
    cost_tier: Optional[ModelCostTier] = None,
    available_runtime_ids: Optional[List[str]] = None,
    model_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Append model entry when unseen."""
    if not model_id or model_id in seen:
        return
    resolved_source_type = source_type or classify_model_source_type(
        provider=provider,
        model_metadata=model_metadata,
    )
    resolved_cost_tier = cost_tier or classify_model_cost_tier(
        source_type=resolved_source_type,
        provider=provider,
        model_id=model_id,
    )
    priority_bucket = resolve_model_priority_bucket(
        source_type=resolved_source_type,
        cost_tier=resolved_cost_tier,
        installed_local=installed_local,
    )
    runtime_compatibility = resolve_runtime_compatibility(
        provider=provider,
        available_runtime_ids=available_runtime_ids or [],
        model_metadata=model_metadata,
    )
    recommended_runtime = resolve_recommended_runtime(runtime_compatibility)
    result.append(
        TrainableModelInfo(
            model_id=model_id,
            label=label,
            provider=provider,
            trainable=reason is None,
            reason_if_not_trainable=reason,
            recommended=(model_id == default_model),
            installed_local=installed_local,
            source_type=resolved_source_type,
            cost_tier=resolved_cost_tier,
            priority_bucket=priority_bucket,
            runtime_compatibility=runtime_compatibility,
            recommended_runtime=recommended_runtime,
        )
    )
    seen.add(model_id)


def collect_local_trainable_models(
    local_models: List[Dict[str, Any]],
    default_model: str,
    available_runtime_ids: List[str],
    result: List[TrainableModelInfo],
    seen: set[str],
) -> None:
    """Collect models from model manager catalog."""
    for model in local_models:
        model_id = str(model.get("name") or "").strip()
        if not model_id or model_id in seen:
            continue
        provider = str(model.get("provider") or model.get("source") or "unknown")
        source = str(model.get("source") or "")
        reason = get_model_non_trainable_reason(
            model_id=model_id,
            provider=provider,
            model_metadata=model,
        )
        add_trainable_model_from_catalog(
            result=result,
            seen=seen,
            model_id=model_id,
            provider=provider,
            label=build_model_label(
                model_id=model_id, provider=provider, source=source
            ),
            default_model=default_model,
            reason=reason,
            installed_local=True,
            available_runtime_ids=available_runtime_ids,
            model_metadata=model,
        )


def collect_default_trainable_models(
    default_model: str,
    available_runtime_ids: List[str],
    result: List[TrainableModelInfo],
    seen: set[str],
) -> None:
    """Collect fallback defaults for Academy model list."""
    for entry in get_default_trainable_models_catalog(
        available_runtime_ids=available_runtime_ids
    ):
        if entry.model_id in seen:
            continue
        entry.recommended = entry.model_id == default_model
        result.append(entry)
        seen.add(entry.model_id)


def ensure_default_model_visible(
    default_model: str,
    available_runtime_ids: List[str],
    result: List[TrainableModelInfo],
    seen: set[str],
) -> None:
    """Ensure configured default model is present even if custom/non-trainable."""
    if not default_model or default_model in seen:
        return
    reason = get_model_non_trainable_reason(model_id=default_model, provider=None)
    add_trainable_model_from_catalog(
        result=result,
        seen=seen,
        model_id=default_model,
        provider="config",
        label=f"{default_model} (default)",
        default_model=default_model,
        reason=reason,
        available_runtime_ids=available_runtime_ids,
    )


def _trainable_model_family_key(model_id: str) -> str:
    normalized = model_id.strip().lower()
    if "/" in normalized:
        normalized = normalized.split("/")[-1]
    normalized = _TRAINABLE_MODEL_ALIAS_TO_CANONICAL.get(normalized, normalized)
    return normalized


def _trainable_model_preference(
    item: TrainableModelInfo,
) -> tuple[int, int, int, int, str]:
    # Prefer locally installed entries for the same model family, then stable ordering.
    return (
        0 if item.installed_local else 1,
        0 if item.source_type == "local" else 1,
        0 if item.recommended else 1,
        item.model_id.count("/"),
        item.model_id.lower(),
    )


async def list_trainable_models(
    mgr: Any,
    *,
    local_models: Optional[List[Dict[str, Any]]] = None,
) -> List[TrainableModelInfo]:
    """Build sorted list of Academy trainable models."""
    from venom_core.config import SETTINGS

    result: List[TrainableModelInfo] = []
    seen: set[str] = set()
    default_model_raw = getattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "")
    default_model = (
        default_model_raw.strip() if isinstance(default_model_raw, str) else ""
    )
    discovered_local_models: List[Dict[str, Any]] = local_models or []
    available_runtime_ids: List[str] = []

    if discovered_local_models:
        available_runtime_ids = discover_available_runtime_targets(
            discovered_local_models
        )
        collect_local_trainable_models(
            local_models=discovered_local_models,
            default_model=default_model,
            available_runtime_ids=available_runtime_ids,
            result=result,
            seen=seen,
        )
    elif mgr is not None:
        try:
            discovered_local_models = await mgr.list_local_models()
            available_runtime_ids = discover_available_runtime_targets(
                discovered_local_models
            )
            collect_local_trainable_models(
                local_models=discovered_local_models,
                default_model=default_model,
                available_runtime_ids=available_runtime_ids,
                result=result,
                seen=seen,
            )
        except Exception as exc:
            logger.warning("Failed to load local model catalog for Academy: %s", exc)

    collect_default_trainable_models(
        default_model=default_model,
        available_runtime_ids=available_runtime_ids,
        result=result,
        seen=seen,
    )
    ensure_default_model_visible(
        default_model=default_model,
        available_runtime_ids=available_runtime_ids,
        result=result,
        seen=seen,
    )
    # API contract for Academy model picker: return only actually trainable options.
    result = [item for item in result if item.trainable]
    deduped_by_family: dict[str, TrainableModelInfo] = {}
    for item in result:
        family_key = _trainable_model_family_key(item.model_id)
        existing = deduped_by_family.get(family_key)
        if existing is None or _trainable_model_preference(
            item
        ) < _trainable_model_preference(existing):
            deduped_by_family[family_key] = item
    result = list(deduped_by_family.values())
    result.sort(
        key=lambda item: (
            item.priority_bucket,
            not item.recommended,
            item.label.lower(),
            item.model_id.lower(),
        )
    )
    return result


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


def _resolve_local_runtime_id(runtime_id: str) -> Optional[str]:
    return _canonical_local_runtime_id(runtime_id)


def _canonical_runtime_model_id(model_id: str) -> str:
    normalized = model_id.strip().lower()
    if not normalized:
        return ""
    return _TRAINABLE_MODEL_ALIAS_TO_CANONICAL.get(normalized, normalized)


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


def _resolve_runtime_for_adapter_deploy(runtime_id: str | None) -> str:
    requested = (runtime_id or "").strip().lower()
    if requested:
        return requested
    active_runtime = get_active_llm_runtime()
    active_provider = str(getattr(active_runtime, "provider", "") or "").strip().lower()
    if active_provider:
        return active_provider
    fallback = str(getattr(SETTINGS, "ACTIVE_LLM_SERVER", "") or "").strip().lower()
    return fallback or "ollama"


def _runtime_endpoint_for_hash(runtime_id: str) -> str | None:
    if runtime_id == "vllm":
        return str(getattr(SETTINGS, "VLLM_ENDPOINT", "")).strip() or None
    if runtime_id == "onnx":
        return None
    return build_http_url("localhost", 11434, "/v1")


def _first_runtime_with_previous_model(
    *, config: Dict[str, Any], candidates: tuple[str, ...]
) -> tuple[str | None, str]:
    for candidate_runtime in candidates:
        prev_value = str(
            config.get(previous_model_key_for_server(candidate_runtime)) or ""
        ).strip()
        if prev_value:
            return candidate_runtime, prev_value
    return None, ""


def _resolve_runtime_for_rollback(
    *,
    active_runtime: Any,
    config: Dict[str, Any],
) -> tuple[str, str]:
    runtime_candidate = (
        str(getattr(active_runtime, "provider", "") or "").strip().lower()
    )
    runtime_candidate = (
        runtime_candidate
        or str(getattr(SETTINGS, "ACTIVE_LLM_SERVER", "") or "").strip().lower()
    )
    runtime_local_id = _resolve_local_runtime_id(runtime_candidate)
    if runtime_local_id is None:
        inferred_runtime, _ = _first_runtime_with_previous_model(
            config=config,
            candidates=("ollama", "vllm"),
        )
        runtime_local_id = inferred_runtime
    return runtime_local_id or "ollama", runtime_candidate


def _resolve_fallback_model_for_rollback(
    *,
    config: Dict[str, Any],
    runtime_local_id: str,
) -> tuple[str, str, str]:
    previous_key = previous_model_key_for_server(runtime_local_id)
    fallback_model = str(config.get(previous_key) or "").strip()
    if fallback_model:
        return runtime_local_id, previous_key, fallback_model
    inferred_runtime, inferred_model = _first_runtime_with_previous_model(
        config=config,
        candidates=("ollama", "vllm"),
    )
    if not inferred_runtime:
        return runtime_local_id, previous_key, ""
    return (
        inferred_runtime,
        previous_model_key_for_server(inferred_runtime),
        inferred_model,
    )


def _build_runtime_rollback_updates(
    *,
    mgr: Any,
    runtime_local_id: str,
    previous_key: str,
    fallback_model: str,
) -> Dict[str, Any]:
    updates: Dict[str, Any] = {
        "ACTIVE_LLM_SERVER": runtime_local_id,
        "LLM_MODEL_NAME": fallback_model,
        "HYBRID_LOCAL_MODEL": fallback_model,
        previous_key: "",
    }
    if runtime_local_id == "ollama":
        updates["LAST_MODEL_OLLAMA"] = fallback_model
        return updates
    if runtime_local_id != "vllm":
        return updates
    updates["LAST_MODEL_VLLM"] = fallback_model
    fallback_path = _resolve_local_runtime_model_path_by_name(
        mgr=mgr,
        model_name=fallback_model,
    )
    if not fallback_path:
        return updates
    updates["VLLM_MODEL_PATH"] = fallback_path
    updates["VLLM_SERVED_MODEL_NAME"] = fallback_model
    template_path = Path(fallback_path) / "chat_template.jinja"
    updates["VLLM_CHAT_TEMPLATE"] = str(template_path) if template_path.exists() else ""
    return updates


def _apply_runtime_rollback_settings(
    *,
    runtime_local_id: str,
    fallback_model: str,
    config_hash: str,
    updates: Dict[str, Any],
) -> None:
    SETTINGS.ACTIVE_LLM_SERVER = runtime_local_id
    SETTINGS.LLM_MODEL_NAME = fallback_model
    SETTINGS.HYBRID_LOCAL_MODEL = fallback_model
    SETTINGS.LLM_CONFIG_HASH = config_hash
    if runtime_local_id != "vllm":
        return
    if "VLLM_MODEL_PATH" in updates:
        SETTINGS.VLLM_MODEL_PATH = str(updates["VLLM_MODEL_PATH"])
    SETTINGS.VLLM_SERVED_MODEL_NAME = fallback_model
    SETTINGS.LAST_MODEL_VLLM = fallback_model
    _restart_vllm_runtime()


def _is_runtime_model_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    if not (path / "config.json").exists():
        return False
    if any(path.glob("*.safetensors")):
        return True
    if any(path.glob("pytorch_model*.bin")):
        return True
    if any(path.glob("model*.bin")):
        return True
    return False


def _resolve_repo_root() -> Path:
    root = Path(getattr(SETTINGS, "REPO_ROOT", ".")).resolve()
    return root


def _resolve_local_runtime_model_path_by_name(*, mgr: Any, model_name: str) -> str:
    candidate = model_name.strip()
    if not candidate:
        return ""
    search_dirs: list[Path] = []
    models_dir = getattr(mgr, "models_dir", None)
    if isinstance(models_dir, Path):
        search_dirs.append(models_dir)
    else:
        academy_dir = Path(getattr(SETTINGS, "ACADEMY_MODELS_DIR", "")).resolve()
        search_dirs.append(academy_dir)
    repo_models = _resolve_repo_root() / "models"
    if repo_models not in search_dirs:
        search_dirs.append(repo_models)
    for base in search_dirs:
        candidate_path = base / candidate
        if candidate_path.exists() and candidate_path.is_dir():
            return str(candidate_path)
    return ""


def _restart_vllm_runtime() -> None:
    service_script = _resolve_repo_root() / "scripts" / "llm" / "vllm_service.sh"
    if not service_script.exists():
        raise RuntimeError(f"vLLM service script not found: {service_script}")
    result = subprocess.run(
        ["bash", str(service_script), "restart"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"Failed to restart vLLM runtime: {stderr}")


def _build_vllm_runtime_model_from_adapter(
    *,
    adapter_dir: Path,
    base_model: str,
) -> Path:
    adapter_path = adapter_dir / "adapter"
    if not adapter_path.exists():
        raise FileNotFoundError(f"Adapter path not found: {adapter_path}")

    runtime_dir = adapter_dir / "runtime_vllm"
    if _is_runtime_model_dir(runtime_dir):
        return runtime_dir

    tmp_dir = adapter_dir / "runtime_vllm_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "Missing dependencies required for vLLM adapter deploy. "
            "Install: pip install transformers peft torch"
        ) from exc

    has_cuda = bool(torch.cuda.is_available())
    model_kwargs: Dict[str, Any] = {
        "torch_dtype": torch.float16 if has_cuda else torch.float32,
    }
    if has_cuda:
        model_kwargs["device_map"] = "auto"
    else:
        model_kwargs["low_cpu_mem_usage"] = True

    try:
        base_model_obj = AutoModelForCausalLM.from_pretrained(
            base_model, **model_kwargs
        )
        peft_model = PeftModel.from_pretrained(base_model_obj, str(adapter_path))
        merged_model = peft_model.merge_and_unload()
        merged_model.save_pretrained(str(tmp_dir), safe_serialization=True)

        tokenizer_source = (
            str(adapter_path)
            if (adapter_path / "tokenizer.json").exists()
            else base_model
        )
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_source)
        tokenizer.save_pretrained(str(tmp_dir))
        (tmp_dir / "venom_runtime_vllm.json").write_text(
            json.dumps(
                {
                    "base_model": base_model,
                    "adapter_path": str(adapter_path),
                    "runtime": "vllm",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    tmp_dir.rename(runtime_dir)
    return runtime_dir


def _deploy_adapter_to_vllm_runtime(
    *,
    adapter_id: str,
) -> Dict[str, Any]:
    models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR).resolve()
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    adapter_path = adapter_dir / "adapter"
    if not adapter_path.exists():
        raise FileNotFoundError("Adapter not found")
    base_model = _require_trusted_adapter_base_model(
        adapter_dir=adapter_dir,
        default_model=str(getattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "")).strip(),
    ).strip()
    if not base_model:
        raise RuntimeError("Adapter base model is empty; cannot deploy to vLLM")

    runtime_model_dir = _build_vllm_runtime_model_from_adapter(
        adapter_dir=adapter_dir,
        base_model=base_model,
    )
    if not _is_runtime_model_dir(runtime_model_dir):
        raise RuntimeError(
            f"Failed to prepare runtime-usable vLLM model from adapter: {runtime_model_dir}"
        )

    config = config_manager.get_config(mask_secrets=False)
    last_model_key = "LAST_MODEL_VLLM"
    previous_model_key = previous_model_key_for_server("vllm")
    previous_model = str(
        config.get(last_model_key) or config.get("LLM_MODEL_NAME") or ""
    ).strip()
    selected_model = f"venom-adapter-{adapter_id}"
    template_path = runtime_model_dir / "chat_template.jinja"
    updates: Dict[str, Any] = {
        "LLM_SERVICE_TYPE": "local",
        "ACTIVE_LLM_SERVER": "vllm",
        "LLM_MODEL_NAME": selected_model,
        "HYBRID_LOCAL_MODEL": selected_model,
        "VLLM_MODEL_PATH": str(runtime_model_dir),
        "VLLM_SERVED_MODEL_NAME": selected_model,
        "VLLM_CHAT_TEMPLATE": str(template_path) if template_path.exists() else "",
        last_model_key: selected_model,
    }
    if previous_model and previous_model != selected_model:
        updates[previous_model_key] = previous_model
    endpoint = _runtime_endpoint_for_hash("vllm")
    config_hash = compute_llm_config_hash("vllm", endpoint, selected_model)
    updates["LLM_CONFIG_HASH"] = config_hash
    config_manager.update_config(updates)
    try:
        SETTINGS.LLM_SERVICE_TYPE = "local"
        SETTINGS.ACTIVE_LLM_SERVER = "vllm"
        SETTINGS.LLM_MODEL_NAME = selected_model
        SETTINGS.HYBRID_LOCAL_MODEL = selected_model
        SETTINGS.VLLM_MODEL_PATH = str(runtime_model_dir)
        SETTINGS.VLLM_SERVED_MODEL_NAME = selected_model
        SETTINGS.VLLM_CHAT_TEMPLATE = (
            str(template_path) if template_path.exists() else ""
        )
        SETTINGS.LAST_MODEL_VLLM = selected_model
        SETTINGS.LLM_CONFIG_HASH = config_hash
    except Exception:
        logger.warning("Failed to update SETTINGS for vLLM adapter deploy.")

    _restart_vllm_runtime()
    return {
        "deployed": True,
        "runtime_id": "vllm",
        "chat_model": selected_model,
        "config_hash": config_hash,
        "runtime_model_path": str(runtime_model_dir),
    }


def _deploy_adapter_to_chat_runtime(
    *,
    mgr: Any,
    adapter_id: str,
    runtime_id: str | None,
    model_id: str | None,
) -> Dict[str, Any]:
    runtime_candidate = _resolve_runtime_for_adapter_deploy(runtime_id)
    runtime_local_id = _resolve_local_runtime_id(runtime_candidate)
    if runtime_local_id is None:
        return {
            "deployed": False,
            "reason": f"runtime_not_local:{runtime_candidate}",
            "runtime_id": runtime_candidate,
        }

    if runtime_local_id == "onnx":
        return {
            "deployed": False,
            "reason": f"runtime_not_supported:{runtime_local_id}",
            "runtime_id": runtime_local_id,
        }
    if runtime_local_id == "vllm":
        return _deploy_adapter_to_vllm_runtime(
            adapter_id=adapter_id,
        )

    requested_model = str(model_id or "").strip()
    if not requested_model:
        config_snapshot = config_manager.get_config(mask_secrets=False)
        requested_model = str(
            config_snapshot.get("LAST_MODEL_OLLAMA")
            or config_snapshot.get("LLM_MODEL_NAME")
            or ""
        ).strip()

    models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR).resolve()
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    adapter_base_model = _require_trusted_adapter_base_model(
        adapter_dir=adapter_dir,
        default_model=str(getattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "")).strip(),
    ).strip()
    if adapter_base_model and requested_model:
        adapter_canonical = _canonical_runtime_model_id(adapter_base_model)
        requested_canonical = _canonical_runtime_model_id(requested_model)
        if requested_canonical and requested_canonical != adapter_canonical:
            reason_code = ADAPTER_BASE_MODEL_MISMATCH
            message = (
                "Adapter base model does not match selected Ollama runtime FROM model. "
                f"runtime_model='{requested_model}', adapter_base_model='{adapter_base_model}'."
            )
            logger.warning(
                "Blocking Ollama adapter deploy due to %s "
                "(adapter_id=%s, runtime_model=%s, adapter_base_model=%s)"
                % (
                    reason_code,
                    adapter_id,
                    requested_model,
                    adapter_base_model,
                )
            )
            raise ValueError(f"{reason_code}: {message}")

    ollama_model_name = f"venom-adapter-{adapter_id}"
    deployed_model = mgr.create_ollama_modelfile(
        version_id=adapter_id,
        output_name=ollama_model_name,
    )
    if not deployed_model:
        raise RuntimeError("Failed to create Ollama model for adapter deployment")

    config = config_manager.get_config(mask_secrets=False)
    last_model_key = "LAST_MODEL_OLLAMA"
    previous_model_key = previous_model_key_for_server(runtime_local_id)
    previous_model = str(
        config.get(last_model_key) or config.get("LLM_MODEL_NAME") or ""
    ).strip()
    selected_model = str(deployed_model)
    updates: Dict[str, Any] = {
        "ACTIVE_LLM_SERVER": runtime_local_id,
        "LLM_MODEL_NAME": selected_model,
        "HYBRID_LOCAL_MODEL": selected_model,
        last_model_key: selected_model,
    }
    if previous_model and previous_model != selected_model:
        updates[previous_model_key] = previous_model
    endpoint = _runtime_endpoint_for_hash(runtime_local_id)
    config_hash = compute_llm_config_hash(runtime_local_id, endpoint, selected_model)
    updates["LLM_CONFIG_HASH"] = config_hash
    config_manager.update_config(updates)
    try:
        SETTINGS.ACTIVE_LLM_SERVER = runtime_local_id
        SETTINGS.LLM_MODEL_NAME = selected_model
        SETTINGS.HYBRID_LOCAL_MODEL = selected_model
        SETTINGS.LLM_CONFIG_HASH = config_hash
    except Exception:
        logger.warning("Failed to update SETTINGS for adapter chat deployment.")

    return {
        "deployed": True,
        "runtime_id": runtime_local_id,
        "chat_model": selected_model,
        "config_hash": config_hash,
    }


def _rollback_chat_runtime_after_adapter_deactivation(*, mgr: Any) -> Dict[str, Any]:
    active_runtime = get_active_llm_runtime()
    config = config_manager.get_config(mask_secrets=False)
    runtime_local_id, _ = _resolve_runtime_for_rollback(
        active_runtime=active_runtime,
        config=config,
    )

    if runtime_local_id == "onnx":
        return {
            "rolled_back": False,
            "reason": f"runtime_not_supported:{runtime_local_id}",
            "runtime_id": runtime_local_id,
        }

    runtime_local_id, previous_key, fallback_model = (
        _resolve_fallback_model_for_rollback(
            config=config,
            runtime_local_id=runtime_local_id,
        )
    )
    if not fallback_model:
        return {
            "rolled_back": False,
            "reason": "previous_model_missing",
            "runtime_id": runtime_local_id,
        }

    updates = _build_runtime_rollback_updates(
        mgr=mgr,
        runtime_local_id=runtime_local_id,
        previous_key=previous_key,
        fallback_model=fallback_model,
    )
    endpoint = _runtime_endpoint_for_hash(runtime_local_id)
    config_hash = compute_llm_config_hash(runtime_local_id, endpoint, fallback_model)
    updates["LLM_CONFIG_HASH"] = config_hash
    config_manager.update_config(updates)
    try:
        _apply_runtime_rollback_settings(
            runtime_local_id=runtime_local_id,
            fallback_model=fallback_model,
            config_hash=config_hash,
            updates=updates,
        )
    except Exception:
        logger.warning("Failed to update SETTINGS during adapter chat rollback.")

    return {
        "rolled_back": True,
        "runtime_id": runtime_local_id,
        "chat_model": fallback_model,
        "config_hash": config_hash,
    }


def _resolve_adapter_dir(*, models_dir: Path, adapter_id: str) -> Path:
    """Resolve adapter directory and reject path traversal."""
    adapter_dir = (models_dir / adapter_id).resolve()
    try:
        adapter_dir.relative_to(models_dir)
    except ValueError as exc:
        raise ValueError(
            f"Invalid adapter_id '{adapter_id}': outside of models directory."
        ) from exc
    return adapter_dir


async def validate_adapter_runtime_compatibility(
    *,
    mgr: Any,
    adapter_id: str,
    runtime_id: str,
    model_id: str | None = None,
) -> None:
    """Validate that adapter base model can run on selected inference runtime."""
    from venom_core.config import SETTINGS

    runtime_local_id = _resolve_local_runtime_id(runtime_id.strip().lower())
    if not runtime_id.strip():
        return
    if runtime_local_id is None:
        raise ValueError(
            "Academy adapter supports only local runtimes (ollama/vllm/onnx); "
            f"got '{runtime_id}'."
        )

    models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR).resolve()
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    base_model = _require_trusted_adapter_base_model(
        adapter_dir=adapter_dir,
        default_model=str(getattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "")).strip(),
    ).strip()
    if not base_model:
        return

    trainable_models = await list_trainable_models(mgr=mgr)
    trainable_by_model = {item.model_id.lower(): item for item in trainable_models}
    trainable_info = trainable_by_model.get(base_model.lower())
    if trainable_info is None:
        return

    runtime_compatibility = dict(trainable_info.runtime_compatibility or {})
    if not runtime_compatibility:
        return

    if runtime_compatibility.get(runtime_local_id):
        selected_model = str(model_id or "").strip()
        if not selected_model:
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
        if selected_canonical == base_canonical:
            return
        raise ValueError(
            f"{ADAPTER_BASE_MODEL_MISMATCH}: Adapter base model does not match selected runtime model. "
            f"Selected model: '{selected_model}', adapter base model: '{base_model}'."
        )

    compatible_runtimes = sorted(
        runtime
        for runtime, is_supported in runtime_compatibility.items()
        if is_supported
    )
    if compatible_runtimes:
        supported_hint = ", ".join(compatible_runtimes)
        raise ValueError(
            "Adapter is incompatible with selected runtime "
            f"'{runtime_local_id}'. Compatible runtimes: {supported_hint}."
        )
    raise ValueError(
        "Adapter does not expose compatible local runtimes for activation."
    )


async def audit_adapters(
    *,
    mgr: Any,
    runtime_id: str | None = None,
    model_id: str | None = None,
) -> Dict[str, Any]:
    """Preflight audit for historical adapters metadata confidence and compatibility."""
    models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR)
    if not models_dir.exists():
        return {
            "count": 0,
            "adapters": [],
            "summary": {
                "compatible": 0,
                "blocked_unknown_base": 0,
                "blocked_mismatch": 0,
            },
        }

    runtime_local_id = _resolve_local_runtime_id(str(runtime_id or "").strip().lower())
    selected_model = str(model_id or "").strip()
    selected_model_canonical = _canonical_runtime_model_id(selected_model)

    active_adapter_id = ""
    if mgr:
        active_info = mgr.get_active_adapter_info()
        if isinstance(active_info, dict):
            active_adapter_id = str(active_info.get("adapter_id") or "").strip()

    items: List[Dict[str, Any]] = []
    for training_dir in sorted(models_dir.iterdir(), key=lambda p: p.name):
        if not training_dir.is_dir():
            continue
        adapter_path = training_dir / "adapter"
        if not adapter_path.exists():
            continue

        assessment = _assess_adapter_base_model(
            adapter_dir=training_dir,
            default_model=str(
                getattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "")
            ).strip(),
        )
        base_model = str(assessment.get("base_model") or "").strip()
        reason_code = str(assessment.get("reason_code") or "").strip() or None
        category = "compatible"
        message = "Adapter metadata is consistent"

        if not bool(assessment.get("trusted")):
            if reason_code == ADAPTER_METADATA_INCONSISTENT:
                category = "blocked_mismatch"
                message = str(
                    assessment.get("reason") or "Inconsistent adapter metadata"
                )
            else:
                category = "blocked_unknown_base"
                reason_code = ADAPTER_BASE_MODEL_UNKNOWN
                message = str(
                    assessment.get("reason")
                    or "Reliable base_model metadata is missing"
                )
        elif runtime_local_id and selected_model_canonical:
            base_canonical = _canonical_runtime_model_id(base_model)
            if base_canonical and base_canonical != selected_model_canonical:
                category = "blocked_mismatch"
                reason_code = ADAPTER_BASE_MODEL_MISMATCH
                message = (
                    "Adapter base model does not match selected runtime model "
                    f"('{selected_model}')"
                )

        items.append(
            {
                "adapter_id": training_dir.name,
                "adapter_path": str(adapter_path),
                "base_model": base_model,
                "canonical_base_model": str(
                    assessment.get("canonical_base_model") or ""
                ),
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


async def list_adapters(mgr: Any) -> List[AdapterInfo]:
    """List available local adapters and mark active one."""
    from venom_core.config import SETTINGS

    adapters: List[AdapterInfo] = []
    models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR)

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
                    SETTINGS.ACADEMY_DEFAULT_BASE_MODEL,
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
    from venom_core.config import SETTINGS

    models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR).resolve()
    adapter_dir = _resolve_adapter_dir(models_dir=models_dir, adapter_id=adapter_id)
    adapter_path = (adapter_dir / "adapter").resolve()

    if not adapter_path.exists():
        raise FileNotFoundError("Adapter not found")

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
        deploy_payload = _deploy_adapter_to_chat_runtime(
            mgr=mgr,
            adapter_id=adapter_id,
            runtime_id=runtime_id,
            model_id=model_id,
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
