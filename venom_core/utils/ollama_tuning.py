"""Deterministyczne profile strojenia Ollama dla Venom (single-user local)."""

from __future__ import annotations

from typing import Any, Dict

PROFILE_BALANCED = "balanced-12-24gb"
PROFILE_LOW_VRAM = "low-vram-8-12gb"
PROFILE_MAX_CONTEXT = "max-context-24gb-plus"

_PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    PROFILE_BALANCED: {
        "context_length": 32768,
        "num_parallel": 2,
        "max_queue": 256,
        "flash_attention": True,
        "kv_cache_type": "q8_0",
        "keep_alive": "30m",
    },
    PROFILE_LOW_VRAM: {
        "context_length": 16384,
        "num_parallel": 1,
        "max_queue": 128,
        "flash_attention": True,
        "kv_cache_type": "q4_0",
        "keep_alive": "20m",
    },
    PROFILE_MAX_CONTEXT: {
        "context_length": 65536,
        "num_parallel": 1,
        "max_queue": 128,
        "flash_attention": True,
        "kv_cache_type": "q8_0",
        "keep_alive": "45m",
    },
}


def _normalize_profile_name(profile_name: str | None) -> str:
    candidate = (profile_name or "").strip().lower()
    if candidate in _PROFILE_DEFAULTS:
        return candidate
    return PROFILE_BALANCED


def resolve_ollama_tuning_profile(settings) -> Dict[str, Any]:
    """
    Zwraca skuteczny profil strojenia Ollama.

    Priorytet:
    1) jawne env (OLLAMA_*) jeśli ustawione,
    2) wartości domyślne wynikające z VENOM_OLLAMA_PROFILE.
    """
    profile_name = _normalize_profile_name(
        getattr(settings, "VENOM_OLLAMA_PROFILE", "")
    )
    profile = dict(_PROFILE_DEFAULTS[profile_name])

    context_override = int(getattr(settings, "OLLAMA_CONTEXT_LENGTH", 0) or 0)
    parallel_override = int(getattr(settings, "OLLAMA_NUM_PARALLEL", 0) or 0)
    queue_override = int(getattr(settings, "OLLAMA_MAX_QUEUE", 0) or 0)
    kv_override = str(getattr(settings, "OLLAMA_KV_CACHE_TYPE", "") or "").strip()
    keep_alive_override = str(getattr(settings, "LLM_KEEP_ALIVE", "") or "").strip()
    flash_override = getattr(settings, "OLLAMA_FLASH_ATTENTION", None)

    if context_override > 0:
        profile["context_length"] = context_override
    if parallel_override > 0:
        profile["num_parallel"] = parallel_override
    if queue_override > 0:
        profile["max_queue"] = queue_override
    if kv_override:
        profile["kv_cache_type"] = kv_override
    if keep_alive_override:
        profile["keep_alive"] = keep_alive_override
    if flash_override is not None:
        profile["flash_attention"] = bool(flash_override)

    profile["profile"] = profile_name
    return profile


def build_ollama_runtime_options(settings) -> Dict[str, Any]:
    """Buduje blok `options` przekazywany do API Ollama."""
    resolved = resolve_ollama_tuning_profile(settings)
    return {
        "num_ctx": resolved["context_length"],
        "num_parallel": resolved["num_parallel"],
        "num_queue": resolved["max_queue"],
        "flash_attention": resolved["flash_attention"],
        "kv_cache_type": resolved["kv_cache_type"],
    }
