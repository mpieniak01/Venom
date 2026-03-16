"""Trainable model catalog service for Academy."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set

from venom_core.api.schemas.academy import TrainableModelInfo
from venom_core.utils.logger import get_logger

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
_TRAINING_BASE_PROVIDERS = {"unsloth", "huggingface", "hf", "config", "unknown"}
GEMMA_3_4B_HF_REPO = "google/gemma-3-4b-it"
UNSLOTH_GEMMA_2_2B_REPO = "unsloth/gemma-2-2b-it"
PHI_35_MINI_CANONICAL = "phi-3.5-mini-instruct"
LLAMA_32_1B_CANONICAL = "llama-3.2-1b-instruct"
LLAMA_32_3B_CANONICAL = "llama-3.2-3b-instruct"
_TRAINABLE_MODEL_ALIAS_TO_CANONICAL: Dict[str, str] = {
    "gemma2:2b": "gemma-2-2b-it",
    "gemma2:latest": "gemma-2-2b-it",
    "google/gemma-2-2b-it": "gemma-2-2b-it",
    UNSLOTH_GEMMA_2_2B_REPO: "gemma-2-2b-it",
    "gemma-2-2b-it": "gemma-2-2b-it",
    "gemma3:latest": "gemma-3-4b-it",
    "gemma3:4b": "gemma-3-4b-it",
    "gemma3:1b": "gemma-3-1b-it",
    GEMMA_3_4B_HF_REPO: "gemma-3-4b-it",
    "google/gemma-3-1b-it": "gemma-3-1b-it",
    "phi3:mini": "phi-3-mini-4k-instruct",
    "phi3:latest": "phi-3-mini-4k-instruct",
    "unsloth/phi-3-mini-4k-instruct": "phi-3-mini-4k-instruct",
    "microsoft/phi-3-mini-4k-instruct": "phi-3-mini-4k-instruct",
    "unsloth/phi-3.5-mini-instruct": PHI_35_MINI_CANONICAL,
    "microsoft/phi-3.5-mini-instruct": PHI_35_MINI_CANONICAL,
    "llama3.2:1b": LLAMA_32_1B_CANONICAL,
    "llama3.2:3b": LLAMA_32_3B_CANONICAL,
    "unsloth/llama-3.2-1b-instruct": LLAMA_32_1B_CANONICAL,
    "unsloth/llama-3.2-3b-instruct": LLAMA_32_3B_CANONICAL,
    "qwen2.5-coder:3b": "qwen/qwen2.5-coder-3b-instruct",
    "qwen2.5-coder:7b": "qwen/qwen2.5-coder-7b-instruct",
}
_CANONICAL_TO_PREFERRED_TRAINING_BASE: Dict[str, str] = {
    "gemma-2-2b-it": UNSLOTH_GEMMA_2_2B_REPO,
    "gemma-3-4b-it": GEMMA_3_4B_HF_REPO,
    "gemma-3-1b-it": "google/gemma-3-1b-it",
    "phi-3-mini-4k-instruct": "unsloth/Phi-3-mini-4k-instruct",
    PHI_35_MINI_CANONICAL: "unsloth/Phi-3.5-mini-instruct",
    LLAMA_32_1B_CANONICAL: "unsloth/Llama-3.2-1B-Instruct",
    LLAMA_32_3B_CANONICAL: "unsloth/Llama-3.2-3B-Instruct",
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

    # Canonical trainable families may be referenced by normalized local/runtime ids
    # (e.g. "gemma-3-4b-it") without HF repo prefix.
    if model_id_lc in _TRAINABLE_MODEL_ALIAS_TO_CANONICAL.values():
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


def discover_runtime_model_families(
    local_models: List[Dict[str, Any]],
) -> Dict[str, Set[str]]:
    """Build runtime -> canonical model-family index from local runtime catalog."""
    discovered: Dict[str, Set[str]] = {}
    for model in local_models:
        runtime_id = _canonical_local_runtime_id(
            str(
                model.get("runtime")
                or model.get("provider")
                or model.get("source")
                or ""
            )
        )
        if not runtime_id:
            continue
        canonical_family = _canonical_runtime_model_id(str(model.get("name") or ""))
        if not canonical_family:
            continue
        discovered.setdefault(runtime_id, set()).add(canonical_family)
    return discovered


def resolve_runtime_compatibility(
    *,
    provider: str,
    available_runtime_ids: List[str],
    model_id: str | None = None,
    model_metadata: Optional[Dict[str, Any]] = None,
    runtime_model_families: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, bool]:
    """Resolve where trained model+adapter can be served for inference."""
    compatibility: Dict[str, bool] = dict.fromkeys(available_runtime_ids, False)
    if not compatibility:
        return compatibility

    provider_lc = provider.strip().lower()
    runtime_hint = str((model_metadata or {}).get("runtime") or "").strip().lower()
    runtime_model_id = _runtime_model_id_for_compatibility(
        model_id=model_id,
        model_metadata=model_metadata,
    )
    preferred = _resolve_preferred_runtimes(
        provider_lc=provider_lc,
        compatibility=compatibility,
        runtime_hint=runtime_hint,
        model_id=model_id,
        runtime_model_id=runtime_model_id,
        model_metadata=model_metadata,
        runtime_model_families=runtime_model_families,
    )

    for runtime_id in preferred:
        if runtime_id in compatibility:
            if runtime_id == "ollama" and not _ollama_runtime_family_available(
                model_id=runtime_model_id,
                runtime_model_families=runtime_model_families,
            ):
                continue
            compatibility[runtime_id] = True

    return compatibility


def _runtime_model_id_for_compatibility(
    *,
    model_id: str | None,
    model_metadata: Optional[Dict[str, Any]],
) -> str:
    return model_id or str((model_metadata or {}).get("name") or "")


def _resolve_preferred_runtimes(
    *,
    provider_lc: str,
    compatibility: Dict[str, bool],
    runtime_hint: str,
    model_id: str | None,
    runtime_model_id: str,
    model_metadata: Optional[Dict[str, Any]],
    runtime_model_families: Optional[Dict[str, Set[str]]],
) -> Set[str]:
    preferred: Set[str] = set()
    _seed_preferred_runtime_hints(
        preferred=preferred,
        runtime_hint=runtime_hint,
        provider_lc=provider_lc,
    )
    _add_provider_default_runtimes(
        preferred=preferred,
        provider_lc=provider_lc,
        compatibility=compatibility,
        model_id=model_id,
    )
    _add_ollama_family_runtime(
        preferred=preferred,
        provider_lc=provider_lc,
        compatibility=compatibility,
        runtime_model_id=runtime_model_id,
        runtime_model_families=runtime_model_families,
    )
    _add_ollama_deploy_runtime(
        preferred=preferred,
        provider_lc=provider_lc,
        compatibility=compatibility,
        model_metadata=model_metadata,
    )
    _add_fallback_training_runtimes(
        preferred=preferred,
        provider_lc=provider_lc,
        compatibility=compatibility,
    )
    return preferred


def _seed_preferred_runtime_hints(
    *,
    preferred: Set[str],
    runtime_hint: str,
    provider_lc: str,
) -> None:
    runtime_hint_id = _canonical_local_runtime_id(runtime_hint)
    provider_hint_id = _canonical_local_runtime_id(provider_lc)
    if runtime_hint_id:
        preferred.add(runtime_hint_id)
    if provider_hint_id:
        preferred.add(provider_hint_id)


def _add_provider_default_runtimes(
    *,
    preferred: Set[str],
    provider_lc: str,
    compatibility: Dict[str, bool],
    model_id: str | None,
) -> None:
    if provider_lc not in _TRAINING_BASE_PROVIDERS:
        return
    if "vllm" in compatibility:
        preferred.add("vllm")
    if "ollama" in compatibility and model_id and _looks_like_hf_repo_id(model_id):
        preferred.add("ollama")
    # 202D: ONNX is a valid deploy target for HF/unsloth providers (merge→export pipeline).
    # Excluded: "unknown" and "config" — cannot guarantee PEFT-merge suitability for those.
    _ONNX_MERGE_EXPORT_PROVIDERS = {"huggingface", "hf", "unsloth"}
    if "onnx" in compatibility and provider_lc in _ONNX_MERGE_EXPORT_PROVIDERS:
        preferred.add("onnx")


def _add_ollama_family_runtime(
    *,
    preferred: Set[str],
    provider_lc: str,
    compatibility: Dict[str, bool],
    runtime_model_id: str,
    runtime_model_families: Optional[Dict[str, Set[str]]],
) -> None:
    if "ollama" not in compatibility or provider_lc in {"ollama", "onnx"}:
        return
    if _ollama_runtime_family_available(
        model_id=runtime_model_id,
        runtime_model_families=runtime_model_families,
    ):
        preferred.add("ollama")


def _add_ollama_deploy_runtime(
    *,
    preferred: Set[str],
    provider_lc: str,
    compatibility: Dict[str, bool],
    model_metadata: Optional[Dict[str, Any]],
) -> None:
    if "ollama" not in compatibility:
        return
    if _supports_ollama_adapter_deploy(
        provider_lc=provider_lc,
        model_metadata=model_metadata,
    ):
        preferred.add("ollama")


def _add_fallback_training_runtimes(
    *,
    preferred: Set[str],
    provider_lc: str,
    compatibility: Dict[str, bool],
) -> None:
    if preferred or provider_lc not in _TRAINING_BASE_PROVIDERS:
        return
    if "vllm" in compatibility:
        preferred.add("vllm")
    if "ollama" in compatibility:
        preferred.add("ollama")


def infer_training_provider(model_id: str) -> str:
    """Infer training provider from model identifier."""
    normalized = model_id.strip().lower()
    if ":" in normalized:
        return "ollama"
    if normalized.startswith("unsloth/"):
        return "unsloth"
    if "/" in normalized:
        return "huggingface"
    return "unknown"


def assess_runtime_base_model_compatibility(
    *,
    base_model: str,
    runtime_id: str,
    available_runtime_ids: List[str],
    runtime_model_families: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, Any]:
    """Assess runtime/base model compatibility with a single shared contract."""
    normalized_runtime_id = (
        _canonical_local_runtime_id(runtime_id) or runtime_id.strip().lower()
    )
    compatibility = resolve_runtime_compatibility(
        provider=infer_training_provider(base_model),
        available_runtime_ids=available_runtime_ids,
        model_metadata={"name": base_model},
        model_id=base_model,
        runtime_model_families=runtime_model_families,
    )
    compatible_runtimes = [
        runtime for runtime in LOCAL_RUNTIME_PREFERENCE if compatibility.get(runtime)
    ]
    is_compatible = bool(compatibility.get(normalized_runtime_id))
    reason_code = None
    if not is_compatible:
        reason_code = (
            "MODEL_RUNTIME_INCOMPATIBLE"
            if compatible_runtimes
            else "MODEL_RUNTIME_TARGETS_UNAVAILABLE"
        )
    return {
        "runtime_id": normalized_runtime_id,
        "compatibility": compatibility,
        "compatible_runtimes": compatible_runtimes,
        "is_compatible": is_compatible,
        "reason_code": reason_code,
    }


def _ollama_runtime_family_available(
    *,
    model_id: str,
    runtime_model_families: Optional[Dict[str, Set[str]]],
) -> bool:
    if not runtime_model_families:
        return False
    canonical_family = _canonical_runtime_model_id(model_id)
    if not canonical_family:
        return False
    return canonical_family in runtime_model_families.get("ollama", set())


def _supports_ollama_adapter_deploy(
    *,
    provider_lc: str,
    model_metadata: Optional[Dict[str, Any]],
) -> bool:
    if provider_lc in {"ollama", "onnx"}:
        return False
    if not model_metadata:
        return provider_lc in {"unsloth", "huggingface", "hf", "config", "unknown"}

    model_type = str(model_metadata.get("type") or "").lower()
    runtime = str(model_metadata.get("runtime") or "").lower()
    source = str(model_metadata.get("source") or "").lower()
    if _is_onnx_artifact(
        provider_lc=provider_lc, runtime=runtime, model_type=model_type
    ):
        return False
    if _is_ollama_artifact(provider_lc=provider_lc, source=source):
        return False

    model_path = _resolve_model_path_from_metadata(model_metadata)
    if model_path is None:
        return False
    return _non_trainable_reason_from_model_path(model_path) is None


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
    runtime_model_families: Optional[Dict[str, Set[str]]] = None,
) -> List[TrainableModelInfo]:
    """Return default fallback catalog for trainable models."""
    defaults = [
        ("unsloth/Phi-3-mini-4k-instruct", "Phi-3 Mini 4K (Unsloth)", "unsloth"),
        ("unsloth/Phi-3.5-mini-instruct", "Phi-3.5 Mini (Unsloth)", "unsloth"),
        ("unsloth/Llama-3.2-1B-Instruct", "Llama 3.2 1B (Unsloth)", "unsloth"),
        ("unsloth/Llama-3.2-3B-Instruct", "Llama 3.2 3B (Unsloth)", "unsloth"),
        (
            "Qwen/Qwen2.5-Coder-3B-Instruct",
            "Qwen2.5 Coder 3B (HuggingFace)",
            "huggingface",
        ),
        (
            "Qwen/Qwen2.5-Coder-7B-Instruct",
            "Qwen2.5 Coder 7B (HuggingFace)",
            "huggingface",
        ),
        (UNSLOTH_GEMMA_2_2B_REPO, "Gemma 2 2B Instruct (Unsloth)", "unsloth"),
        (GEMMA_3_4B_HF_REPO, "Gemma 3 4B Instruct (HuggingFace)", "huggingface"),
    ]
    result: List[TrainableModelInfo] = []
    for model_id, label, provider in defaults:
        runtime_compatibility = resolve_runtime_compatibility(
            provider=provider,
            available_runtime_ids=available_runtime_ids,
            model_id=model_id,
            runtime_model_families=runtime_model_families,
        )
        result.append(
            TrainableModelInfo(
                model_id=model_id,
                label=label,
                provider=provider,
                trainable=True,
                recommended=False,
                source_type="local",
                cost_tier="free",
                priority_bucket=1,
                runtime_compatibility=runtime_compatibility,
                recommended_runtime=resolve_recommended_runtime(runtime_compatibility),
            )
        )
    return result


def add_trainable_model_from_catalog(
    result: List[TrainableModelInfo],
    seen: set[str],
    model_id: str,
    provider: str,
    label: str,
    reason: Optional[str] = None,
    installed_local: bool = False,
    source_type: Optional[ModelSourceType] = None,
    cost_tier: Optional[ModelCostTier] = None,
    available_runtime_ids: Optional[List[str]] = None,
    model_metadata: Optional[Dict[str, Any]] = None,
    runtime_model_families: Optional[Dict[str, Set[str]]] = None,
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
        model_id=model_id,
        model_metadata=model_metadata,
        runtime_model_families=runtime_model_families,
    )
    recommended_runtime = resolve_recommended_runtime(runtime_compatibility)
    result.append(
        TrainableModelInfo(
            model_id=model_id,
            label=label,
            provider=provider,
            trainable=reason is None,
            reason_if_not_trainable=reason,
            recommended=False,
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
    available_runtime_ids: List[str],
    runtime_model_families: Dict[str, Set[str]],
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
            reason=reason,
            installed_local=True,
            available_runtime_ids=available_runtime_ids,
            model_metadata=model,
            runtime_model_families=runtime_model_families,
        )


def collect_default_trainable_models(
    available_runtime_ids: List[str],
    runtime_model_families: Dict[str, Set[str]],
    result: List[TrainableModelInfo],
    seen: set[str],
) -> None:
    """Collect fallback defaults for Academy model list."""
    for entry in get_default_trainable_models_catalog(
        available_runtime_ids=available_runtime_ids,
        runtime_model_families=runtime_model_families,
    ):
        if entry.model_id in seen:
            continue
        result.append(entry)
        seen.add(entry.model_id)


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
    result: List[TrainableModelInfo] = []
    seen: set[str] = set()
    discovered_local_models: List[Dict[str, Any]] = local_models or []
    available_runtime_ids: List[str] = []
    runtime_model_families: Dict[str, Set[str]] = {}

    if discovered_local_models:
        available_runtime_ids = discover_available_runtime_targets(
            discovered_local_models
        )
        runtime_model_families = discover_runtime_model_families(
            discovered_local_models
        )
        collect_local_trainable_models(
            local_models=discovered_local_models,
            available_runtime_ids=available_runtime_ids,
            runtime_model_families=runtime_model_families,
            result=result,
            seen=seen,
        )
    elif mgr is not None:
        try:
            discovered_local_models = await mgr.list_local_models()
            available_runtime_ids = discover_available_runtime_targets(
                discovered_local_models
            )
            runtime_model_families = discover_runtime_model_families(
                discovered_local_models
            )
            collect_local_trainable_models(
                local_models=discovered_local_models,
                available_runtime_ids=available_runtime_ids,
                runtime_model_families=runtime_model_families,
                result=result,
                seen=seen,
            )
        except Exception as exc:
            logger.warning("Failed to load local model catalog for Academy: %s", exc)

    collect_default_trainable_models(
        available_runtime_ids=available_runtime_ids,
        runtime_model_families=runtime_model_families,
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
            item.label.lower(),
            item.model_id.lower(),
        )
    )
    for index, item in enumerate(result):
        item.recommended = index == 0
    return result


def _canonical_runtime_model_id(model_id: str) -> str:
    normalized = model_id.strip().lower()
    if not normalized:
        return ""
    mapped = _TRAINABLE_MODEL_ALIAS_TO_CANONICAL.get(normalized)
    if mapped:
        return mapped
    # Runtime ONNX artifacts often carry suffixes like:
    #   gemma-3-4b-it-onnx-build-test / gemma-3-4b-it-onnx-int4
    # Canonicalize them back to their base model family to keep adapter
    # compatibility checks stable across ONNX artifact naming variants.
    onnx_marker_index = normalized.find("-onnx")
    if onnx_marker_index > 0:
        base_candidate = normalized[:onnx_marker_index]
        return _TRAINABLE_MODEL_ALIAS_TO_CANONICAL.get(base_candidate, base_candidate)
    return normalized


def _resolve_local_runtime_id(runtime_id: str) -> Optional[str]:
    return _canonical_local_runtime_id(runtime_id)


def _resolve_local_hf_training_path(
    *,
    model_id: str,
    canonical_model_id: str,
    local_models: List[Dict[str, Any]],
) -> Optional[str]:
    requested = model_id.strip()
    requested_path = Path(requested).expanduser()
    if requested and requested_path.exists():
        resolved = requested_path.resolve()
        if _non_trainable_reason_from_model_path(resolved) is None:
            return str(resolved)

    for local_model in local_models:
        local_model_name = str(local_model.get("name") or "").strip()
        if not local_model_name:
            continue
        local_canonical = _canonical_runtime_model_id(local_model_name)
        if local_model_name != requested and local_canonical != canonical_model_id:
            continue
        local_path = _resolve_model_path_from_metadata(local_model)
        if local_path is None:
            continue
        if _non_trainable_reason_from_model_path(local_path) is None:
            return str(local_path.resolve())
    return None


def resolve_effective_training_base_model(
    model_id: str,
    *,
    local_models: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Resolve selected model id to concrete training base (local HF path or repo id)."""
    selected_model_id = model_id.strip()
    if not selected_model_id:
        return ""

    canonical_model_id = _canonical_runtime_model_id(selected_model_id)
    resolved_local_path = _resolve_local_hf_training_path(
        model_id=selected_model_id,
        canonical_model_id=canonical_model_id,
        local_models=local_models or [],
    )
    if resolved_local_path:
        return resolved_local_path

    if _looks_like_hf_repo_id(selected_model_id):
        return selected_model_id

    preferred = _CANONICAL_TO_PREFERRED_TRAINING_BASE.get(canonical_model_id)
    if preferred:
        return preferred
    return selected_model_id
