"""Policy helpers for CODE_GENERATION feedback-loop model selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from venom_core.config import SETTINGS
from venom_core.utils.ollama_tuning import resolve_ollama_tuning_profile

FEEDBACK_LOOP_REQUESTED_ALIAS = "code_generation"
FEEDBACK_LOOP_PRIMARY_MODEL = "qwen2.5-coder:3b"
FEEDBACK_LOOP_FALLBACK_MODELS: tuple[str, ...] = ()
_LEGACY_REQUESTED_ALIAS = "OpenCodeInterpreter-Qwen2.5-7B"


@dataclass(frozen=True)
class FeedbackLoopGuardResult:
    """Resource/profile guard verdict for feedback-loop model activation."""

    allowed: bool
    guard_reason: str | None
    recommendation: str | None


@dataclass(frozen=True)
class FeedbackLoopResolution:
    """Resolved model decision for feedback-loop alias handling."""

    requested_model_alias: str | None
    requested_model_id: str | None
    resolved_model_id: str | None
    resolution_reason: str
    feedback_loop_tier: str
    feedback_loop_ready: bool


@dataclass(frozen=True)
class FeedbackLoopPolicy:
    """Alias policy for OpenCodeInterpreter class in local Ollama stack."""

    requested_alias: str
    primary: str
    fallbacks: tuple[str, ...]

    @property
    def candidates(self) -> tuple[str, ...]:
        return (self.primary, *self.fallbacks)


def feedback_loop_policy(settings: object | None = None) -> FeedbackLoopPolicy:
    """Resolve a configurable role; the legacy alias is not a model requirement."""
    settings = settings if settings is not None else SETTINGS
    primary = (
        str(
            getattr(
                settings, "FEEDBACK_LOOP_PRIMARY_MODEL", FEEDBACK_LOOP_PRIMARY_MODEL
            )
        ).strip()
        or FEEDBACK_LOOP_PRIMARY_MODEL
    )
    configured = str(getattr(settings, "FEEDBACK_LOOP_FALLBACK_MODELS", ""))
    fallbacks = tuple(
        dict.fromkeys(
            item.strip()
            for item in configured.split(",")
            if item.strip() and item.strip().lower() != primary.lower()
        )
    )
    return FeedbackLoopPolicy(
        requested_alias=FEEDBACK_LOOP_REQUESTED_ALIAS,
        primary=primary,
        fallbacks=fallbacks,
    )


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower()


def is_feedback_loop_alias(value: str | None) -> bool:
    return _normalize(value) in {
        _normalize(FEEDBACK_LOOP_REQUESTED_ALIAS),
        _normalize(_LEGACY_REQUESTED_ALIAS),
    }


def classify_feedback_loop_tier(model_id: str | None) -> str:
    normalized = _normalize(model_id)
    policy = feedback_loop_policy()
    if normalized == _normalize(policy.primary):
        return "primary"
    if normalized in {_normalize(item) for item in policy.fallbacks}:
        return "fallback"
    return "not_recommended"


def is_feedback_loop_ready(model_id: str | None) -> bool:
    return classify_feedback_loop_tier(model_id) in {"primary", "fallback"}


def _resolve_feedback_loop_alias(
    *,
    policy: FeedbackLoopPolicy,
    requested: str,
    prefer_feedback_loop_default: bool,
) -> str | None:
    if is_feedback_loop_alias(requested):
        return requested
    if not requested and prefer_feedback_loop_default:
        return policy.requested_alias
    return None


def _non_alias_resolution(requested: str | None) -> FeedbackLoopResolution:
    requested_value = requested or None
    return FeedbackLoopResolution(
        requested_model_alias=None,
        requested_model_id=requested_value,
        resolved_model_id=requested_value,
        resolution_reason="exact",
        feedback_loop_tier=classify_feedback_loop_tier(requested_value),
        feedback_loop_ready=is_feedback_loop_ready(requested_value),
    )


def _exact_primary_resolution(
    *,
    requested_alias: str,
    requested_model_id: str | None,
    resolved_model_id: str,
) -> FeedbackLoopResolution:
    return FeedbackLoopResolution(
        requested_model_alias=requested_alias,
        requested_model_id=requested_model_id,
        resolved_model_id=resolved_model_id,
        resolution_reason="exact",
        feedback_loop_tier="primary",
        feedback_loop_ready=True,
    )


def _not_found_feedback_resolution(
    *,
    requested_alias: str,
    requested_model_id: str | None,
) -> FeedbackLoopResolution:
    return FeedbackLoopResolution(
        requested_model_alias=requested_alias,
        requested_model_id=requested_model_id,
        resolved_model_id=None,
        resolution_reason="not_found",
        feedback_loop_tier="primary",
        feedback_loop_ready=False,
    )


def _fallback_feedback_resolution(
    *,
    requested_alias: str,
    requested_model_id: str | None,
    resolved_model_id: str,
    primary_allowed: bool,
) -> FeedbackLoopResolution:
    return FeedbackLoopResolution(
        requested_model_alias=requested_alias,
        requested_model_id=requested_model_id,
        resolved_model_id=resolved_model_id,
        resolution_reason=("resource_guard" if not primary_allowed else "fallback"),
        feedback_loop_tier="fallback",
        feedback_loop_ready=True,
    )


def resolve_feedback_loop_model(
    *,
    requested_model: str | None,
    available_models: Iterable[str],
    prefer_feedback_loop_default: bool,
    exact_only: bool = False,
    primary_allowed: bool = True,
) -> FeedbackLoopResolution:
    """Resolve requested model (or default) to feedback-loop primary/fallback model."""
    policy = feedback_loop_policy()
    requested = str(requested_model or "").strip()
    requested_model_id = requested or None
    available_map = {
        _normalize(model_id): str(model_id).strip()
        for model_id in available_models
        if str(model_id).strip()
    }

    requested_alias = _resolve_feedback_loop_alias(
        policy=policy,
        requested=requested,
        prefer_feedback_loop_default=prefer_feedback_loop_default,
    )

    # Explicit non-alias request: preserve standard exact behavior.
    if requested and requested_alias is None:
        return _non_alias_resolution(requested)

    if requested_alias is None:
        return _non_alias_resolution(requested_model_id)

    primary_key = _normalize(policy.primary)
    if primary_allowed and primary_key in available_map:
        return _exact_primary_resolution(
            requested_alias=requested_alias,
            requested_model_id=requested_model_id,
            resolved_model_id=available_map[primary_key],
        )

    if exact_only:
        return _not_found_feedback_resolution(
            requested_alias=requested_alias,
            requested_model_id=requested_model_id,
        )

    for fallback in policy.fallbacks:
        key = _normalize(fallback)
        if key in available_map:
            return _fallback_feedback_resolution(
                requested_alias=requested_alias,
                requested_model_id=requested_model_id,
                resolved_model_id=available_map[key],
                primary_allowed=primary_allowed,
            )

    return _not_found_feedback_resolution(
        requested_alias=requested_alias,
        requested_model_id=requested_model_id,
    )


def evaluate_feedback_loop_guard(
    *,
    model_id: str,
    settings,
    ram_total_gb: float | None,
    vram_total_mb: float | None,
) -> FeedbackLoopGuardResult:
    """Apply the configured role budget rather than a model-name whitelist."""
    if _normalize(model_id) != _normalize(feedback_loop_policy(settings).primary):
        return FeedbackLoopGuardResult(True, None, None)
    context = int(resolve_ollama_tuning_profile(settings).get("context_length") or 0)
    maximum = int(getattr(settings, "FEEDBACK_LOOP_MAX_CONTEXT", 32768))
    minimum_ram = float(getattr(settings, "FEEDBACK_LOOP_MIN_RAM_GB", 2.0))
    minimum_vram = float(getattr(settings, "FEEDBACK_LOOP_MIN_VRAM_MB", 0))
    reason = None
    if maximum > 0 and context > maximum:
        reason = "feedback_loop_context_budget_exceeded"
    elif ram_total_gb is not None and ram_total_gb < minimum_ram:
        reason = "feedback_loop_ram_budget_exceeded"
    elif vram_total_mb is not None and vram_total_mb < minimum_vram:
        reason = "feedback_loop_vram_budget_exceeded"
    return FeedbackLoopGuardResult(
        allowed=reason is None,
        guard_reason="resource_guard" if reason else None,
        recommendation=reason,
    )
