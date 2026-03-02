from types import SimpleNamespace

from venom_core.services.feedback_loop_policy import (
    FEEDBACK_LOOP_PRIMARY_MODEL,
    FEEDBACK_LOOP_REQUESTED_ALIAS,
    classify_feedback_loop_tier,
    evaluate_feedback_loop_guard,
    resolve_feedback_loop_model,
)


def test_resolve_feedback_loop_alias_exact_primary() -> None:
    resolved = resolve_feedback_loop_model(
        requested_model=FEEDBACK_LOOP_REQUESTED_ALIAS,
        available_models={FEEDBACK_LOOP_PRIMARY_MODEL, "qwen2.5-coder:3b"},
        prefer_feedback_loop_default=False,
        exact_only=False,
        primary_allowed=True,
    )
    assert resolved.resolved_model_id == FEEDBACK_LOOP_PRIMARY_MODEL
    assert resolved.resolution_reason == "exact"
    assert resolved.feedback_loop_tier == "primary"
    assert resolved.feedback_loop_ready is True


def test_resolve_feedback_loop_alias_fallback_when_primary_missing() -> None:
    resolved = resolve_feedback_loop_model(
        requested_model=FEEDBACK_LOOP_REQUESTED_ALIAS,
        available_models={"qwen2.5-coder:3b"},
        prefer_feedback_loop_default=False,
        exact_only=False,
        primary_allowed=True,
    )
    assert resolved.resolved_model_id == "qwen2.5-coder:3b"
    assert resolved.resolution_reason == "fallback"
    assert resolved.feedback_loop_tier == "fallback"
    assert resolved.feedback_loop_ready is True


def test_resolve_feedback_loop_alias_resource_guard_fallback() -> None:
    resolved = resolve_feedback_loop_model(
        requested_model=FEEDBACK_LOOP_REQUESTED_ALIAS,
        available_models={"qwen2.5-coder:3b"},
        prefer_feedback_loop_default=False,
        exact_only=False,
        primary_allowed=False,
    )
    assert resolved.resolved_model_id == "qwen2.5-coder:3b"
    assert resolved.resolution_reason == "resource_guard"


def test_evaluate_feedback_loop_guard_blocks_low_vram_profile() -> None:
    settings = SimpleNamespace(
        VENOM_OLLAMA_PROFILE="low-vram-8-12gb",
        OLLAMA_CONTEXT_LENGTH=0,
        OLLAMA_NUM_PARALLEL=0,
        OLLAMA_MAX_QUEUE=0,
        OLLAMA_KV_CACHE_TYPE="",
        OLLAMA_FLASH_ATTENTION=True,
        LLM_KEEP_ALIVE="30m",
    )
    guard = evaluate_feedback_loop_guard(
        model_id=FEEDBACK_LOOP_PRIMARY_MODEL,
        settings=settings,
        ram_total_gb=16.0,
        vram_total_mb=8192.0,
    )
    assert guard.allowed is False
    assert guard.guard_reason == "resource_guard"
    assert "qwen2.5-coder:3b" in str(guard.recommendation)


def test_classify_feedback_loop_tier_values() -> None:
    assert classify_feedback_loop_tier("qwen2.5-coder:7b") == "primary"
    assert classify_feedback_loop_tier("qwen2.5-coder:3b") == "fallback"
    assert classify_feedback_loop_tier("phi3:mini") == "not_recommended"
