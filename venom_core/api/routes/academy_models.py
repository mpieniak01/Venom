"""Trainable-model catalog helpers for Academy routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import anyio

from venom_core.api.schemas.academy import AdapterInfo, TrainableModelInfo
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def is_model_trainable(model_id: str) -> bool:
    """Return True when model can be used for Academy LoRA/QLoRA training."""
    return get_model_non_trainable_reason(model_id=model_id, provider=None) is None


def get_model_non_trainable_reason(
    model_id: str,
    provider: Optional[str] = None,
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

    blocked_name_markers = ("gpt-", "claude", "gemini")
    if any(marker in model_id_lc for marker in blocked_name_markers):
        return "Model family does not support local Academy LoRA training"

    trainable_patterns = (
        "unsloth/",
        "phi-3",
        "llama-3",
        "mistral",
        "qwen",
        "gemma",
        "test-",
    )
    if any(pattern in model_id_lc for pattern in trainable_patterns):
        return None

    return "Model is not in Academy trainable families list"


def build_model_label(
    model_id: str, provider: str, source: Optional[str] = None
) -> str:
    """Build human-readable model label for Academy UI."""
    source_suffix = f" [{source}]" if source else ""
    return f"{model_id} ({provider}){source_suffix}"


def get_default_trainable_models_catalog() -> List[TrainableModelInfo]:
    """Return default fallback catalog for trainable models."""
    return [
        TrainableModelInfo(
            model_id="unsloth/Phi-3-mini-4k-instruct",
            label="Phi-3 Mini 4K (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=True,
        ),
        TrainableModelInfo(
            model_id="unsloth/Phi-3.5-mini-instruct",
            label="Phi-3.5 Mini (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=False,
        ),
        TrainableModelInfo(
            model_id="unsloth/Llama-3.2-1B-Instruct",
            label="Llama 3.2 1B (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=False,
        ),
        TrainableModelInfo(
            model_id="unsloth/Llama-3.2-3B-Instruct",
            label="Llama 3.2 3B (Unsloth)",
            provider="unsloth",
            trainable=True,
            recommended=False,
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
) -> None:
    """Append model entry when unseen."""
    if not model_id or model_id in seen:
        return
    result.append(
        TrainableModelInfo(
            model_id=model_id,
            label=label,
            provider=provider,
            trainable=reason is None,
            reason_if_not_trainable=reason,
            recommended=(model_id == default_model),
            installed_local=installed_local,
        )
    )
    seen.add(model_id)


async def collect_local_trainable_models(
    mgr: Any,
    default_model: str,
    result: List[TrainableModelInfo],
    seen: set[str],
) -> None:
    """Collect models from model manager catalog."""
    local_models = await mgr.list_local_models()
    for model in local_models:
        model_id = str(model.get("name") or "").strip()
        if not model_id or model_id in seen:
            continue
        provider = str(model.get("provider") or model.get("source") or "unknown")
        source = str(model.get("source") or "")
        reason = get_model_non_trainable_reason(model_id=model_id, provider=provider)
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
        )


def collect_default_trainable_models(
    default_model: str,
    result: List[TrainableModelInfo],
    seen: set[str],
) -> None:
    """Collect fallback defaults for Academy model list."""
    for entry in get_default_trainable_models_catalog():
        if entry.model_id in seen:
            continue
        entry.recommended = entry.model_id == default_model
        result.append(entry)
        seen.add(entry.model_id)


def ensure_default_model_visible(
    default_model: str,
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

    if mgr is not None:
        try:
            await collect_local_trainable_models(
                mgr=mgr,
                default_model=default_model,
                result=result,
                seen=seen,
            )
        except Exception as exc:
            logger.warning("Failed to load local model catalog for Academy: %s", exc)

    collect_default_trainable_models(
        default_model=default_model,
        result=result,
        seen=seen,
    )
    ensure_default_model_visible(
        default_model=default_model,
        result=result,
        seen=seen,
    )
    result.sort(key=lambda item: (not item.recommended, not item.trainable, item.label))
    return result


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
