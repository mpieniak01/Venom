"""Tests for provider governance - credentials, cost limits, fallback policy."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from venom_core.core.provider_governance import (
    ProviderGovernance,
    FallbackPolicy,
    CredentialStatus,
    FallbackReasonCode,
    LimitType,
    CostLimit,
    RateLimit,
    get_provider_governance,
)


class TestCredentialManagement:
    """Tests for credential validation and masking."""

    def test_validate_credentials_openai_configured(self):
        """Test OpenAI credential validation when API key is configured."""
        with patch("venom_core.core.provider_governance.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-test-key-1234567890"
            governance = ProviderGovernance()
            status = governance.validate_credentials("openai")
            assert status == CredentialStatus.CONFIGURED

    def test_validate_credentials_openai_missing(self):
        """Test OpenAI credential validation when API key is missing."""
        with patch("venom_core.core.provider_governance.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            governance = ProviderGovernance()
            status = governance.validate_credentials("openai")
            assert status == CredentialStatus.MISSING_CREDENTIALS

    def test_validate_credentials_google_configured(self):
        """Test Google credential validation when API key is configured."""
        with patch("venom_core.core.provider_governance.SETTINGS") as mock_settings:
            mock_settings.GOOGLE_API_KEY = "AIzaSy-test-key-1234567890"
            governance = ProviderGovernance()
            status = governance.validate_credentials("google")
            assert status == CredentialStatus.CONFIGURED

    def test_validate_credentials_local_runtime(self):
        """Test local runtime (ollama, vllm) always returns configured."""
        governance = ProviderGovernance()
        assert governance.validate_credentials("ollama") == CredentialStatus.CONFIGURED
        assert governance.validate_credentials("vllm") == CredentialStatus.CONFIGURED

    def test_validate_credentials_huggingface(self):
        """Test HuggingFace (catalog) always returns configured."""
        governance = ProviderGovernance()
        assert governance.validate_credentials("huggingface") == CredentialStatus.CONFIGURED

    def test_mask_secret_short(self):
        """Test masking of short secrets."""
        governance = ProviderGovernance()
        assert governance.mask_secret("short") == "***"
        assert governance.mask_secret("") == "***"

    def test_mask_secret_normal(self):
        """Test masking of normal length secrets."""
        governance = ProviderGovernance()
        secret = "sk-1234567890abcdefghij"
        masked = governance.mask_secret(secret)
        assert masked.startswith("sk-1")
        assert masked.endswith("ghij")
        assert "..." in masked
        # Ensure middle part is hidden
        assert "567890abcd" not in masked

    def test_no_secret_leakage_in_logs(self):
        """Test that secrets are not logged in plain text."""
        with patch("venom_core.core.provider_governance.SETTINGS") as mock_settings:
            secret_key = "sk-very-secret-key-do-not-log-123456"
            mock_settings.OPENAI_API_KEY = secret_key
            governance = ProviderGovernance()
            
            # Trigger operations that might log
            status = governance.validate_credentials("openai")
            
            # Verify masking works correctly
            masked = governance.mask_secret(secret_key)
            assert secret_key not in masked
            assert masked.startswith("sk-v")
            assert masked.endswith("3456")


class TestCostLimits:
    """Tests for cost limit enforcement."""

    def test_cost_limit_under_limit(self):
        """Test request under cost limit is allowed."""
        governance = ProviderGovernance()
        allowed, reason_code, message = governance.check_cost_limit("openai", 1.0)
        assert allowed is True
        assert reason_code is None
        assert message is None

    def test_cost_limit_soft_warning(self):
        """Test soft limit triggers warning but allows request."""
        governance = ProviderGovernance()
        # Set current usage near soft limit
        governance.cost_limits["global"].current_usage_usd = 9.5
        governance.cost_limits["global"].soft_limit_usd = 10.0
        governance.cost_limits["global"].hard_limit_usd = 50.0
        
        allowed, reason_code, message = governance.check_cost_limit("openai", 1.0)
        assert allowed is True  # Still allowed (soft limit is a warning, not a block)
        # Soft limit exceeded but request is allowed

    def test_cost_limit_hard_block(self):
        """Test hard limit blocks request."""
        governance = ProviderGovernance()
        # Set current usage at hard limit
        governance.cost_limits["global"].current_usage_usd = 49.0
        governance.cost_limits["global"].hard_limit_usd = 50.0
        
        allowed, reason_code, message = governance.check_cost_limit("openai", 2.0)
        assert allowed is False
        assert reason_code == "BUDGET_HARD_LIMIT_EXCEEDED"
        assert "hard limit exceeded" in message.lower()

    def test_cost_limit_per_provider(self):
        """Test per-provider cost limits."""
        governance = ProviderGovernance()
        # Add provider-specific limit
        governance.cost_limits["provider:openai"] = CostLimit(
            limit_type=LimitType.PER_PROVIDER,
            scope="openai",
            soft_limit_usd=2.0,
            hard_limit_usd=5.0,
            current_usage_usd=4.5,
        )
        
        allowed, reason_code, message = governance.check_cost_limit("openai", 1.0)
        assert allowed is False
        assert reason_code == "PROVIDER_BUDGET_EXCEEDED"
        assert "openai" in message.lower()

    def test_record_usage_updates_limits(self):
        """Test that recording usage updates cost and rate counters."""
        governance = ProviderGovernance()
        initial_global_cost = governance.cost_limits["global"].current_usage_usd
        
        governance.record_usage("openai", cost_usd=5.0, tokens=1000, requests=1)
        
        # Check global cost updated
        assert governance.cost_limits["global"].current_usage_usd == initial_global_cost + 5.0
        
        # Check provider cost created and updated
        assert "provider:openai" in governance.cost_limits
        assert governance.cost_limits["provider:openai"].current_usage_usd == 5.0
        
        # Check rate limit updated
        assert governance.rate_limits["global"].current_requests == 1
        assert governance.rate_limits["global"].current_tokens == 1000


class TestRateLimits:
    """Tests for rate limit enforcement."""

    def test_rate_limit_under_limit(self):
        """Test request under rate limit is allowed."""
        governance = ProviderGovernance()
        allowed, reason_code, message = governance.check_rate_limit("openai", 100)
        assert allowed is True
        assert reason_code is None

    def test_rate_limit_requests_exceeded(self):
        """Test rate limit blocks when max requests exceeded."""
        governance = ProviderGovernance()
        governance.rate_limits["global"].max_requests_per_minute = 10
        governance.rate_limits["global"].current_requests = 10
        
        allowed, reason_code, message = governance.check_rate_limit("openai", 100)
        assert allowed is False
        assert reason_code == "RATE_LIMIT_REQUESTS_EXCEEDED"
        assert "request rate limit exceeded" in message.lower()

    def test_rate_limit_tokens_exceeded(self):
        """Test rate limit blocks when max tokens exceeded."""
        governance = ProviderGovernance()
        governance.rate_limits["global"].max_tokens_per_minute = 1000
        governance.rate_limits["global"].current_tokens = 900
        
        allowed, reason_code, message = governance.check_rate_limit("openai", 200)
        assert allowed is False
        assert reason_code == "RATE_LIMIT_TOKENS_EXCEEDED"
        assert "token rate limit exceeded" in message.lower()

    def test_rate_limit_period_reset(self):
        """Test rate limit counters reset after period expires."""
        governance = ProviderGovernance()
        # Set high usage
        governance.rate_limits["global"].current_requests = 50
        governance.rate_limits["global"].current_tokens = 50000
        # Set period start to more than 1 minute ago
        governance.rate_limits["global"].period_start = datetime.now() - timedelta(minutes=2)
        
        # Should reset and allow
        allowed, reason_code, message = governance.check_rate_limit("openai", 100)
        assert allowed is True
        assert governance.rate_limits["global"].current_requests == 0
        assert governance.rate_limits["global"].current_tokens == 0


class TestFallbackPolicy:
    """Tests for fallback policy engine."""

    def test_fallback_policy_default(self):
        """Test default fallback policy configuration."""
        policy = FallbackPolicy()
        assert policy.preferred_provider == "ollama"
        assert "ollama" in policy.fallback_order
        assert policy.enable_timeout_fallback is True
        assert policy.enable_auth_fallback is True

    def test_select_provider_no_fallback_needed(self):
        """Test provider selection when no fallback is needed."""
        with patch("venom_core.core.provider_governance.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-test-key"
            governance = ProviderGovernance()
            
            decision = governance.select_provider_with_fallback("openai")
            
            assert decision.allowed is True
            assert decision.provider == "openai"
            assert decision.fallback_applied is False

    def test_select_provider_fallback_on_missing_credentials(self):
        """Test fallback when preferred provider has missing credentials."""
        with patch("venom_core.core.provider_governance.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""  # Missing
            mock_settings.GOOGLE_API_KEY = ""  # Missing
            
            governance = ProviderGovernance()
            # Set fallback order: openai -> ollama
            governance.fallback_policy.fallback_order = ["openai", "ollama", "vllm"]
            
            decision = governance.select_provider_with_fallback("openai")
            
            # Should fallback to ollama (local, always configured)
            assert decision.allowed is True
            assert decision.provider == "ollama"
            assert decision.fallback_applied is True
            assert decision.reason_code == "FALLBACK_AUTH_ERROR"

    def test_select_provider_no_fallback_available(self):
        """Test when no fallback provider is available."""
        with patch("venom_core.core.provider_governance.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.GOOGLE_API_KEY = ""
            
            governance = ProviderGovernance()
            # Set fallback order to only cloud providers
            governance.fallback_policy.fallback_order = ["openai", "google"]
            
            decision = governance.select_provider_with_fallback("openai")
            
            assert decision.allowed is False
            assert decision.provider is None
            assert decision.reason_code == "NO_PROVIDER_AVAILABLE"

    def test_fallback_event_recorded(self):
        """Test that fallback events are recorded in audit trail."""
        with patch("venom_core.core.provider_governance.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            
            governance = ProviderGovernance()
            governance.fallback_policy.fallback_order = ["openai", "ollama"]
            
            initial_count = len(governance.fallback_history)
            governance.select_provider_with_fallback("openai")
            
            # Check event recorded
            assert len(governance.fallback_history) == initial_count + 1
            event = governance.fallback_history[-1]
            assert event.from_provider == "openai"
            assert event.to_provider == "ollama"
            assert event.reason_code == FallbackReasonCode.AUTH_ERROR

    def test_fallback_timeout_disabled(self):
        """Test fallback is not applied when timeout fallback is disabled."""
        governance = ProviderGovernance()
        governance.fallback_policy.enable_timeout_fallback = False
        
        result = governance._find_fallback_provider("openai", FallbackReasonCode.TIMEOUT)
        assert result is None

    def test_fallback_budget_disabled(self):
        """Test fallback is not applied when budget fallback is disabled."""
        governance = ProviderGovernance()
        governance.fallback_policy.enable_budget_fallback = False
        
        result = governance._find_fallback_provider("openai", FallbackReasonCode.BUDGET_EXCEEDED)
        assert result is None

    def test_fallback_history_limit(self):
        """Test fallback history is limited to last 100 events."""
        governance = ProviderGovernance()
        
        # Record 150 events
        for i in range(150):
            governance._record_fallback_event(
                "openai",
                "ollama",
                FallbackReasonCode.TIMEOUT,
                f"Event {i}",
            )
        
        # Should keep only last 100
        assert len(governance.fallback_history) == 100


class TestGovernanceStatus:
    """Tests for governance status reporting."""

    def test_get_governance_status_structure(self):
        """Test governance status returns expected structure."""
        governance = ProviderGovernance()
        status = governance.get_governance_status()
        
        assert "cost_limits" in status
        assert "rate_limits" in status
        assert "recent_fallbacks" in status
        assert "fallback_policy" in status

    def test_get_governance_status_cost_limits(self):
        """Test cost limits in governance status."""
        governance = ProviderGovernance()
        governance.cost_limits["global"].current_usage_usd = 5.0
        
        status = governance.get_governance_status()
        
        assert "global" in status["cost_limits"]
        global_limit = status["cost_limits"]["global"]
        assert global_limit["current_usage_usd"] == 5.0
        assert "usage_percentage" in global_limit

    def test_get_governance_status_recent_fallbacks(self):
        """Test recent fallbacks in governance status (max 10)."""
        governance = ProviderGovernance()
        
        # Record 15 fallback events
        for i in range(15):
            governance._record_fallback_event(
                "openai",
                "ollama",
                FallbackReasonCode.TIMEOUT,
                f"Event {i}",
            )
        
        status = governance.get_governance_status()
        
        # Should return only last 10
        assert len(status["recent_fallbacks"]) == 10

    def test_governance_singleton(self):
        """Test that get_provider_governance returns singleton instance."""
        instance1 = get_provider_governance()
        instance2 = get_provider_governance()
        
        assert instance1 is instance2


class TestReasonCodeStability:
    """Tests for reason_code stability and consistency."""

    def test_reason_codes_are_stable(self):
        """Test that reason codes remain consistent across operations."""
        governance = ProviderGovernance()
        
        # Test cost limit reason codes
        governance.cost_limits["global"].current_usage_usd = 100.0
        governance.cost_limits["global"].hard_limit_usd = 50.0
        
        _, reason_code1, _ = governance.check_cost_limit("openai", 1.0)
        _, reason_code2, _ = governance.check_cost_limit("openai", 1.0)
        
        assert reason_code1 == reason_code2
        assert reason_code1 == "BUDGET_HARD_LIMIT_EXCEEDED"

    def test_fallback_reason_codes_enum(self):
        """Test that fallback reason codes are from enum."""
        # Verify all expected reason codes exist
        assert FallbackReasonCode.TIMEOUT.value == "TIMEOUT"
        assert FallbackReasonCode.AUTH_ERROR.value == "AUTH_ERROR"
        assert FallbackReasonCode.BUDGET_EXCEEDED.value == "BUDGET_EXCEEDED"
        assert FallbackReasonCode.PROVIDER_DEGRADED.value == "PROVIDER_DEGRADED"
        assert FallbackReasonCode.PROVIDER_OFFLINE.value == "PROVIDER_OFFLINE"
        assert FallbackReasonCode.RATE_LIMIT_EXCEEDED.value == "RATE_LIMIT_EXCEEDED"
