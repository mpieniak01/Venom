"""Model discovery helpers for the multi_runtime daemon.

Canonical replacement for venom_core.services.gemma4_audio_models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from venom_core.config import SETTINGS

_MULTI_RUNTIME_TARGET_MODEL_CANDIDATES: tuple[str, ...] = (
    "google/gemma-4-E2B-it",
    "google/gemma-4-E4B-it",
)
_MULTI_RUNTIME_ASSISTANT_MODEL_CANDIDATES: tuple[str, ...] = (
    "google/gemma-4-E2B-it-assistant",
)


def _resolve_cache_root(settings_obj: Any | None = None) -> Path:
    settings = settings_obj or SETTINGS
    cache_dir = Path(
        str(
            getattr(settings, "GEMMA4_AUDIO_CACHE_DIR", "models_cache/hf")
            or "models_cache/hf"
        )
    ).expanduser()
    if cache_dir.is_absolute():
        return cache_dir.resolve()
    repo_root = Path(str(getattr(settings, "REPO_ROOT", ".") or ".")).expanduser()
    if not repo_root.is_absolute():
        repo_root = repo_root.resolve()
    return (repo_root / cache_dir).resolve()


def _resolve_repo_snapshot_dir(
    model_id: str, *, settings_obj: Any | None = None
) -> Path:
    normalized = str(model_id or "").strip()
    if "/" not in normalized:
        return Path("__invalid__")
    owner, name = normalized.split("/", 1)
    model_store = f"models--{owner}--{name}".replace("/", "--")
    return _resolve_cache_root(settings_obj=settings_obj) / model_store / "snapshots"


def multi_runtime_model_has_snapshot(
    model_id: str,
    *,
    settings_obj: Any | None = None,
) -> bool:
    """Return True when the model has at least one complete snapshot in the HF cache."""
    snapshots_dir = _resolve_repo_snapshot_dir(model_id, settings_obj=settings_obj)
    if not snapshots_dir.exists() or not snapshots_dir.is_dir():
        return False
    snapshots = sorted(
        (path for path in snapshots_dir.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for snapshot in snapshots:
        if (snapshot / "config.json").exists():
            return True
    return False


def multi_runtime_available_models(
    *,
    role: str = "target",
    settings_obj: Any | None = None,
) -> list[str]:
    """Return model IDs available in the local HF cache for the given role."""
    role_normalized = str(role or "").strip().lower()
    if role_normalized == "assistant":
        candidates = _MULTI_RUNTIME_ASSISTANT_MODEL_CANDIDATES
    else:
        candidates = _MULTI_RUNTIME_TARGET_MODEL_CANDIDATES

    return [
        model_id
        for model_id in candidates
        if multi_runtime_model_has_snapshot(model_id, settings_obj=settings_obj)
    ]
