"""Soft integration layer for routing contract in orchestrator submit flow."""

from __future__ import annotations

import os
import threading
import time
from typing import Any
from weakref import WeakKeyDictionary

from venom_core.api.schemas.tasks import TaskRequest
from venom_core.contracts.routing import ReasonCode, RoutingDecision, RuntimeTarget
from venom_core.core.provider_governance import get_provider_governance
from venom_core.core.slash_commands import normalize_forced_provider
from venom_core.execution.model_router import HybridModelRouter, TaskType
from venom_core.services.feedback_loop_policy import (
    FEEDBACK_LOOP_REQUESTED_ALIAS,
    is_feedback_loop_ready,
)

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

_KNOWN_PROVIDERS = {"openai", "google", "ollama", "vllm"}
_RESEARCH_TOOLS = {"browser", "web", "research"}
_RUNTIME_TARGET_BY_PROVIDER: dict[str, RuntimeTarget] = {
    "ollama": RuntimeTarget.LOCAL_OLLAMA,
    "vllm": RuntimeTarget.LOCAL_VLLM,
    "openai": RuntimeTarget.CLOUD_OPENAI,
    "google": RuntimeTarget.CLOUD_GOOGLE,
}
_ROUTER_CACHE: "WeakKeyDictionary[Any, tuple[int, HybridModelRouter]]" = (
    WeakKeyDictionary()
)
_ROUTER_CACHE_NO_STATE: dict[int, HybridModelRouter] = {}
_ROUTER_CACHE_LOCK = threading.Lock()


def _router_cache_enabled() -> bool:
    raw = os.getenv("VENOM_ROUTER_CACHE_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _build_fallback_chain(
    *,
    preferred_provider: str,
    selected_provider: str,
    fallback_applied: bool,
) -> list[str]:
    if not preferred_provider:
        return []
    if (
        fallback_applied
        and selected_provider
        and selected_provider != preferred_provider
    ):
        return [preferred_provider, selected_provider]
    return [preferred_provider]


def _to_runtime_target(provider: str | None) -> RuntimeTarget | None:
    provider_key = (provider or "").strip().lower()
    return _RUNTIME_TARGET_BY_PROVIDER.get(provider_key)


def _to_task_type(request: TaskRequest) -> TaskType:
    forced_intent = str(request.forced_intent or "").strip().upper()
    if forced_intent in _TASK_TYPE_FROM_FORCED_INTENT:
        return _TASK_TYPE_FROM_FORCED_INTENT[forced_intent]
    forced_tool = str(request.forced_tool or "").strip().lower()
    if forced_tool in _RESEARCH_TOOLS:
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


def _resolve_decision_model(
    *,
    is_code_generation: bool,
    selected_provider: str,
    routing_info: dict[str, Any],
    runtime_info: Any,
) -> str:
    base_model = str(
        routing_info.get("model_name") or getattr(runtime_info, "model_name", "")
    )
    if not is_code_generation:
        return base_model
    if selected_provider != "ollama":
        return base_model
    if is_feedback_loop_ready(base_model):
        return base_model
    return FEEDBACK_LOOP_REQUESTED_ALIAS


def _get_router(state_manager: Any) -> HybridModelRouter:
    router_cls = HybridModelRouter
    if not _router_cache_enabled():
        return router_cls(state_manager=state_manager)

    with _ROUTER_CACHE_LOCK:
        router_cls_id = id(router_cls)
        if state_manager is None:
            cached_router = _ROUTER_CACHE_NO_STATE.get(router_cls_id)
            if cached_router is not None:
                return cached_router
            router = router_cls(state_manager=state_manager)
            _ROUTER_CACHE_NO_STATE[router_cls_id] = router
            return router

        try:
            cached_entry = _ROUTER_CACHE.get(state_manager)
        except TypeError:
            return router_cls(state_manager=state_manager)

        if cached_entry is not None and cached_entry[0] == router_cls_id:
            return cached_entry[1]

        router = router_cls(state_manager=state_manager)
        _ROUTER_CACHE[state_manager] = (router_cls_id, router)
        return router


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
    router = _get_router(state_manager)
    task_type = _to_task_type(request)
    request_content = request.content
    routing_info = router.route_task(task_type, request_content)
    complexity_score = float(router.calculate_complexity(request_content, task_type))
    forced_intent_upper = str(request.forced_intent or "").strip().upper()
    is_sensitive = bool(
        task_type == TaskType.SENSITIVE or forced_intent_upper == "SENSITIVE"
    )

    preferred_provider = normalize_forced_provider(request.forced_provider)
    if not preferred_provider:
        routed_provider = str(routing_info.get("provider", "")).strip().lower()
        if routed_provider in _KNOWN_PROVIDERS:
            preferred_provider = routed_provider
        else:
            preferred_provider = (
                str(getattr(runtime_info, "provider", "")).strip().lower() or "ollama"
            )

    governance = get_provider_governance()
    routing_reason = str(routing_info.get("reason") or "")
    governance_decision = governance.select_provider_with_fallback(
        preferred_provider=preferred_provider,
        reason=routing_reason,
    )

    selected_provider = (
        str(governance_decision.provider or preferred_provider or "").strip().lower()
    )
    reason_code = _REASON_CODE_FROM_GOVERNANCE.get(
        str(governance_decision.reason_code or ""),
        _to_reason_code(routing_info),
    )

    decision = RoutingDecision(
        target_runtime=_to_runtime_target(selected_provider),
        provider=selected_provider,
        model=_resolve_decision_model(
            is_code_generation=forced_intent_upper == "CODE_GENERATION",
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
        error_message=None
        if governance_decision.allowed
        else governance_decision.user_message,
    )
    return decision
