"""Tests for venom_core.contracts package exports."""

from venom_core import contracts
from venom_core.contracts import (
    ComplexityThresholds,
    FallbackPolicy,
    ReasonCode,
    RoutingDecision,
    RoutingKPIs,
    RuntimeTarget,
)


def test_contracts_module_exports_are_available():
    """Package should re-export routing contract symbols via __all__."""
    exported = set(contracts.__all__)

    assert "RuntimeTarget" in exported
    assert "ReasonCode" in exported
    assert "RoutingDecision" in exported
    assert "RoutingKPIs" in exported
    assert "ComplexityThresholds" in exported
    assert "FallbackPolicy" in exported

    assert RuntimeTarget is contracts.RuntimeTarget
    assert ReasonCode is contracts.ReasonCode
    assert RoutingDecision is contracts.RoutingDecision
    assert RoutingKPIs is contracts.RoutingKPIs
    assert ComplexityThresholds is contracts.ComplexityThresholds
    assert FallbackPolicy is contracts.FallbackPolicy
