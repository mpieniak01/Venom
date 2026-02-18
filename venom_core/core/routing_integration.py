"""Soft integration layer for routing contract in orchestrator submit flow."""

from __future__ import annotations

import time
from typing import Any

from venom_core.api.schemas.tasks import TaskRequest
from venom_core.contracts.routing import ReasonCode, RoutingDecision, RuntimeTarget
from venom_core.core.provider_governance import get_provider_governance
from venom_core.core.slash_commands import normalize_forced_provider
from venom_core.execution.model_router import HybridModelRouter, TaskType

_TASK_TYPE_FROM_FORCED_INTENT: dict[str, TaskType] = {
    "RESEARCH": TaskType.RESEARCH,
    "GENERAL_CHAT": TaskType.CHAT,
    "CODE_GENERATION": TaskType.CODING_SIMPLE,
    "COMPLEX_PLANNING": TaskType.CODING_COMPLEX,
    "ANALYSIS": TaskType.ANALYSIS,
    "GENERATION": TaskType.GENERATION,
    "SENSITIVE": TaskType.SENSITIVE,
}

_REASON_CODE_FROM_GOVERNANCE: dict[str, ReasonCode] = {
    "FALLBACK_AUTH_ERROR": ReasonCode.FALLBACK_AUTH_ERROR,
    "FALLBACK_BUDGET_EXCEEDED": ReasonCode.FALLBACK_BUDGET_EXCEEDED,
    "FALLBACK_RATE_LIMIT": ReasonCode.FALLBACK_RATE_LIMIT,
}


def _to_runtime_target(provider: str | None) -> RuntimeTarget | None:
    provider_key = (provider or "").strip().lower()
    if provider_key == "ollama":
        return RuntimeTarget.LOCAL_OLLAMA
    if provider_key == "vllm":
        return RuntimeTarget.LOCAL_VLLM
    if provider_key == "openai":
        return RuntimeTarget.CLOUD_OPENAI
    if provider_key == "google":
        return RuntimeTarget.CLOUD_GOOGLE
    return None


def _to_task_type(request: TaskRequest) -> TaskType:
    forced_intent = str(request.forced_intent or "").strip().upper()
    if forced_intent in _TASK_TYPE_FROM_FORCED_INTENT:
        return _TASK_TYPE_FROM_FORCED_INTENT[forced_intent]
    if request.forced_tool in {"browser", "web", "research"}:
        return TaskType.RESEARCH
    return TaskType.STANDARD


def _to_reason_code(routing_info: dict[str, Any]) -> ReasonCode:
    reason = str(routing_info.get("reason") or "").lower()
    if "sensitive" in reason:
        return ReasonCode.SENSITIVE_CONTENT_OVERRIDE
    if "complexity" in reason and "high" in reason:
        return ReasonCode.TASK_COMPLEXITY_HIGH
    if "complexity" in reason and "low" in reason:
        return ReasonCode.TASK_COMPLEXITY_LOW
    if "cloud" in str(routing_info.get("target", "")).lower():
        return ReasonCode.TASK_COMPLEXITY_HIGH
    return ReasonCode.DEFAULT_ECO_MODE


def build_routing_decision(
    *,
    request: TaskRequest,
    runtime_info: Any,
    state_manager: Any = None,
) -> RoutingDecision:
    """
    Build RoutingDecision for governance/policy/observability without changing runtime execution.
    """
    start = time.perf_counter()
    router = HybridModelRouter(state_manager=state_manager)
    task_type = _to_task_type(request)
    routing_info = router.route_task(task_type, request.content)
    complexity_score = float(router.calculate_complexity(request.content, task_type))
    is_sensitive = bool(
        task_type == TaskType.SENSITIVE or request.forced_intent == "SENSITIVE"
    )

    preferred_provider = normalize_forced_provider(request.forced_provider)
    if not preferred_provider:
        routed_provider = str(routing_info.get("provider", "")).strip().lower()
        if routed_provider in {"openai", "google", "ollama", "vllm"}:
            preferred_provider = routed_provider
        elif routed_provider == "local":
            preferred_provider = (
                str(getattr(runtime_info, "provider", "")).strip().lower() or "ollama"
            )
        else:
            preferred_provider = (
                str(getattr(runtime_info, "provider", "")).strip().lower() or "ollama"
            )

    governance = get_provider_governance()
    governance_decision = governance.select_provider_with_fallback(
        preferred_provider=preferred_provider,
        reason=str(routing_info.get("reason") or ""),
    )

    selected_provider = governance_decision.provider or preferred_provider
    reason_code = _REASON_CODE_FROM_GOVERNANCE.get(
        str(governance_decision.reason_code or ""),
        _to_reason_code(routing_info),
    )

    decision = RoutingDecision(
        target_runtime=_to_runtime_target(selected_provider),
        provider=selected_provider,
        model=str(
            routing_info.get("model_name") or getattr(runtime_info, "model_name", "")
        ),
        reason_code=reason_code,
        complexity_score=complexity_score,
        is_sensitive=is_sensitive,
        fallback_applied=bool(governance_decision.fallback_applied),
        fallback_chain=(
            [preferred_provider, selected_provider]
            if governance_decision.fallback_applied
            and selected_provider
            and selected_provider != preferred_provider
            else [preferred_provider]
            if preferred_provider
            else []
        ),
        policy_gate_passed=True,
        estimated_cost_usd=0.0,
        budget_remaining_usd=None,
        decision_latency_ms=(time.perf_counter() - start) * 1000.0,
        error_message=None
        if governance_decision.allowed
        else governance_decision.user_message,
    )
    return decision
