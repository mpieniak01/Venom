"""Service layer for multi_runtime execution profile.

Owns three responsibilities:
1. The canonical apply-mode matrix — which profile fields require live/reload/restart.
2. Validation — classifies a partial update into accepted / rejected buckets.
3. Profile assembly — builds a MultiRuntimeProfile from daemon status or defaults.

Deliberately does NOT import anything from services.gemma4_audio_runtime so that
this layer can be tested and used independently of whether the daemon is running.
"""

from __future__ import annotations

from typing import Any, Optional

from venom_core.api.schemas.multi_runtime_profile import (
    ApplyMode,
    MultiRuntimeApplyMatrix,
    MultiRuntimeFieldRejection,
    MultiRuntimeProfile,
    MultiRuntimeProfileResponse,
    MultiRuntimeProfileUpdateRequest,
    MultiRuntimeProfileUpdateResponse,
    MultiRuntimeSupportedOptions,
)

# ---------------------------------------------------------------------------
# Apply-mode matrix (single source of truth)
# ---------------------------------------------------------------------------

APPLY_MATRIX: dict[str, ApplyMode] = {
    "model_id": "hard_restart",
    "assistant_model_id": "hard_restart",
    "cache_implementation": "soft_reload",
    "max_new_tokens": "live",
    "image_token_budget": "live",
    "enable_thinking": "live",
    "reasoning_summary_enabled": "live",
    "emotion_detection_enabled": "live",
    "emotion_response_style_enabled": "live",
    "execution_mode": "live",
    "image_strategy": "live",
    "retrieval_mode": "live",
    "audio_output_mode": "live",
    "assistant_mode": "live",
    "economy_mode": "live",
    "precision": "soft_reload",
    "quantization_backend": "soft_reload",
    "device_target": "soft_reload",
}

# Priority order for resolving most-restrictive apply_mode.
# Lower index = higher priority (overrides less-restrictive modes).
_MODE_PRIORITY: dict[ApplyMode, int] = {
    "hard_restart": 0,
    "soft_reload": 1,
    "live": 2,
    "unsupported": 3,
}

SUPPORTED_OPTIONS = MultiRuntimeSupportedOptions()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def apply_mode_for_field(field: str) -> ApplyMode:
    """Return the apply_mode required to change a named profile field."""
    return APPLY_MATRIX.get(field, "unsupported")


def required_apply_mode(fields: list[str]) -> ApplyMode:
    """Return the most restrictive apply_mode across all changed fields.

    'hard_restart' beats 'soft_reload' beats 'live'. 'unsupported' is treated
    as the least important: if any field is accepted (live/soft_reload/hard_restart),
    the overall required mode is driven by the accepted fields only.
    """
    accepted_modes = [
        APPLY_MATRIX[f] for f in fields if APPLY_MATRIX.get(f) != "unsupported"
    ]
    if not accepted_modes:
        return "unsupported"
    return min(accepted_modes, key=lambda m: _MODE_PRIORITY[m])


# ---------------------------------------------------------------------------
# Profile assembly
# ---------------------------------------------------------------------------


def build_default_profile(model_id: str) -> MultiRuntimeProfile:
    """Return a minimal default profile for the given model_id."""
    return MultiRuntimeProfile(model_id=model_id)


def build_profile_from_daemon_params(
    *,
    target_model: str,
    assistant_model: Optional[str],
    daemon_params: dict[str, Any],
) -> MultiRuntimeProfile:
    """Build a MultiRuntimeProfile from flat daemon status fields.

    Accepts the same field names as DaemonParamsInfo so callers can use
    ``**daemon_status.params.model_dump()`` after expanding model fields.
    """

    def _str_or_default(value: Any, default: str) -> str:
        if value is None:
            return default
        text = str(value).strip()
        return text or default

    return MultiRuntimeProfile(
        model_id=target_model,
        assistant_model_id=assistant_model,
        max_new_tokens=int(daemon_params.get("max_new_tokens", 128)),
        enable_thinking=bool(daemon_params.get("enable_thinking", False)),
        image_token_budget=int(daemon_params.get("image_token_budget", 280)),
        reasoning_summary_enabled=bool(
            daemon_params.get("reasoning_summary_enabled", False)
        ),
        emotion_detection_enabled=bool(
            daemon_params.get("emotion_detection_enabled", False)
        ),
        emotion_response_style_enabled=bool(
            daemon_params.get("emotion_response_style_enabled", False)
        ),
        cache_implementation=daemon_params.get("cache_implementation"),
        execution_mode=str(daemon_params.get("execution_mode", "balanced")),
        image_strategy=str(daemon_params.get("image_strategy", "vlm_only")),
        retrieval_mode=str(daemon_params.get("retrieval_mode", "off")),
        audio_output_mode=str(daemon_params.get("audio_output_mode", "off")),
        assistant_mode=str(daemon_params.get("assistant_mode", "off")),
        economy_mode=str(daemon_params.get("economy_mode", "off")),
        precision=str(daemon_params.get("precision", "auto")),
        quantization_backend=daemon_params.get("quantization_backend"),
        device_target=_str_or_default(daemon_params.get("device_target"), "auto"),
    )


def build_profile_response(
    profile: MultiRuntimeProfile,
    *,
    daemon_reachable: bool = False,
) -> MultiRuntimeProfileResponse:
    """Wrap a profile in the full API response envelope."""
    return MultiRuntimeProfileResponse(
        profile=profile,
        apply_matrix=MultiRuntimeApplyMatrix(),
        supported_options=SUPPORTED_OPTIONS,
        daemon_reachable=daemon_reachable,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _reject(
    field: str,
    value: Any,
    reason: str,
    detail: str = "",
) -> MultiRuntimeFieldRejection:
    return MultiRuntimeFieldRejection(
        field=field,
        value=value,
        reason=reason,  # type: ignore[arg-type]
        detail=detail,
    )


def validate_profile_update(
    request: MultiRuntimeProfileUpdateRequest,
) -> MultiRuntimeProfileUpdateResponse:
    """Classify each field in a partial update into accepted or rejected.

    Rules:
    - Fields with apply_mode 'unsupported' are always rejected.
    - Fields not present in the request (None) are skipped.
    - Value-range validation is already enforced by Pydantic; this layer
      handles semantic rejections (unsupported backend, unsupported combination).
    """
    accepted: dict[str, Any] = {}
    rejected: list[MultiRuntimeFieldRejection] = []

    update_dict = request.model_dump(exclude_none=True)

    for field, value in update_dict.items():
        mode = apply_mode_for_field(field)

        if mode == "unsupported":
            reason, detail = _unsupported_reason(field)
            rejected.append(_reject(field, value, reason, detail))
            continue

        # Semantic validation for accepted fields
        semantic_rejection = _semantic_check(field, value)
        if semantic_rejection:
            rejected.append(_reject(field, value, *semantic_rejection))
            continue

        accepted[field] = value

    req_mode = required_apply_mode(list(accepted.keys()))

    return MultiRuntimeProfileUpdateResponse(
        accepted=accepted,
        rejected=rejected,
        required_apply_mode=req_mode,
        applied=False,
        message=_summary_message(accepted, rejected, req_mode),
    )


def _unsupported_reason(field: str) -> tuple[str, str]:
    """Return (rejection_reason, detail) for an unsupported field."""
    return (
        "unsupported_field",
        f"'{field}' is not yet supported in this runtime version",
    )


def _semantic_check(field: str, value: Any) -> Optional[tuple[str, str]]:
    """Return (rejection_reason, detail) for semantic violations, or None if OK."""
    validators = {
        "cache_implementation": _validate_cache_implementation,
        "precision": _validate_precision,
        "quantization_backend": _validate_quantization_backend,
        "device_target": _validate_device_target,
    }
    validator = validators.get(field)
    if validator is None:
        return None
    return validator(value)


def _validate_cache_implementation(value: Any) -> Optional[tuple[str, str]]:
    if value is None:
        return None
    allowed = [v for v in SUPPORTED_OPTIONS.cache_implementation if v is not None]
    if value in allowed:
        return None
    return (
        "unsupported_combination",
        f"cache_implementation='{value}' is not in supported set: {allowed}",
    )


def _validate_precision(value: Any) -> Optional[tuple[str, str]]:
    normalized = str(value or "auto").lower().strip()
    allowed = {"auto", "float16", "bfloat16", "float32", "int4", "int8"}
    if normalized in allowed:
        return None
    return (
        "value_out_of_range",
        f"precision='{value}' is not in supported set: {sorted(allowed)}",
    )


def _validate_quantization_backend(value: Any) -> Optional[tuple[str, str]]:
    normalized = None if value is None else str(value).lower().strip()
    if normalized not in {None, "bitsandbytes"}:
        return (
            "unsupported_combination",
            "quantization_backend must be either None or 'bitsandbytes'",
        )
    if normalized != "bitsandbytes":
        return None
    try:
        import bitsandbytes  # noqa: F401
    except ImportError:
        return (
            "quantization_backend_unavailable",
            "bitsandbytes is not installed; quantization_backend cannot be activated",
        )
    return None


def _validate_device_target(value: Any) -> Optional[tuple[str, str]]:
    normalized = str(value or "auto").lower().strip()
    allowed = {"auto", "cpu", "cuda"}
    if normalized in allowed:
        return None
    return (
        "value_out_of_range",
        f"device_target='{value}' is not in supported set: {sorted(allowed)}",
    )


def _summary_message(
    accepted: dict[str, Any],
    rejected: list[MultiRuntimeFieldRejection],
    mode: ApplyMode,
) -> str:
    if not accepted and rejected:
        return f"All {len(rejected)} field(s) rejected; no changes will be applied."
    parts: list[str] = []
    if accepted:
        parts.append(f"{len(accepted)} field(s) accepted (requires {mode})")
    if rejected:
        parts.append(f"{len(rejected)} field(s) rejected")
    return "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# System-profile guard (ensures no collision with VENOM_RUNTIME_PROFILE)
# ---------------------------------------------------------------------------


SYSTEM_RUNTIME_PROFILES: frozenset[str] = frozenset({"full", "light", "llm_off"})


def is_system_runtime_profile(name: str) -> bool:
    """Return True when the name belongs to the Venom system profile (full|light|llm_off).

    These must never be confused with multi_runtime_profile identifiers.
    """
    return str(name or "").strip().lower() in SYSTEM_RUNTIME_PROFILES


def assert_not_system_profile(name: str) -> None:
    """Raise ValueError if name collides with a system profile identifier."""
    if is_system_runtime_profile(name):
        raise ValueError(
            f"'{name}' is a Venom system runtime profile (full|light|llm_off), "
            "not a multi_runtime_profile identifier. Use a distinct profile_id."
        )
