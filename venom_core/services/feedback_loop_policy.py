"""Policy helpers for CODE_GENERATION feedback-loop model selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from venom_core.utils.ollama_tuning import resolve_ollama_tuning_profile

FEEDBACK_LOOP_REQUESTED_ALIAS = "OpenCodeInterpreter-Qwen2.5-7B"
FEEDBACK_LOOP_PRIMARY_MODEL = "qwen2.5-coder:7b"
FEEDBACK_LOOP_FALLBACK_MODELS: tuple[str, ...] = (
    "qwen2.5-coder:3b",
    "codestral:latest",
)

_RESOURCE_GUARD_MIN_RAM_GB_7B = 12.0
_RESOURCE_GUARD_MIN_VRAM_MB_7B = 6144.0
_RESOURCE_GUARD_MAX_CONTEXT_7B = 65536


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


def feedback_loop_policy() -> FeedbackLoopPolicy:
    return FeedbackLoopPolicy(
        requested_alias=FEEDBACK_LOOP_REQUESTED_ALIAS,
        primary=FEEDBACK_LOOP_PRIMARY_MODEL,
        fallbacks=FEEDBACK_LOOP_FALLBACK_MODELS,
    )


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower()


def is_feedback_loop_alias(value: str | None) -> bool:
    return _normalize(value) == _normalize(FEEDBACK_LOOP_REQUESTED_ALIAS)


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
    available_map = {
        _normalize(model_id): str(model_id).strip()
        for model_id in available_models
        if str(model_id).strip()
    }

    requested_alias: str | None = None
    if is_feedback_loop_alias(requested):
        requested_alias = policy.requested_alias
    elif not requested and prefer_feedback_loop_default:
        requested_alias = policy.requested_alias

    # Explicit non-alias request: preserve standard exact behavior.
    if requested and requested_alias is None:
        tier = classify_feedback_loop_tier(requested)
        return FeedbackLoopResolution(
            requested_model_alias=None,
            requested_model_id=requested,
            resolved_model_id=requested,
            resolution_reason="exact",
            feedback_loop_tier=tier,
            feedback_loop_ready=is_feedback_loop_ready(requested),
        )

    if requested_alias is None:
        return FeedbackLoopResolution(
            requested_model_alias=None,
            requested_model_id=requested or None,
            resolved_model_id=requested or None,
            resolution_reason="exact",
            feedback_loop_tier=classify_feedback_loop_tier(requested or None),
            feedback_loop_ready=is_feedback_loop_ready(requested or None),
        )

    primary_key = _normalize(policy.primary)
    if primary_allowed and primary_key in available_map:
        return FeedbackLoopResolution(
            requested_model_alias=requested_alias,
            requested_model_id=requested or None,
            resolved_model_id=available_map[primary_key],
            resolution_reason="exact",
            feedback_loop_tier="primary",
            feedback_loop_ready=True,
        )

    if exact_only:
        return FeedbackLoopResolution(
            requested_model_alias=requested_alias,
            requested_model_id=requested or None,
            resolved_model_id=None,
            resolution_reason="not_found",
            feedback_loop_tier="primary",
            feedback_loop_ready=False,
        )

    for fallback in policy.fallbacks:
        key = _normalize(fallback)
        if key in available_map:
            return FeedbackLoopResolution(
                requested_model_alias=requested_alias,
                requested_model_id=requested or None,
                resolved_model_id=available_map[key],
                resolution_reason=(
                    "resource_guard" if not primary_allowed else "fallback"
                ),
                feedback_loop_tier="fallback",
                feedback_loop_ready=True,
            )

    return FeedbackLoopResolution(
        requested_model_alias=requested_alias,
        requested_model_id=requested or None,
        resolved_model_id=None,
        resolution_reason="not_found",
        feedback_loop_tier="primary",
        feedback_loop_ready=False,
    )


def evaluate_feedback_loop_guard(
    *,
    model_id: str,
    settings,
    ram_total_gb: float | None,
    vram_total_mb: float | None,
) -> FeedbackLoopGuardResult:
    """Validate host/resource/profile readiness for 7B feedback-loop model."""
    normalized = _normalize(model_id)
    if normalized != _normalize(FEEDBACK_LOOP_PRIMARY_MODEL):
        return FeedbackLoopGuardResult(
            allowed=True, guard_reason=None, recommendation=None
        )

    resolved_profile = resolve_ollama_tuning_profile(settings)
    profile_name = str(resolved_profile.get("profile") or "").strip().lower()
    context_length = int(resolved_profile.get("context_length") or 0)

    if profile_name == "low-vram-8-12gb":
        return FeedbackLoopGuardResult(
            allowed=False,
            guard_reason="resource_guard",
            recommendation=(
                "Użyj fallbacku qwen2.5-coder:3b lub zmień VENOM_OLLAMA_PROFILE "
                "na balanced-12-24gb"
            ),
        )

    if context_length > _RESOURCE_GUARD_MAX_CONTEXT_7B:
        return FeedbackLoopGuardResult(
            allowed=False,
            guard_reason="resource_guard",
            recommendation=(
                "Zmniejsz OLLAMA_CONTEXT_LENGTH do <=65536 lub użyj fallbacku "
                "qwen2.5-coder:3b"
            ),
        )

    if ram_total_gb is not None and ram_total_gb < _RESOURCE_GUARD_MIN_RAM_GB_7B:
        return FeedbackLoopGuardResult(
            allowed=False,
            guard_reason="resource_guard",
            recommendation=(
                "Niewystarczająca pamięć RAM dla 7B; użyj fallbacku qwen2.5-coder:3b"
            ),
        )

    if (
        vram_total_mb is not None
        and vram_total_mb > 0
        and vram_total_mb < _RESOURCE_GUARD_MIN_VRAM_MB_7B
    ):
        return FeedbackLoopGuardResult(
            allowed=False,
            guard_reason="resource_guard",
            recommendation=(
                "Niewystarczająca pamięć VRAM dla 7B; użyj fallbacku qwen2.5-coder:3b"
            ),
        )

    return FeedbackLoopGuardResult(allowed=True, guard_reason=None, recommendation=None)
