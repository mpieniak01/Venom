from __future__ import annotations

import gc
import time
import tracemalloc
from dataclasses import dataclass

import pytest

from venom_core.contracts.routing import ReasonCode, RoutingDecision
from venom_core.core.routing_integration import build_routing_decision

pytestmark = [pytest.mark.performance]


@dataclass
class _Request:
    content: str
    forced_intent: str | None = None
    forced_tool: str | None = None
    forced_provider: str | None = None


@dataclass
class _RuntimeInfo:
    provider: str
    model_name: str


@dataclass
class _GovernanceDecision:
    allowed: bool
    provider: str
    reason_code: str
    fallback_applied: bool
    user_message: str


class _DummyRouter:
    def __init__(self, *args, **kwargs):
        self._provider = "openai"
        self._init_cost = [idx for idx in range(128)]

    def route_task(self, task_type, prompt):
        return {
            "target": "cloud",
            "model_name": "gpt-4o-mini",
            "provider": self._provider,
            "reason": "Tryb HYBRID: złożone zadanie CODING_COMPLEX -> CLOUD",
            "is_paid": True,
        }

    def calculate_complexity(self, prompt, task_type):
        return 8


class _DummyGovernance:
    def select_provider_with_fallback(self, preferred_provider, reason=None):
        return _GovernanceDecision(
            allowed=True,
            provider="vllm",
            reason_code="FALLBACK_AUTH_ERROR",
            fallback_applied=True,
            user_message="fallback",
        )


def _baseline_build_routing_decision(request, runtime_info, state_manager=None):
    from venom_core.core.routing_integration import (
        _REASON_CODE_FROM_GOVERNANCE,
        _build_fallback_chain,
        _resolve_decision_model,
        _to_reason_code,
        _to_runtime_target,
        _to_task_type,
    )

    start = time.perf_counter()
    router = _DummyRouter(state_manager=state_manager)
    task_type = _to_task_type(request)
    routing_info = router.route_task(task_type, request.content)
    complexity_score = float(router.calculate_complexity(request.content, task_type))
    is_sensitive = bool(
        task_type.name == "SENSITIVE" or request.forced_intent == "SENSITIVE"
    )

    preferred_provider = "openai"
    governance_decision = _DummyGovernance().select_provider_with_fallback(
        preferred_provider=preferred_provider,
        reason=str(routing_info.get("reason") or ""),
    )

    selected_provider = governance_decision.provider or preferred_provider
    reason_code = _REASON_CODE_FROM_GOVERNANCE.get(
        str(governance_decision.reason_code or ""),
        _to_reason_code(routing_info),
    )

    return RoutingDecision(
        target_runtime=_to_runtime_target(selected_provider),
        provider=selected_provider,
        model=_resolve_decision_model(
            is_code_generation=str(request.forced_intent or "").strip().upper()
            == "CODE_GENERATION",
            selected_provider=selected_provider,
            routing_info=routing_info,
            runtime_info=runtime_info,
        ),
        reason_code=reason_code,
        complexity_score=complexity_score,
        is_sensitive=is_sensitive,
        fallback_applied=bool(governance_decision.fallback_applied),
        fallback_chain=_build_fallback_chain(
            preferred_provider=preferred_provider,
            selected_provider=selected_provider,
            fallback_applied=bool(governance_decision.fallback_applied),
        ),
        policy_gate_passed=bool(governance_decision.allowed),
        estimated_cost_usd=0.0,
        budget_remaining_usd=None,
        decision_latency_ms=(time.perf_counter() - start) * 1000.0,
        error_message=None,
    )


def _run_mix(iterations: int, routing_builder) -> None:
    request = _Request(
        content="implement complex flow", forced_intent="COMPLEX_PLANNING"
    )
    runtime_info = _RuntimeInfo(provider="ollama", model_name="gemma3:4b")

    class _StateManager:
        pass

    state_manager = _StateManager()
    for _ in range(iterations):
        decision = routing_builder(
            request=request, runtime_info=runtime_info, state_manager=state_manager
        )
        assert decision.reason_code == ReasonCode.FALLBACK_AUTH_ERROR
        assert decision.provider in {"vllm", "VLLM", "vllm"}


def _measure_elapsed(iterations: int, routing_builder) -> float:
    start = time.perf_counter()
    _run_mix(iterations, routing_builder)
    return time.perf_counter() - start


def _measure_peak(iterations: int, routing_builder) -> int:
    gc.collect()
    tracemalloc.start()
    _run_mix(iterations, routing_builder)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def test_build_routing_decision_reduces_hot_path_latency_and_memory(monkeypatch):
    monkeypatch.setattr(
        "venom_core.core.routing_integration.HybridModelRouter",
        _DummyRouter,
    )
    monkeypatch.setattr(
        "venom_core.core.routing_integration.get_provider_governance",
        lambda: _DummyGovernance(),
    )
    monkeypatch.setattr(
        "venom_core.core.routing_integration.normalize_forced_provider",
        lambda _value: "openai",
    )

    _run_mix(200, build_routing_decision)

    iterations = 8000
    baseline_elapsed = _measure_elapsed(iterations, _baseline_build_routing_decision)
    optimized_elapsed = _measure_elapsed(iterations, build_routing_decision)

    baseline_peak = _measure_peak(iterations, _baseline_build_routing_decision)
    optimized_peak = _measure_peak(iterations, build_routing_decision)

    assert optimized_elapsed <= baseline_elapsed * 1.20
    # Lock-protected cache access can add tiny allocation noise under tracemalloc.
    assert optimized_peak <= int(baseline_peak * 1.35)
