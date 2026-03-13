import gc
import time
import tracemalloc

import pytest

from venom_core.api.schemas.tasks import TaskRequest
from venom_core.services.execution_mode_planner import (
    API_SKILL_INTENTS,
    API_SKILL_TOOLS,
    BROWSER_AUTOMATION_INTENTS,
    BROWSER_AUTOMATION_TOOLS,
    GUI_FALLBACK_INTENTS,
    GUI_FALLBACK_TOOLS,
    ExecutionModeDecision,
    decide_execution_mode,
)
from venom_core.services.execution_template_planner import (
    CRITICAL_BROWSER_KEYWORDS,
    FORCED_TOOL_TEMPLATE_MAP,
    INTENT_TEMPLATE_MAP,
    SMOKE_BROWSER_KEYWORDS,
    ExecutionTemplateDecision,
    resolve_api_skill_template,
    resolve_browser_profile,
)

pytestmark = [pytest.mark.performance]


def _baseline_decide_execution_mode(
    request: TaskRequest, intent: str | None
) -> ExecutionModeDecision:
    forced_tool = str(request.forced_tool or "").strip().lower()
    normalized_intent = str(intent or "").strip().upper()

    if forced_tool in API_SKILL_TOOLS:
        return ExecutionModeDecision(execution_mode="api_skill")
    if normalized_intent in API_SKILL_INTENTS:
        return ExecutionModeDecision(execution_mode="api_skill")
    if forced_tool in BROWSER_AUTOMATION_TOOLS:
        return ExecutionModeDecision(execution_mode="browser_automation")
    if normalized_intent in BROWSER_AUTOMATION_INTENTS:
        return ExecutionModeDecision(execution_mode="browser_automation")
    if forced_tool in GUI_FALLBACK_TOOLS:
        return ExecutionModeDecision(
            execution_mode="gui_fallback",
            fallback_reason="forced_gui_tool",
            reason_code="EXECUTION_MODE_GUI_FALLBACK_FORCED_TOOL",
        )
    if normalized_intent in GUI_FALLBACK_INTENTS:
        return ExecutionModeDecision(
            execution_mode="gui_fallback",
            fallback_reason="intent_requires_gui_path",
            reason_code="EXECUTION_MODE_GUI_FALLBACK_INTENT",
        )
    return ExecutionModeDecision(execution_mode="api_skill")


def _baseline_resolve_api_skill_template(
    request: TaskRequest, intent: str
) -> ExecutionTemplateDecision | None:
    forced_tool = str(request.forced_tool or "").strip().lower()
    normalized_intent = str(intent or "").strip().upper()

    forced_tool_template = FORCED_TOOL_TEMPLATE_MAP.get(forced_tool)
    if forced_tool_template is not None:
        return ExecutionTemplateDecision(
            template_id=forced_tool_template,
            source="forced_tool",
        )

    intent_template = INTENT_TEMPLATE_MAP.get(normalized_intent)
    if intent_template is not None:
        return ExecutionTemplateDecision(
            template_id=intent_template,
            source="intent",
        )

    return None


def _baseline_resolve_browser_profile(request: TaskRequest, intent: str) -> str:
    normalized_intent = str(intent or "").strip().upper()
    content_lower = str(request.content or "").strip().lower()
    tokens = set(content_lower.replace("_", " ").replace("-", " ").split())

    if normalized_intent == "E2E_TESTING" or tokens.intersection(
        CRITICAL_BROWSER_KEYWORDS
    ):
        return "critical"
    if tokens.intersection(SMOKE_BROWSER_KEYWORDS):
        return "smoke"
    return "functional"


def _run_planner_mix(
    iterations: int,
    decide_fn,
    template_fn,
    profile_fn,
) -> None:
    api_request = TaskRequest(content="edit repository files", forced_tool="github")
    browser_request = TaskRequest(content="run smoke checkout test")
    gui_request = TaskRequest(content="click submit", forced_tool="ui")

    for _ in range(iterations):
        api_decision = decide_fn(api_request, "VERSION_CONTROL")
        assert api_decision.execution_mode == "api_skill"

        template_decision = template_fn(api_request, "VERSION_CONTROL")
        assert template_decision is not None
        assert template_decision.template_id == "github_repo_ops_v1"

        browser_decision = decide_fn(browser_request, "RESEARCH")
        assert browser_decision.execution_mode == "browser_automation"
        assert profile_fn(browser_request, "RESEARCH") == "smoke"

        gui_decision = decide_fn(gui_request, "GENERAL_CHAT")
        assert gui_decision.execution_mode == "gui_fallback"


def _measure_elapsed(iterations: int, decide_fn, template_fn, profile_fn) -> float:
    start = time.perf_counter()
    _run_planner_mix(iterations, decide_fn, template_fn, profile_fn)
    return time.perf_counter() - start


def _measure_peak_memory(iterations: int, decide_fn, template_fn, profile_fn) -> int:
    gc.collect()
    tracemalloc.start()
    _run_planner_mix(iterations, decide_fn, template_fn, profile_fn)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def test_execution_planners_reduce_hot_path_latency_and_peak_memory() -> None:
    iterations = 5000

    _run_planner_mix(
        200, decide_execution_mode, resolve_api_skill_template, resolve_browser_profile
    )

    baseline_elapsed = _measure_elapsed(
        iterations,
        _baseline_decide_execution_mode,
        _baseline_resolve_api_skill_template,
        _baseline_resolve_browser_profile,
    )
    optimized_elapsed = _measure_elapsed(
        iterations,
        decide_execution_mode,
        resolve_api_skill_template,
        resolve_browser_profile,
    )

    baseline_peak = _measure_peak_memory(
        iterations,
        _baseline_decide_execution_mode,
        _baseline_resolve_api_skill_template,
        _baseline_resolve_browser_profile,
    )
    optimized_peak = _measure_peak_memory(
        iterations,
        decide_execution_mode,
        resolve_api_skill_template,
        resolve_browser_profile,
    )

    assert optimized_elapsed <= baseline_elapsed
    assert optimized_peak <= baseline_peak
