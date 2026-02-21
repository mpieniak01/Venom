"""
Unit tests for routing contract module.

Tests the routing decision contract, enums, and policy definitions
defined in ADR-001.
"""

from datetime import datetime

from venom_core.contracts.routing import (
    ComplexityThresholds,
    FallbackPolicy,
    ReasonCode,
    RoutingDecision,
    RoutingKPIs,
    RuntimeTarget,
)


class TestRuntimeTarget:
    """Test RuntimeTarget enum and methods."""

    def test_local_runtime_identification(self):
        """Test that local runtimes are correctly identified."""
        assert RuntimeTarget.LOCAL_OLLAMA.is_local() is True
        assert RuntimeTarget.LOCAL_VLLM.is_local() is True
        assert RuntimeTarget.CLOUD_OPENAI.is_local() is False
        assert RuntimeTarget.CLOUD_GOOGLE.is_local() is False

    def test_cloud_runtime_identification(self):
        """Test that cloud runtimes are correctly identified."""
        assert RuntimeTarget.CLOUD_OPENAI.is_cloud() is True
        assert RuntimeTarget.CLOUD_GOOGLE.is_cloud() is True
        assert RuntimeTarget.LOCAL_OLLAMA.is_cloud() is False
        assert RuntimeTarget.LOCAL_VLLM.is_cloud() is False

    def test_runtime_values(self):
        """Test that runtime target values match provider names."""
        assert RuntimeTarget.LOCAL_OLLAMA.value == "ollama"
        assert RuntimeTarget.LOCAL_VLLM.value == "vllm"
        assert RuntimeTarget.CLOUD_OPENAI.value == "openai"
        assert RuntimeTarget.CLOUD_GOOGLE.value == "google"


class TestReasonCode:
    """Test ReasonCode enum."""

    def test_primary_routing_codes_exist(self):
        """Test that primary routing reason codes are defined."""
        assert ReasonCode.DEFAULT_ECO_MODE
        assert ReasonCode.TASK_COMPLEXITY_LOW
        assert ReasonCode.TASK_COMPLEXITY_HIGH
        assert ReasonCode.SENSITIVE_CONTENT_OVERRIDE

    def test_fallback_codes_exist(self):
        """Test that fallback reason codes are defined."""
        assert ReasonCode.FALLBACK_TIMEOUT
        assert ReasonCode.FALLBACK_AUTH_ERROR
        assert ReasonCode.FALLBACK_BUDGET_EXCEEDED
        assert ReasonCode.FALLBACK_PROVIDER_DEGRADED
        assert ReasonCode.FALLBACK_PROVIDER_OFFLINE
        assert ReasonCode.FALLBACK_RATE_LIMIT

    def test_policy_block_codes_exist(self):
        """Test that policy block reason codes are defined."""
        assert ReasonCode.POLICY_BLOCKED_BUDGET
        assert ReasonCode.POLICY_BLOCKED_RATE_LIMIT
        assert ReasonCode.POLICY_BLOCKED_NO_PROVIDER
        assert ReasonCode.POLICY_BLOCKED_CONTENT


class TestRoutingDecision:
    """Test RoutingDecision dataclass."""

    def test_successful_local_decision(self):
        """Test creating a successful local routing decision."""
        decision = RoutingDecision(
            target_runtime=RuntimeTarget.LOCAL_OLLAMA,
            provider="ollama",
            model="gemma2:9b-instruct-q8_0",
            reason_code=ReasonCode.DEFAULT_ECO_MODE,
            complexity_score=2.0,
            is_sensitive=False,
            estimated_cost_usd=0.0,
        )

        assert decision.is_successful() is True
        assert decision.is_cost_free() is True
        assert decision.target_runtime.is_local() is True
        assert decision.fallback_applied is False
        assert decision.policy_gate_passed is True

    def test_successful_cloud_decision(self):
        """Test creating a successful cloud routing decision."""
        decision = RoutingDecision(
            target_runtime=RuntimeTarget.CLOUD_OPENAI,
            provider="openai",
            model="gpt-4o-mini",
            reason_code=ReasonCode.TASK_COMPLEXITY_HIGH,
            complexity_score=8.5,
            is_sensitive=False,
            estimated_cost_usd=0.015,
            budget_remaining_usd=42.50,
        )

        assert decision.is_successful() is True
        assert decision.is_cost_free() is False
        assert decision.target_runtime.is_cloud() is True

    def test_failed_decision_no_provider(self):
        """Test creating a failed routing decision (no provider available)."""
        decision = RoutingDecision(
            target_runtime=None,
            provider=None,
            model=None,
            reason_code=ReasonCode.POLICY_BLOCKED_NO_PROVIDER,
            policy_gate_passed=False,
            error_message="No provider available: all local providers offline",
        )

        assert decision.is_successful() is False
        assert decision.policy_gate_passed is False
        assert decision.error_message is not None

    def test_sensitive_content_override(self):
        """Test routing decision for sensitive content."""
        decision = RoutingDecision(
            target_runtime=RuntimeTarget.LOCAL_OLLAMA,
            provider="ollama",
            model="gemma2:9b-instruct-q8_0",
            reason_code=ReasonCode.SENSITIVE_CONTENT_OVERRIDE,
            complexity_score=6.0,
            is_sensitive=True,
            estimated_cost_usd=0.0,
        )

        assert decision.is_successful() is True
        assert decision.is_sensitive is True
        assert decision.target_runtime.is_local() is True

    def test_fallback_applied(self):
        """Test routing decision with fallback."""
        decision = RoutingDecision(
            target_runtime=RuntimeTarget.LOCAL_VLLM,
            provider="vllm",
            model="Qwen2.5-14B-Instruct",
            reason_code=ReasonCode.FALLBACK_BUDGET_EXCEEDED,
            complexity_score=7.5,
            fallback_applied=True,
            fallback_chain=["openai", "vllm"],
            estimated_cost_usd=0.0,
        )

        assert decision.is_successful() is True
        assert decision.fallback_applied is True
        assert len(decision.fallback_chain) == 2
        assert decision.fallback_chain[0] == "openai"

    def test_to_dict_serialization(self):
        """Test converting routing decision to dictionary."""
        decision = RoutingDecision(
            target_runtime=RuntimeTarget.LOCAL_OLLAMA,
            provider="ollama",
            model="gemma2:9b",
            reason_code=ReasonCode.DEFAULT_ECO_MODE,
            complexity_score=2.0,
        )

        result = decision.to_dict()

        assert isinstance(result, dict)
        assert result["target_runtime"] == "ollama"
        assert result["provider"] == "ollama"
        assert result["model"] == "gemma2:9b"
        assert result["reason_code"] == "default_eco_mode"
        assert result["complexity_score"] == 2.0

    def test_is_cost_free_with_floating_point(self):
        """Test is_cost_free with various floating point values (SonarCloud fix)."""
        # Local runtime should always be cost-free
        local_decision = RoutingDecision(
            target_runtime=RuntimeTarget.LOCAL_OLLAMA,
            provider="ollama",
            model="test",
            reason_code=ReasonCode.DEFAULT_ECO_MODE,
            estimated_cost_usd=0.00001,  # Even with negligible cost
        )
        assert local_decision.is_cost_free() is True

        # Cloud with negligible cost (< $0.0001) should be considered free
        negligible_cost = RoutingDecision(
            target_runtime=RuntimeTarget.CLOUD_OPENAI,
            provider="openai",
            model="test",
            reason_code=ReasonCode.TASK_COMPLEXITY_HIGH,
            estimated_cost_usd=0.00005,
        )
        assert negligible_cost.is_cost_free() is True

        # Cloud with actual cost should not be free
        actual_cost = RoutingDecision(
            target_runtime=RuntimeTarget.CLOUD_OPENAI,
            provider="openai",
            model="test",
            reason_code=ReasonCode.TASK_COMPLEXITY_HIGH,
            estimated_cost_usd=0.001,
        )
        assert actual_cost.is_cost_free() is False

    def test_decision_timestamp_format(self):
        """Test that decision timestamp is in ISO 8601 format."""
        decision = RoutingDecision(
            target_runtime=RuntimeTarget.LOCAL_OLLAMA,
            provider="ollama",
            model="gemma2:9b",
            reason_code=ReasonCode.DEFAULT_ECO_MODE,
        )

        # Verify timestamp is valid ISO 8601
        timestamp = decision.decision_timestamp
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert isinstance(parsed, datetime)


class TestRoutingKPIs:
    """Test RoutingKPIs constants."""

    def test_cost_kpis_defined(self):
        """Test that cost KPIs are properly defined."""
        assert RoutingKPIs.DAILY_COST_ECO_TARGET_USD == 0.0
        assert RoutingKPIs.DAILY_COST_PAID_TARGET_USD == 5.0
        assert RoutingKPIs.DAILY_COST_SOFT_LIMIT_USD == 10.0
        assert RoutingKPIs.DAILY_COST_HARD_LIMIT_USD == 50.0
        assert RoutingKPIs.COST_PER_REQUEST_TARGET_USD == 0.01

    def test_latency_kpis_defined(self):
        """Test that latency KPIs are properly defined."""
        assert RoutingKPIs.ROUTING_DECISION_TARGET_MS == 100
        assert RoutingKPIs.LOCAL_INFERENCE_P95_TARGET_S == 3.0
        assert RoutingKPIs.CLOUD_INFERENCE_P95_TARGET_S == 2.0
        assert RoutingKPIs.TOTAL_REQUEST_P99_TARGET_S == 5.0

    def test_quality_kpis_defined(self):
        """Test that quality KPIs are properly defined."""
        assert RoutingKPIs.TASK_SUCCESS_RATE_TARGET == 0.95
        assert RoutingKPIs.STRUCTURED_OUTPUT_VALIDITY_TARGET == 0.98
        assert RoutingKPIs.FALLBACK_SUCCESS_RATE_TARGET == 0.90
        assert RoutingKPIs.SENSITIVE_DATA_LEAK_RATE == 0.0

    def test_reliability_kpis_defined(self):
        """Test that reliability KPIs are properly defined."""
        assert RoutingKPIs.PROVIDER_AVAILABILITY_LOCAL_TARGET == 0.99
        assert RoutingKPIs.PROVIDER_AVAILABILITY_CLOUD_TARGET == 0.999
        assert RoutingKPIs.FALLBACK_CHAIN_EXHAUSTION_TARGET == 0.01


class TestComplexityThresholds:
    """Test ComplexityThresholds constants."""

    def test_complexity_ranges(self):
        """Test complexity score ranges."""
        assert ComplexityThresholds.LOW_COMPLEXITY_MAX == 5
        assert ComplexityThresholds.HIGH_COMPLEXITY_MIN == 6

    def test_complexity_weights(self):
        """Test complexity scoring weights."""
        assert ComplexityThresholds.CHARS_PER_POINT == 500
        assert ComplexityThresholds.CODE_BLOCK_BONUS == 2
        assert ComplexityThresholds.STRUCTURED_OUTPUT_BONUS == 1

    def test_task_complexity_base_scores(self):
        """Test base complexity scores for task types."""
        base = ComplexityThresholds.TASK_COMPLEXITY_BASE
        assert base["STANDARD"] == 2
        assert base["CHAT"] == 3
        assert base["CODING_SIMPLE"] == 4
        assert base["CODING_COMPLEX"] == 7
        assert base["ANALYSIS"] == 6
        assert base["GENERATION"] == 5
        assert base["RESEARCH"] == 7
        assert base["SENSITIVE"] == 0


class TestFallbackPolicy:
    """Test FallbackPolicy configuration."""

    def test_default_fallback_order(self):
        """Test default fallback order."""
        order = FallbackPolicy.DEFAULT_FALLBACK_ORDER
        assert order == ["ollama", "vllm", "openai", "google"]

    def test_eco_mode_fallback_order(self):
        """Test eco mode fallback order (local only)."""
        order = FallbackPolicy.ECO_MODE_FALLBACK_ORDER
        assert order == ["ollama", "vllm"]
        assert "openai" not in order
        assert "google" not in order

    def test_sensitive_content_fallback(self):
        """Test sensitive content fallback (local only)."""
        order = FallbackPolicy.SENSITIVE_CONTENT_FALLBACK
        assert order == ["ollama", "vllm"]
        assert "openai" not in order
        assert "google" not in order

    def test_paid_high_complexity_fallback(self):
        """Test paid mode high complexity fallback (cloud first)."""
        order = FallbackPolicy.PAID_HIGH_COMPLEXITY_FALLBACK
        assert order[0] in ["openai", "google"]  # Cloud first
        assert "ollama" in order  # Local as fallback

    def test_get_fallback_order_eco_mode(self):
        """Test getting fallback order for eco mode."""
        order = FallbackPolicy.get_fallback_order(
            is_eco_mode=True, is_sensitive=False, complexity_score=5.0
        )
        assert order == FallbackPolicy.ECO_MODE_FALLBACK_ORDER

    def test_get_fallback_order_sensitive(self):
        """Test getting fallback order for sensitive content."""
        order = FallbackPolicy.get_fallback_order(
            is_eco_mode=False, is_sensitive=True, complexity_score=8.0
        )
        assert order == FallbackPolicy.SENSITIVE_CONTENT_FALLBACK

    def test_get_fallback_order_paid_low_complexity(self):
        """Test getting fallback order for paid mode, low complexity."""
        order = FallbackPolicy.get_fallback_order(
            is_eco_mode=False, is_sensitive=False, complexity_score=4.0
        )
        assert order == FallbackPolicy.PAID_LOW_COMPLEXITY_FALLBACK
        assert order[0] == "ollama"  # Local first for cost

    def test_get_fallback_order_paid_high_complexity(self):
        """Test getting fallback order for paid mode, high complexity."""
        order = FallbackPolicy.get_fallback_order(
            is_eco_mode=False, is_sensitive=False, complexity_score=8.0
        )
        assert order == FallbackPolicy.PAID_HIGH_COMPLEXITY_FALLBACK
        assert order[0] in ["openai", "google"]  # Cloud first for quality

    def test_fallback_flags(self):
        """Test fallback behavior flags."""
        assert FallbackPolicy.ENABLE_TIMEOUT_FALLBACK is True
        assert FallbackPolicy.ENABLE_AUTH_FALLBACK is True
        assert FallbackPolicy.ENABLE_BUDGET_FALLBACK is True
        assert FallbackPolicy.ENABLE_DEGRADED_FALLBACK is True
        assert FallbackPolicy.TIMEOUT_THRESHOLD_SECONDS == 30.0
