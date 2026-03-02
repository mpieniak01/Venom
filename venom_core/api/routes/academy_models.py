"""Trainable-model catalog helpers for Academy routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import anyio

from venom_core.api.schemas.academy import AdapterInfo, TrainableModelInfo
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
    if candidate.startswith(("http://", "https://")):
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
    model_type = str(model_metadata.get("type") or "").lower()
    runtime = str(model_metadata.get("runtime") or "").lower()
    source = str(model_metadata.get("source") or "").lower()

    if provider_lc == "onnx" or runtime == "onnx" or model_type == "onnx":
        return "ONNX runtime artifacts are inference-only in Academy LoRA pipeline"

    if provider_lc == "ollama" or source == "ollama":
        return (
            "Ollama runtime models are inference-focused in this pipeline; "
            "select a HuggingFace/Unsloth base model for Academy training"
        )

    model_path = _resolve_model_path_from_metadata(model_metadata)
    if model_path is None:
        if _looks_like_hf_repo_id(model_id):
            return None
        return "Model capability cannot be verified for Academy LoRA training"

    if model_path.is_file():
        suffix = model_path.suffix.lower()
        if suffix in {".onnx", ".gguf"}:
            return f"Model artifact '{model_path.name}' is inference-only and not LoRA-trainable"
        return "Model file artifact is not a supported HuggingFace training layout"

    if not model_path.is_dir():
        return "Model path does not point to a valid local model directory"

    config_file = model_path / "config.json"
    if not config_file.exists():
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
    installed_local: bool,
    model_metadata: Optional[Dict[str, Any]] = None,
) -> str:
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


def classify_model_cost_tier(*, source_type: str, provider: str, model_id: str) -> str:
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
    source_type: str,
    cost_tier: str,
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
    compatibility: Dict[str, bool] = {
        runtime_id: False for runtime_id in available_runtime_ids
    }
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

    # For HF/Unsloth trainable families, vLLM is the primary local inference target.
    if not preferred and provider_lc in {
        "unsloth",
        "huggingface",
        "hf",
        "config",
        "unknown",
    }:
        preferred.add("vllm")

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
    source_type: Optional[str] = None,
    cost_tier: Optional[str] = None,
    available_runtime_ids: Optional[List[str]] = None,
    model_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Append model entry when unseen."""
    if not model_id or model_id in seen:
        return
    resolved_source_type = source_type or classify_model_source_type(
        provider=provider,
        installed_local=installed_local,
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


async def list_trainable_models(mgr: Any) -> List[TrainableModelInfo]:
    """Build sorted list of Academy trainable models."""
    from venom_core.config import SETTINGS

    result: List[TrainableModelInfo] = []
    seen: set[str] = set()
    default_model_raw = getattr(SETTINGS, "ACADEMY_DEFAULT_BASE_MODEL", "")
    default_model = (
        default_model_raw.strip() if isinstance(default_model_raw, str) else ""
    )
    local_models: List[Dict[str, Any]] = []
    available_runtime_ids: List[str] = []

    if mgr is not None:
        try:
            local_models = await mgr.list_local_models()
            available_runtime_ids = discover_available_runtime_targets(local_models)
            collect_local_trainable_models(
                local_models=local_models,
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


def _resolve_adapter_base_model(*, adapter_dir: Path, default_model: str) -> str:
    metadata = _load_adapter_metadata(adapter_dir)
    base_model = str(metadata.get("base_model") or "").strip()
    if base_model:
        return base_model
    return default_model


def _resolve_local_runtime_id(runtime_id: str) -> Optional[str]:
    return _canonical_local_runtime_id(runtime_id)


async def validate_adapter_runtime_compatibility(
    *,
    mgr: Any,
    adapter_id: str,
    runtime_id: str,
) -> None:
    """Validate that adapter base model can run on selected inference runtime."""
    from venom_core.config import SETTINGS

    runtime_normalized = runtime_id.strip().lower()
    if not runtime_normalized:
        return
    runtime_local_id = _resolve_local_runtime_id(runtime_normalized)
    if runtime_local_id is None:
        raise ValueError(
            "Academy adapter supports only local runtimes (ollama/vllm/onnx); "
            f"got '{runtime_id}'."
        )

    models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR).resolve()
    adapter_dir = (models_dir / adapter_id).resolve()
    base_model = _resolve_adapter_base_model(
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

    runtime_compatibility = trainable_info.runtime_compatibility or {}
    if not runtime_compatibility:
        return
    if runtime_compatibility.get(runtime_local_id):
        return

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


def activate_adapter(mgr: Any, adapter_id: str) -> Dict[str, Any]:
    """Activate adapter in model manager, returning API payload."""
    from venom_core.config import SETTINGS

    models_dir = Path(SETTINGS.ACADEMY_MODELS_DIR).resolve()
    adapter_path = (models_dir / adapter_id / "adapter").resolve()

    if not adapter_path.exists():
        raise FileNotFoundError("Adapter not found")

    success = mgr.activate_adapter(
        adapter_id=adapter_id, adapter_path=str(adapter_path)
    )
    if not success:
        raise RuntimeError(f"Failed to activate adapter {adapter_id}")

    logger.info("Activated adapter: %s", adapter_id)
    return {
        "success": True,
        "message": f"Adapter {adapter_id} activated successfully",
        "adapter_id": adapter_id,
        "adapter_path": str(adapter_path),
    }


def deactivate_adapter(mgr: Any) -> Dict[str, Any]:
    """Deactivate active adapter in model manager."""
    success = mgr.deactivate_adapter()
    if not success:
        return {
            "success": False,
            "message": "No active adapter to deactivate",
        }

    logger.info("Adapter deactivated - rolled back to base model")
    return {
        "success": True,
        "message": "Adapter deactivated successfully - using base model",
    }
