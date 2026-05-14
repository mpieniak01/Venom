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
    "precision": "unsupported",
    "quantization_backend": "unsupported",
    "device_target": "unsupported",
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
    max_new_tokens: int,
    enable_thinking: bool,
    image_token_budget: int,
    reasoning_summary_enabled: bool,
    emotion_detection_enabled: bool,
    emotion_response_style_enabled: bool,
    cache_implementation: Optional[str],
) -> MultiRuntimeProfile:
    """Build a MultiRuntimeProfile from flat daemon status fields.

    Accepts the same field names as DaemonParamsInfo so callers can use
    ``**daemon_status.params.model_dump()`` after expanding model fields.
    """
    return MultiRuntimeProfile(
        model_id=target_model,
        assistant_model_id=assistant_model,
        max_new_tokens=max_new_tokens,
        enable_thinking=enable_thinking,
        image_token_budget=image_token_budget,
        reasoning_summary_enabled=reasoning_summary_enabled,
        emotion_detection_enabled=emotion_detection_enabled,
        emotion_response_style_enabled=emotion_response_style_enabled,
        cache_implementation=cache_implementation,
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
            reason, detail = _unsupported_reason(field, value)
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


def _unsupported_reason(field: str, value: Any) -> tuple[str, str]:
    """Return (rejection_reason, detail) for an unsupported field."""
    if field == "quantization_backend":
        return (
            "quantization_backend_unavailable",
            "bitsandbytes is not installed; quantization_backend cannot be activated",
        )
    if field == "precision":
        return (
            "precision_not_supported_for_runtime",
            f"precision='{value}' is accepted in the contract but the loader "
            "uses dtype='auto'; explicit precision is not yet applied",
        )
    if field == "device_target":
        return (
            "unsupported_field",
            "device_target is declared in the profile contract but runtime "
            "device selection is not yet active",
        )
    return (
        "unsupported_field",
        f"'{field}' is not yet supported in this runtime version",
    )


def _semantic_check(field: str, value: Any) -> Optional[tuple[str, str]]:
    """Return (rejection_reason, detail) for semantic violations, or None if OK."""
    if field == "cache_implementation" and value is not None:
        allowed = [v for v in SUPPORTED_OPTIONS.cache_implementation if v is not None]
        if value not in allowed:
            return (
                "unsupported_combination",
                f"cache_implementation='{value}' is not in supported set: {allowed}",
            )
    return None


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
