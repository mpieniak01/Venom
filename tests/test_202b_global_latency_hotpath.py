"""Global p95 latency measurement for 202B backend hot path."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from venom_core.api.schemas.tasks import TaskRequest
from venom_core.contracts.routing import ReasonCode
from venom_core.core.orchestrator.orchestrator_dispatch import _build_risk_context
from venom_core.core.routing_integration import build_routing_decision
from venom_core.services.execution_mode_planner import decide_execution_mode

pytestmark = [pytest.mark.performance]


class _DummyRouter:
    def __init__(self, *args, **kwargs):
        # Simulate realistic startup/alloc cost that cache should avoid.
        self._seed = [idx for idx in range(4096)]

    def route_task(self, task_type, prompt):
        return {
            "target": "cloud",
            "model_name": "gpt-4o-mini",
            "provider": "openai",
            "reason": "Tryb HYBRID: złożone zadanie CODING_COMPLEX -> CLOUD",
            "is_paid": True,
        }

    def calculate_complexity(self, prompt, task_type):
        return 8


class _DummyGovernance:
    def select_provider_with_fallback(self, preferred_provider, reason=None):
        return SimpleNamespace(
            allowed=True,
            provider="vllm",
            reason_code="FALLBACK_AUTH_ERROR",
            fallback_applied=True,
            user_message="fallback",
        )


def _percentile(samples: list[float], q: float) -> float:
    if not samples:
        return 0.0
    if q <= 0:
        return min(samples)
    if q >= 1:
        return max(samples)
    ordered = sorted(samples)
    index = int(q * (len(ordered) - 1))
    return ordered[index]


def _baseline_decide_execution_mode(request: TaskRequest, intent: str | None):
    forced_tool = str(request.forced_tool or "").strip().lower()
    normalized_intent = str(intent or "").strip().upper()
    if forced_tool in {"calendar", "github", "git", "file", "fs", "filesystem"}:
        return "api_skill"
    if normalized_intent in {
        "VERSION_CONTROL",
        "FILE_OPERATION",
        "DOCUMENTATION",
        "RELEASE_PROJECT",
        "STATUS_REPORT",
        "INFRA_STATUS",
        "TIME_REQUEST",
    }:
        return "api_skill"
    if forced_tool in {"browser", "web", "http", "network"}:
        return "browser_automation"
    if normalized_intent in {"RESEARCH", "KNOWLEDGE_SEARCH", "E2E_TESTING"}:
        return "browser_automation"
    if forced_tool in {"desktop", "vision", "ghost", "ui", "input"}:
        return "gui_fallback"
    if normalized_intent in {"DESKTOP_AUTOMATION", "VISION_CONTROL"}:
        return "gui_fallback"
    return "api_skill"


def _baseline_build_risk_context(
    request: TaskRequest, intent: str, tool_required: bool
):
    forced_tool = str(request.forced_tool or "").strip().lower()
    intent_upper = str(intent or "").strip().upper()
    return {
        "desktop": forced_tool in {"desktop", "vision", "ghost", "ui"}
        or intent_upper in {"DESKTOP_AUTOMATION", "VISION_CONTROL"},
        "fileops": forced_tool in {"file", "fs", "filesystem", "fileops"}
        or intent_upper
        in {"FILE_OPERATIONS", "FILESYSTEM_OPERATION", "CODE_GENERATION"},
        "shell": forced_tool in {"shell", "bash", "terminal", "command"}
        or intent_upper in {"SHELL_EXECUTION", "SYSTEM_DIAGNOSTICS"},
        "network": forced_tool in {"browser", "web", "http", "network"}
        or intent_upper in {"RESEARCH", "WEB_RESEARCH", "NETWORK_OPERATION"},
        "tool_required": tool_required,
    }


def _baseline_build_routing_decision(request, runtime_info, state_manager=None):
    from venom_core.core.routing_integration import (
        _REASON_CODE_FROM_GOVERNANCE,
        _build_fallback_chain,
        _resolve_decision_model,
        _to_reason_code,
        _to_runtime_target,
        _to_task_type,
    )

    router = _DummyRouter(state_manager=state_manager)
    task_type = _to_task_type(request)
    routing_info = router.route_task(task_type, request.content)
    complexity_score = float(router.calculate_complexity(request.content, task_type))
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

    return {
        "target_runtime": _to_runtime_target(selected_provider),
        "provider": selected_provider,
        "model": _resolve_decision_model(
            is_code_generation=str(request.forced_intent or "").strip().upper()
            == "CODE_GENERATION",
            selected_provider=selected_provider,
            routing_info=routing_info,
            runtime_info=runtime_info,
        ),
        "reason_code": reason_code,
        "complexity_score": complexity_score,
        "fallback_chain": _build_fallback_chain(
            preferred_provider=preferred_provider,
            selected_provider=selected_provider,
            fallback_applied=bool(governance_decision.fallback_applied),
        ),
    }


def _run_global_path(iterations: int, optimized: bool) -> list[float]:
    request_api = TaskRequest(
        content="implement complex orchestration flow",
        forced_intent="COMPLEX_PLANNING",
        forced_tool="github",
        forced_provider="openai",
    )
    runtime_info = SimpleNamespace(provider="ollama", model_name="gemma3:4b")

    class _StateManager:
        pass

    state_manager = _StateManager()
    if optimized:
        # Warm up cached router path before measuring p95.
        _ = build_routing_decision(
            request=request_api,
            runtime_info=runtime_info,
            state_manager=state_manager,
        )

    latencies_ms: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        if optimized:
            mode = decide_execution_mode(request_api, "RESEARCH").execution_mode
            risk = _build_risk_context(request_api, "RESEARCH", True)
            decision = build_routing_decision(
                request=request_api,
                runtime_info=runtime_info,
                state_manager=state_manager,
            )
            assert decision.reason_code == ReasonCode.FALLBACK_AUTH_ERROR
        else:
            mode = _baseline_decide_execution_mode(request_api, "RESEARCH")
            risk = _baseline_build_risk_context(request_api, "RESEARCH", True)
            decision = _baseline_build_routing_decision(
                request_api,
                runtime_info,
                state_manager=state_manager,
            )
            assert decision["reason_code"] == ReasonCode.FALLBACK_AUTH_ERROR
        assert mode in {"api_skill", "browser_automation", "gui_fallback"}
        assert risk["network"] is True
        latencies_ms.append((time.perf_counter() - start) * 1000.0)
    return latencies_ms


def _write_report(report: dict[str, float]) -> None:
    output = Path(
        os.getenv(
            "VENOM_202B_GLOBAL_P95_REPORT",
            "test-results/perf/202b-global-latency.json",
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def test_202b_global_hot_path_p95_improves_vs_baseline(monkeypatch):
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

    iterations = int(os.getenv("VENOM_202B_P95_ITERATIONS", "6000"))
    baseline = _run_global_path(iterations, optimized=False)
    optimized = _run_global_path(iterations, optimized=True)

    baseline_p95 = _percentile(baseline, 0.95)
    optimized_p95 = _percentile(optimized, 0.95)
    improvement_pct = (
        ((baseline_p95 - optimized_p95) / baseline_p95) * 100.0
        if baseline_p95 > 0
        else 0.0
    )

    report = {
        "samples": float(iterations),
        "baseline_p95_ms": round(baseline_p95, 4),
        "optimized_p95_ms": round(optimized_p95, 4),
        "improvement_pct": round(improvement_pct, 2),
    }
    _write_report(report)

    # 202B acceptance target: at least 20% p95 improvement against baseline.
    assert optimized_p95 <= baseline_p95 * 0.80, report
