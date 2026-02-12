"""Testy dla policy gate - globalnego gate'u polityk bezpieczeństwa."""

import os
from unittest.mock import patch

from venom_core.core.policy_gate import (
    PolicyDecision,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
    PolicyGate,
    PolicyReasonCode,
    policy_gate,
)


class TestPolicyGate:
    """Testy dla PolicyGate."""

    def test_singleton_pattern(self):
        """PolicyGate powinien być singletonem."""
        gate1 = PolicyGate()
        gate2 = PolicyGate()
        assert gate1 is gate2

    def test_gate_disabled_by_default(self):
        """Gate powinien być domyślnie wyłączony."""
        with patch.dict(os.environ, {}, clear=True):
            gate = PolicyGate()
            assert not gate.enabled

    def test_gate_enabled_via_env(self):
        """Gate powinien być włączony gdy ENABLE_POLICY_GATE=true."""
        with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
            gate = PolicyGate()
            gate._initialized = False
            gate.__init__()
            assert gate.enabled

    def test_evaluate_bypass_when_disabled(self):
        """Gdy gate wyłączony, powinien zawsze pozwalać."""
        with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "false"}):
            gate = PolicyGate()
            gate._initialized = False
            gate.__init__()

            context = PolicyEvaluationContext(
                content="test request",
                intent="CODE_GENERATION",
            )
            result = gate.evaluate(context)

            assert result.decision == PolicyDecision.ALLOW
            assert "disabled" in result.message.lower()

    def test_evaluate_allow_when_enabled(self):
        """Gdy gate włączony (MVP), powinien pozwalać (brak reguł)."""
        with patch.dict(os.environ, {"ENABLE_POLICY_GATE": "true"}):
            gate = PolicyGate()
            gate._initialized = False
            gate.__init__()

            context = PolicyEvaluationContext(
                content="test request",
                intent="CODE_GENERATION",
            )
            result = gate.evaluate(context)

            assert result.decision == PolicyDecision.ALLOW

    def test_evaluate_before_provider_selection(self):
        """Test ewaluacji przed wyborem providera."""
        context = PolicyEvaluationContext(
            content="test request",
            planned_provider="openai",
        )
        result = policy_gate.evaluate_before_provider_selection(context)
        assert isinstance(result, PolicyEvaluationResult)

    def test_evaluate_before_tool_execution(self):
        """Test ewaluacji przed wykonaniem narzędzi."""
        context = PolicyEvaluationContext(
            content="test request",
            planned_tools=["git", "shell"],
        )
        result = policy_gate.evaluate_before_tool_execution(context)
        assert isinstance(result, PolicyEvaluationResult)


class TestPolicyEvaluationContext:
    """Testy dla PolicyEvaluationContext."""

    def test_minimal_context(self):
        """Test minimalnego kontekstu."""
        context = PolicyEvaluationContext(content="test")
        assert context.content == "test"
        assert context.intent is None
        assert context.planned_tools == []

    def test_full_context(self):
        """Test pełnego kontekstu."""
        context = PolicyEvaluationContext(
            content="test request",
            intent="CODE_GENERATION",
            planned_provider="openai",
            planned_tools=["git", "shell"],
            session_id="session-123",
            forced_tool="git",
            forced_provider="openai",
        )
        assert context.content == "test request"
        assert context.intent == "CODE_GENERATION"
        assert context.planned_provider == "openai"
        assert context.planned_tools == ["git", "shell"]
        assert context.session_id == "session-123"


class TestPolicyEvaluationResult:
    """Testy dla PolicyEvaluationResult."""

    def test_allow_result(self):
        """Test wyniku ALLOW."""
        result = PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            message="Request allowed",
        )
        assert result.decision == PolicyDecision.ALLOW
        assert result.reason_code is None

    def test_block_result(self):
        """Test wyniku BLOCK z kodem przyczyny."""
        result = PolicyEvaluationResult(
            decision=PolicyDecision.BLOCK,
            reason_code=PolicyReasonCode.POLICY_UNSAFE_CONTENT,
            message="Unsafe content detected",
        )
        assert result.decision == PolicyDecision.BLOCK
        assert result.reason_code == PolicyReasonCode.POLICY_UNSAFE_CONTENT
        assert "unsafe" in result.message.lower()


class TestPolicyDecision:
    """Testy dla PolicyDecision enum."""

    def test_decision_values(self):
        """Test wartości decision enum."""
        assert PolicyDecision.ALLOW.value == "allow"
        assert PolicyDecision.BLOCK.value == "block"
        assert PolicyDecision.REVIEW.value == "review"


class TestPolicyReasonCode:
    """Testy dla PolicyReasonCode enum."""

    def test_reason_codes(self):
        """Test wszystkich kodów przyczyn."""
        assert PolicyReasonCode.POLICY_UNSAFE_CONTENT.value == "POLICY_UNSAFE_CONTENT"
        assert (
            PolicyReasonCode.POLICY_TOOL_RESTRICTED.value == "POLICY_TOOL_RESTRICTED"
        )
        assert (
            PolicyReasonCode.POLICY_PROVIDER_RESTRICTED.value
            == "POLICY_PROVIDER_RESTRICTED"
        )
        assert (
            PolicyReasonCode.POLICY_MISSING_CONTEXT.value == "POLICY_MISSING_CONTEXT"
        )
