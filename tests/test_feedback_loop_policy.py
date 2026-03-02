from types import SimpleNamespace

from venom_core.services.feedback_loop_policy import (
    FEEDBACK_LOOP_FALLBACK_MODELS,
    FEEDBACK_LOOP_PRIMARY_MODEL,
    FEEDBACK_LOOP_REQUESTED_ALIAS,
    classify_feedback_loop_tier,
    evaluate_feedback_loop_guard,
    feedback_loop_policy,
    is_feedback_loop_alias,
    is_feedback_loop_ready,
    resolve_feedback_loop_model,
)


def test_is_feedback_loop_alias_matches_case_and_whitespace() -> None:
    assert is_feedback_loop_alias("  opencodeinterpreter-qwen2.5-7b  ") is True
    assert is_feedback_loop_alias("qwen2.5-coder:7b") is False


def test_is_feedback_loop_ready_for_primary_fallback_and_other() -> None:
    assert is_feedback_loop_ready("qwen2.5-coder:7b") is True
    assert is_feedback_loop_ready("qwen2.5-coder:3b") is True
    assert is_feedback_loop_ready("phi3:mini") is False


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


def test_resolve_feedback_loop_alias_exact_only_not_found_sets_null_resolved() -> None:
    resolved = resolve_feedback_loop_model(
        requested_model=FEEDBACK_LOOP_REQUESTED_ALIAS,
        available_models={"qwen2.5-coder:3b"},
        prefer_feedback_loop_default=False,
        exact_only=True,
        primary_allowed=True,
    )
    assert resolved.resolved_model_id is None
    assert resolved.resolution_reason == "not_found"
    assert resolved.feedback_loop_ready is False


def test_resolve_feedback_loop_default_alias_when_preferred() -> None:
    resolved = resolve_feedback_loop_model(
        requested_model=None,
        available_models={FEEDBACK_LOOP_PRIMARY_MODEL},
        prefer_feedback_loop_default=True,
        exact_only=False,
        primary_allowed=True,
    )
    assert resolved.requested_model_alias == FEEDBACK_LOOP_REQUESTED_ALIAS
    assert resolved.resolved_model_id == FEEDBACK_LOOP_PRIMARY_MODEL
    assert resolved.resolution_reason == "exact"


def test_resolve_feedback_loop_preserves_non_alias_request() -> None:
    resolved = resolve_feedback_loop_model(
        requested_model="qwen2.5-coder:3b",
        available_models=set(),
        prefer_feedback_loop_default=True,
        exact_only=False,
        primary_allowed=False,
    )
    assert resolved.requested_model_alias is None
    assert resolved.requested_model_id == "qwen2.5-coder:3b"
    assert resolved.resolved_model_id == "qwen2.5-coder:3b"
    assert resolved.resolution_reason == "exact"
    assert resolved.feedback_loop_tier == "fallback"
    assert resolved.feedback_loop_ready is True


def test_resolve_feedback_loop_without_request_and_without_preference() -> None:
    resolved = resolve_feedback_loop_model(
        requested_model=None,
        available_models={"qwen2.5-coder:7b"},
        prefer_feedback_loop_default=False,
        exact_only=False,
        primary_allowed=True,
    )
    assert resolved.requested_model_alias is None
    assert resolved.requested_model_id is None
    assert resolved.resolved_model_id is None
    assert resolved.resolution_reason == "exact"
    assert resolved.feedback_loop_tier == "not_recommended"
    assert resolved.feedback_loop_ready is False


def test_resolve_feedback_loop_alias_not_found_when_no_candidates_available() -> None:
    resolved = resolve_feedback_loop_model(
        requested_model=FEEDBACK_LOOP_REQUESTED_ALIAS,
        available_models={"phi3:mini"},
        prefer_feedback_loop_default=False,
        exact_only=False,
        primary_allowed=True,
    )
    assert resolved.requested_model_alias == FEEDBACK_LOOP_REQUESTED_ALIAS
    assert resolved.resolved_model_id is None
    assert resolved.resolution_reason == "not_found"
    assert resolved.feedback_loop_tier == "primary"
    assert resolved.feedback_loop_ready is False


def test_resolve_feedback_loop_default_alias_resource_guard_uses_fallback() -> None:
    resolved = resolve_feedback_loop_model(
        requested_model=None,
        available_models={"qwen2.5-coder:3b"},
        prefer_feedback_loop_default=True,
        exact_only=False,
        primary_allowed=False,
    )
    assert resolved.requested_model_alias == FEEDBACK_LOOP_REQUESTED_ALIAS
    assert resolved.resolved_model_id == "qwen2.5-coder:3b"
    assert resolved.resolution_reason == "resource_guard"
    assert resolved.feedback_loop_tier == "fallback"
    assert resolved.feedback_loop_ready is True


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


def test_evaluate_feedback_loop_guard_blocks_low_ram() -> None:
    settings = SimpleNamespace(
        VENOM_OLLAMA_PROFILE="balanced-12-24gb",
        OLLAMA_CONTEXT_LENGTH=32768,
        OLLAMA_NUM_PARALLEL=0,
        OLLAMA_MAX_QUEUE=0,
        OLLAMA_KV_CACHE_TYPE="",
        OLLAMA_FLASH_ATTENTION=True,
        LLM_KEEP_ALIVE="30m",
    )
    guard = evaluate_feedback_loop_guard(
        model_id=FEEDBACK_LOOP_PRIMARY_MODEL,
        settings=settings,
        ram_total_gb=8.0,
        vram_total_mb=8192.0,
    )
    assert guard.allowed is False
    assert guard.guard_reason == "resource_guard"


def test_evaluate_feedback_loop_guard_blocks_high_context_length() -> None:
    settings = SimpleNamespace(
        VENOM_OLLAMA_PROFILE="balanced-12-24gb",
        OLLAMA_CONTEXT_LENGTH=131072,
        OLLAMA_NUM_PARALLEL=0,
        OLLAMA_MAX_QUEUE=0,
        OLLAMA_KV_CACHE_TYPE="",
        OLLAMA_FLASH_ATTENTION=True,
        LLM_KEEP_ALIVE="30m",
    )
    guard = evaluate_feedback_loop_guard(
        model_id=FEEDBACK_LOOP_PRIMARY_MODEL,
        settings=settings,
        ram_total_gb=32.0,
        vram_total_mb=24576.0,
    )
    assert guard.allowed is False
    assert guard.guard_reason == "resource_guard"
    assert "OLLAMA_CONTEXT_LENGTH" in str(guard.recommendation)


def test_evaluate_feedback_loop_guard_blocks_low_vram_metric() -> None:
    settings = SimpleNamespace(
        VENOM_OLLAMA_PROFILE="balanced-12-24gb",
        OLLAMA_CONTEXT_LENGTH=32768,
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
        vram_total_mb=2048.0,
    )
    assert guard.allowed is False
    assert guard.guard_reason == "resource_guard"
    assert "VRAM" in str(guard.recommendation)


def test_evaluate_feedback_loop_guard_allows_non_primary_model() -> None:
    settings = SimpleNamespace(
        VENOM_OLLAMA_PROFILE="low-vram-8-12gb",
        OLLAMA_CONTEXT_LENGTH=131072,
        OLLAMA_NUM_PARALLEL=0,
        OLLAMA_MAX_QUEUE=0,
        OLLAMA_KV_CACHE_TYPE="",
        OLLAMA_FLASH_ATTENTION=True,
        LLM_KEEP_ALIVE="30m",
    )
    guard = evaluate_feedback_loop_guard(
        model_id="qwen2.5-coder:3b",
        settings=settings,
        ram_total_gb=1.0,
        vram_total_mb=256.0,
    )
    assert guard.allowed is True
    assert guard.guard_reason is None
    assert guard.recommendation is None


def test_evaluate_feedback_loop_guard_allows_when_thresholds_met() -> None:
    settings = SimpleNamespace(
        VENOM_OLLAMA_PROFILE="balanced-12-24gb",
        OLLAMA_CONTEXT_LENGTH=32768,
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
    assert guard.allowed is True
    assert guard.guard_reason is None
    assert guard.recommendation is None


def test_feedback_loop_policy_candidates_include_primary_and_fallbacks() -> None:
    policy = feedback_loop_policy()
    assert policy.candidates == (
        FEEDBACK_LOOP_PRIMARY_MODEL,
        *FEEDBACK_LOOP_FALLBACK_MODELS,
    )


def test_classify_feedback_loop_tier_values() -> None:
    assert classify_feedback_loop_tier("qwen2.5-coder:7b") == "primary"
    assert classify_feedback_loop_tier("qwen2.5-coder:3b") == "fallback"
    assert classify_feedback_loop_tier("phi3:mini") == "not_recommended"
