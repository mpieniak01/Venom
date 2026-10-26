"""Coding roles are configurable and do not require retired model weights."""

from types import SimpleNamespace

import pytest

from venom_core.services import feedback_loop_policy as policy


def test_neutral_and_legacy_aliases_select_the_small_configured_primary():
    assert policy.FEEDBACK_LOOP_PRIMARY_MODEL == "qwen2.5-coder:3b"
    for alias in ["code_generation", " OpenCodeInterpreter-Qwen2.5-7B "]:
        assert policy.is_feedback_loop_alias(alias)
        result = policy.resolve_feedback_loop_model(
            requested_model=alias,
            available_models={"qwen2.5-coder:3b"},
            prefer_feedback_loop_default=False,
        )
        assert result.resolved_model_id == "qwen2.5-coder:3b"
        assert result.feedback_loop_tier == "primary"
        assert result.resolution_reason == "exact"
    assert not policy.is_feedback_loop_alias("qwen2.5-coder:7b")
    assert not policy.is_feedback_loop_ready("codestral:latest")


def test_role_configuration_deduplicates_and_does_not_pin_model_family(monkeypatch):
    monkeypatch.setattr(
        policy.SETTINGS, "FEEDBACK_LOOP_PRIMARY_MODEL", " custom:small "
    )
    monkeypatch.setattr(
        policy.SETTINGS,
        "FEEDBACK_LOOP_FALLBACK_MODELS",
        " alt:small,custom:small, alt:small, ",
    )
    role = policy.feedback_loop_policy()
    assert role.primary == "custom:small"
    assert role.fallbacks == ("alt:small",)
    assert policy.is_feedback_loop_ready(" custom:small ")
    assert policy.classify_feedback_loop_tier("alt:small") == "fallback"
    result = policy.resolve_feedback_loop_model(
        requested_model="custom:small",
        available_models=set(),
        prefer_feedback_loop_default=False,
    )
    assert result.requested_model_alias is None
    assert result.resolved_model_id == "custom:small"


@pytest.mark.parametrize(
    "allowed,exact,available,model,reason",
    [
        (True, False, {"alt:small"}, "alt:small", "fallback"),
        (False, False, {"alt:small"}, "alt:small", "resource_guard"),
        (True, True, {"alt:small"}, None, "not_found"),
        (True, False, set(), None, "not_found"),
    ],
)
def test_configured_fallback_or_explicit_failure(
    monkeypatch, allowed, exact, available, model, reason
):
    monkeypatch.setattr(policy.SETTINGS, "FEEDBACK_LOOP_PRIMARY_MODEL", "custom:small")
    monkeypatch.setattr(policy.SETTINGS, "FEEDBACK_LOOP_FALLBACK_MODELS", "alt:small")
    result = policy.resolve_feedback_loop_model(
        requested_model="code_generation",
        available_models=available,
        prefer_feedback_loop_default=False,
        primary_allowed=allowed,
        exact_only=exact,
    )
    assert result.resolved_model_id == model
    assert result.resolution_reason == reason
    assert result.feedback_loop_ready is (model is not None)


def test_missing_selection_and_preferred_role():
    result = policy.resolve_feedback_loop_model(
        requested_model=None,
        available_models=set(),
        prefer_feedback_loop_default=False,
    )
    assert result.resolved_model_id is None and not result.feedback_loop_ready
    result = policy.resolve_feedback_loop_model(
        requested_model=None,
        available_models={"qwen2.5-coder:3b"},
        prefer_feedback_loop_default=True,
    )
    assert result.resolved_model_id == "qwen2.5-coder:3b"


def test_blank_primary_keeps_default():
    assert (
        policy.feedback_loop_policy(
            SimpleNamespace(FEEDBACK_LOOP_PRIMARY_MODEL=" ")
        ).primary
        == "qwen2.5-coder:3b"
    )


@pytest.mark.parametrize(
    "context,ram,vram,minimum_ram,minimum_vram,maximum,reason",
    [
        (16384, 8, 4096, 2, 0, 32768, None),
        (65536, 16, 8192, 2, 0, 32768, "context"),
        (16384, 1, 8192, 2, 0, 32768, "ram"),
        (16384, 16, 1024, 2, 2048, 32768, "vram"),
        (65536, None, None, 2, 2048, 0, None),
    ],
)
def test_resource_budget_is_explicit_and_small_model_allowed(
    context, ram, vram, minimum_ram, minimum_vram, maximum, reason
):
    settings = SimpleNamespace(
        VENOM_OLLAMA_PROFILE="low-vram-8-12gb",
        OLLAMA_CONTEXT_LENGTH=context,
        FEEDBACK_LOOP_MIN_RAM_GB=minimum_ram,
        FEEDBACK_LOOP_MIN_VRAM_MB=minimum_vram,
        FEEDBACK_LOOP_MAX_CONTEXT=maximum,
    )
    result = policy.evaluate_feedback_loop_guard(
        model_id="qwen2.5-coder:3b",
        settings=settings,
        ram_total_gb=ram,
        vram_total_mb=vram,
    )
    assert result.allowed is (reason is None)
    if reason:
        assert reason in result.reason_code
        assert result.recommendation and " " in result.recommendation
        assert result.reason_code not in result.recommendation
    else:
        assert result.guard_reason is None and result.recommendation is None
    result = policy.evaluate_feedback_loop_guard(
        model_id="unrelated:model",
        settings=settings,
        ram_total_gb=0,
        vram_total_mb=0,
    )
    assert result.allowed


def test_policy_budget_default_values():
    result = policy.evaluate_feedback_loop_guard(
        model_id="qwen2.5-coder:3b",
        settings=SimpleNamespace(VENOM_OLLAMA_PROFILE="low-vram-8-12gb"),
        ram_total_gb=8,
        vram_total_mb=4096,
    )
    assert result.allowed
