"""Task execution and dispatch logic for Orchestrator."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from venom_core.agents.base import reset_llm_stream_callback, set_llm_stream_callback
from venom_core.config import SETTINGS
from venom_core.core import metrics as metrics_module
from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.policy_autonomy_contract import (
    build_policy_block_payload,
    to_audit_details,
)
from venom_core.core.policy_gate import (
    PolicyDecision,
    PolicyEvaluationContext,
    policy_gate,
)
from venom_core.core.tracer import TraceStatus
from venom_core.services.audit_stream import get_audit_stream
from venom_core.services.execution_mode_planner import (
    decide_execution_mode,
    resolve_gui_fallback_contract,
)
from venom_core.services.execution_template_planner import (
    resolve_api_skill_template,
    resolve_browser_execution_contract,
    resolve_browser_profile,
)
from venom_core.utils.logger import get_logger

from .constants import (
    DEFAULT_USER_ID,
    HISTORY_SUMMARY_TRIGGER_CHARS,
    HISTORY_SUMMARY_TRIGGER_MSGS,
    LEARNING_LOG_PATH,
    MAX_LEARNING_SNIPPET,
    STATIC_INTENTS,
    SUMMARY_STRATEGY_DEFAULT,
)

if TYPE_CHECKING:
    from .orchestrator_core import Orchestrator

from .task_pipeline.execution_strategy import ExecutionStrategy

logger = get_logger(__name__)

_RISK_DESKTOP_TOOLS = frozenset({"desktop", "vision", "ghost", "ui"})
_RISK_DESKTOP_INTENTS = frozenset({"DESKTOP_AUTOMATION", "VISION_CONTROL"})
_RISK_FILEOPS_TOOLS = frozenset({"file", "fs", "filesystem", "fileops"})
_RISK_FILEOPS_INTENTS = frozenset(
    {"FILE_OPERATIONS", "FILESYSTEM_OPERATION", "CODE_GENERATION"}
)
_RISK_SHELL_TOOLS = frozenset({"shell", "bash", "terminal", "command"})
_RISK_SHELL_INTENTS = frozenset({"SHELL_EXECUTION", "SYSTEM_DIAGNOSTICS"})
_RISK_NETWORK_TOOLS = frozenset({"browser", "web", "http", "network"})
_RISK_NETWORK_INTENTS = frozenset({"RESEARCH", "WEB_RESEARCH", "NETWORK_OPERATION"})


def _normalize_lower(value: object | None) -> str:
    return str(value or "").strip().lower()


def _normalize_upper(value: object | None) -> str:
    return str(value or "").strip().upper()


async def _handle_policy_block_global_pre_execution(
    orch: "Orchestrator",
    task_id: UUID,
    request: TaskRequest,
    policy_context: PolicyEvaluationContext,
) -> bool:
    """
    Obsługuje blokadę policy na globalnym checkpointcie pre-execution.

    Args:
        orch: Orchestrator
        task_id: ID zadania
        request: Żądanie zadania
        policy_context: Kontekst ewaluacji policy

    Returns:
        True jeśli flow został przerwany (zadanie zablokowane), False jeśli można kontynuować
    """
    if not policy_gate.enabled:
        return False

    policy_result = policy_gate.evaluate_global_pre_execution(policy_context)

    if policy_result.decision != PolicyDecision.BLOCK:
        return False

    # Zadanie zostało zablokowane
    logger.warning(
        f"Policy gate blocked pre-execution for task {task_id}: {policy_result.reason_code}"
    )
    reason_code = (
        getattr(policy_result.reason_code, "value", policy_result.reason_code)
        if policy_result.reason_code
        else None
    )
    payload = build_policy_block_payload(
        reason_code=reason_code,
        user_message=policy_result.message,
        remediation_hint=getattr(policy_result, "remediation_hint", None),
        phase="global_pre_execution",
        operation="orchestrator_execution",
        task_id=str(task_id),
        intent=getattr(policy_context, "intent", None),
        planned_provider=getattr(policy_context, "planned_provider", None),
        forced_provider=getattr(policy_context, "forced_provider", None),
        forced_tool=getattr(policy_context, "forced_tool", None),
        session_id=getattr(policy_context, "session_id", None),
    )
    get_audit_stream().publish(
        source="core.policy",
        action="policy.blocked.global_pre_execution",
        actor="system",
        status="blocked",
        details=to_audit_details(payload),
    )
    orch.state_manager.add_log(
        task_id,
        f"🚫 Policy gate blocked pre-execution: {policy_result.message}",
    )

    # Store policy block details in task context for UI retrieval
    orch.state_manager.update_context(
        task_id,
        {
            "policy_blocked": True,
            "reason_code": policy_result.reason_code.value
            if policy_result.reason_code
            else None,
            "user_message": policy_result.message,
            "remediation_hint": getattr(policy_result, "remediation_hint", None),
            "technical_context": payload.technical_context.model_dump(
                exclude_none=True
            ),
        },
    )

    await orch.state_manager.update_status(
        task_id,
        TaskStatus.FAILED,
        result=policy_result.message,
    )

    # Add assistant session history entry with policy block details
    orch._append_session_history(
        task_id,
        role="assistant",
        content=policy_result.message,
        session_id=request.session_id,
        policy_blocked=True,
        reason_code=policy_result.reason_code.value
        if policy_result.reason_code
        else None,
        user_message=policy_result.message,
    )

    # Increment policy blocked metric
    if metrics_module.metrics_collector:
        metrics_module.metrics_collector.increment_policy_blocked(
            reason_code=reason_code,
        )

    if orch.request_tracer:
        orch.request_tracer.update_status(task_id, TraceStatus.FAILED)
        orch.request_tracer.add_step(
            task_id,
            "PolicyGate",
            "block_global_pre_execution",
            status="blocked",
            details=f"Reason: {policy_result.reason_code}",
        )

    return True


def _resolve_planned_provider(
    orch: "Orchestrator", task_id: UUID, request: TaskRequest
) -> str | None:
    task = orch.state_manager.get_task(task_id)
    routing_decision = (
        getattr(task, "context_history", {}).get("routing_decision", {})
        if task is not None
        else {}
    )
    routed_provider = str(routing_decision.get("provider") or "").strip() or None
    return request.forced_provider or routed_provider


def _build_risk_context(
    request: TaskRequest, intent: str, tool_required: bool
) -> dict[str, bool]:
    forced_tool = _normalize_lower(request.forced_tool)
    intent_upper = _normalize_upper(intent)
    return {
        "desktop": forced_tool in _RISK_DESKTOP_TOOLS
        or intent_upper in _RISK_DESKTOP_INTENTS,
        "fileops": forced_tool in _RISK_FILEOPS_TOOLS
        or intent_upper in _RISK_FILEOPS_INTENTS,
        "shell": forced_tool in _RISK_SHELL_TOOLS
        or intent_upper in _RISK_SHELL_INTENTS,
        "network": forced_tool in _RISK_NETWORK_TOOLS
        or intent_upper in _RISK_NETWORK_INTENTS,
        "tool_required": tool_required,
    }


async def _prepare_intent_and_context(
    orch: "Orchestrator",
    task_id: UUID,
    request: TaskRequest,
    request_content: str,
    fast_path: bool,
) -> tuple[str, str, bool, dict]:
    """
    Klasyfikuje intencję i buduje kontekst.

    Args:
        orch: Orchestrator
        task_id: ID zadania
        request: Żądanie zadania
        request_content: Treść żądania
        fast_path: Czy użyć fast path

    Returns:
        Krotka (intent, context, tool_required, intent_debug)
    """
    intent, intent_debug = await _classify_intent_and_log(
        orch, task_id, request, request_content
    )

    context = await _build_context_for_intent(
        orch, task_id, request, request_content, intent, fast_path
    )

    context_updates: dict[str, object] = {}
    if intent_debug:
        context_updates["intent_debug"] = intent_debug

    context_updates.update(_collect_generation_params_context_updates(task_id, request))
    context_updates.update(
        _collect_non_llm_metadata_updates(orch, task_id, intent, intent_debug)
    )
    context_updates.update(
        _build_execution_mode_metadata(orch, task_id, request, intent)
    )

    tool_required, intent, tool_updates = _evaluate_tool_requirement_and_routing(
        orch, task_id, intent
    )
    context_updates.update(tool_updates)

    if context_updates:
        orch.state_manager.update_context(task_id, context_updates)

    return intent, context, tool_required, intent_debug


def _build_execution_mode_metadata(
    orch: "Orchestrator", task_id: UUID, request: TaskRequest, intent: str
) -> dict[str, object]:
    decision = decide_execution_mode(request=request, intent=intent)
    collector = metrics_module.metrics_collector
    if collector is not None:
        collector.increment_execution_mode_selected(decision.execution_mode)

    template_decision = None
    browser_profile = None
    browser_execution_contract: dict[str, object] | None = None
    gui_fallback_contract: dict[str, object] | None = None
    if decision.execution_mode == "api_skill":
        template_decision = resolve_api_skill_template(request=request, intent=intent)
    elif decision.execution_mode == "browser_automation":
        browser_profile = resolve_browser_profile(request=request, intent=intent)
        browser_execution_contract = resolve_browser_execution_contract(browser_profile)
    elif decision.execution_mode == "gui_fallback":
        gui_fallback_contract = resolve_gui_fallback_contract(decision)

    updates: dict[str, object] = {
        "execution_mode": decision.execution_mode,
        "fallback_reason": decision.fallback_reason,
        "execution_mode_reason_code": decision.reason_code,
    }
    if template_decision is not None:
        updates["execution_template"] = {
            "template_id": template_decision.template_id,
            "source": template_decision.source,
        }
    if browser_profile is not None:
        updates["browser_profile"] = browser_profile
    if browser_execution_contract is not None:
        updates["browser_execution_contract"] = browser_execution_contract
    if gui_fallback_contract is not None:
        updates["gui_fallback_contract"] = gui_fallback_contract

    gui_fail_closed: object | None = None
    if gui_fallback_contract:
        safety_config = gui_fallback_contract.get("safety")
        if isinstance(safety_config, dict):
            gui_fail_closed = safety_config.get("critical_steps_fail_closed")

    if orch.request_tracer:
        details = {
            "execution_mode": decision.execution_mode,
            "fallback_reason": decision.fallback_reason,
            "reason_code": decision.reason_code,
            "template_id": getattr(template_decision, "template_id", None),
            "browser_profile": browser_profile,
            "browser_timeout_seconds": (
                browser_execution_contract.get("timeout_seconds")
                if browser_execution_contract
                else None
            ),
            "gui_fail_closed": gui_fail_closed,
        }
        orch.request_tracer.add_step(
            task_id,
            "DecisionGate",
            "execution_mode_selector",
            status="ok",
            details=json.dumps(details, ensure_ascii=False),
        )

    return updates


def _emit_classification_trace(
    orch: "Orchestrator", task_id: UUID, intent: str
) -> None:
    """
    Emituje ślad klasyfikacji intencji.

    Args:
        orch: Orchestrator
        task_id: ID zadania
        intent: Intencja
    """
    orch.state_manager.add_log(
        task_id, f"Sklasyfikowana intencja: {intent} - {datetime.now().isoformat()}"
    )
    if orch.request_tracer:
        orch.request_tracer.add_step(
            task_id,
            "Orchestrator",
            "classify_intent",
            status="ok",
            details=f"Intent: {intent}",
        )


def _trace_context_preview(orch: "Orchestrator", task_id: UUID, context: str) -> None:
    if not orch.request_tracer:
        return
    max_len = 2000
    truncated = len(context) > max_len
    context_preview = context[:max_len] + "...(truncated)" if truncated else context
    orch.request_tracer.add_step(
        task_id,
        "DecisionGate",
        "context_preview",
        status="ok",
        details=json.dumps(
            {
                "mode": "normal",
                "prompt_context_preview": context_preview,
                "prompt_context_truncated": truncated,
            },
            ensure_ascii=False,
        ),
    )


async def run_task(
    orch: "Orchestrator",
    task_id: UUID,
    request: TaskRequest,
    fast_path: bool = False,
) -> None:
    context = request.content
    tool_required = False

    try:
        task = await _initialize_task_execution(orch, task_id)
        if task is None:
            return

        orch._persist_session_context(task_id, request)

        await orch.context_builder.preprocess_request(task_id, request)
        request_content = request.content

        if orch._is_perf_test_prompt(request_content):
            await orch._complete_perf_test_task(task_id)
            logger.info("Zadanie %s zakończone w trybie perf-test", task_id)
            return

        orch.validator.validate_forced_tool(
            task_id, request.forced_tool, request.forced_intent
        )

        # Prepare intent and context
        (
            intent,
            context,
            tool_required,
            intent_debug,
        ) = await _prepare_intent_and_context(
            orch, task_id, request, request_content, fast_path
        )

        if intent not in orch.NON_LEARNING_INTENTS and not tool_required:
            context = await orch.context_builder.enrich_context_with_lessons(
                task_id, context, intent=intent
            )
            context = await orch.context_builder.add_hidden_prompts(
                task_id, context, intent
            )
            _trace_context_preview(orch, task_id, context)

        _emit_classification_trace(orch, task_id, intent)

        await _broadcast_intent(orch, task_id, intent)
        orch._append_session_history(
            task_id,
            role="user",
            content=request.content,
            session_id=request.session_id,
        )

        planned_provider = _resolve_planned_provider(orch, task_id, request)
        planned_tools: list[str] = []
        if request.forced_tool:
            planned_tools.append(request.forced_tool)

        policy_context = PolicyEvaluationContext(
            content=request.content,
            intent=intent,
            planned_provider=planned_provider,
            planned_tools=planned_tools,
            session_id=request.session_id,
            forced_tool=request.forced_tool,
            forced_provider=request.forced_provider,
            phase="global_pre_execution",
            risk_context=_build_risk_context(request, intent, tool_required),
        )

        # Single global checkpoint before runtime execution.
        if await _handle_policy_block_global_pre_execution(
            orch, task_id, request, policy_context
        ):
            return

        result = await _execute_with_stream_callback(
            orch, task_id, intent, context, request
        )

        await orch.result_processor.process_success(
            task_id, result, intent, context, request, tool_required
        )

    except Exception as exc:
        await orch.result_processor.process_error(task_id, exc, request, context)


async def _initialize_task_execution(orch: "Orchestrator", task_id: UUID):
    task = orch.state_manager.get_task(task_id)
    if task is None:
        logger.error("Zadanie %s nie istnieje", task_id)
        return None
    await orch.state_manager.update_status(task_id, TaskStatus.PROCESSING)
    orch.state_manager.add_log(
        task_id, f"Rozpoczęto przetwarzanie: {datetime.now().isoformat()}"
    )
    if orch.request_tracer:
        orch.request_tracer.update_status(task_id, TraceStatus.PROCESSING)
        await orch._trace_step_async(
            task_id, "Orchestrator", "start_processing", status="ok"
        )
    await orch._broadcast_event(
        event_type="TASK_STARTED",
        message=f"Rozpoczynam przetwarzanie zadania {task_id}",
        data={"task_id": str(task_id)},
    )
    logger.info("Rozpoczynam przetwarzanie zadania %s", task_id)
    return task


async def _classify_intent_and_log(
    orch: "Orchestrator", task_id: UUID, request: TaskRequest, request_content: str
) -> tuple[str, dict]:
    if request.forced_intent:
        intent = request.forced_intent
        intent_debug = {"source": "forced", "intent": request.forced_intent}
    else:
        intent = await orch.intent_manager.classify_intent(request_content)
        intent_debug = getattr(orch.intent_manager, "last_intent_debug", {})
    if intent_debug and orch.request_tracer:
        try:
            details = json.dumps(intent_debug, ensure_ascii=False)
        except Exception:
            details = str(intent_debug)
        orch.request_tracer.add_step(
            task_id, "DecisionGate", "intent_debug", status="ok", details=details
        )
    return intent, intent_debug


async def _build_context_for_intent(
    orch: "Orchestrator",
    task_id: UUID,
    request: TaskRequest,
    request_content: str,
    intent: str,
    fast_path: bool,
) -> str:
    if intent in STATIC_INTENTS:
        logger.info(f"Fast path: Skipping context build for intent {intent}")
        orch.state_manager.add_log(
            task_id, "🚀 Fast Path: Pominięto budowanie kontekstu"
        )
        return request_content
    return await orch.context_builder.build_context(task_id, request, fast_path)


def _collect_generation_params_context_updates(
    task_id: UUID, request: TaskRequest
) -> dict[str, object]:
    if not request.generation_params:
        return {}
    logger.info(
        "Zapisano parametry generacji dla zadania %s: %s",
        task_id,
        request.generation_params,
    )
    return {"generation_params": request.generation_params}


def _collect_non_llm_metadata_updates(
    orch: "Orchestrator", task_id: UUID, intent: str, intent_debug: dict
) -> dict[str, object]:
    if not orch.request_tracer:
        return {}
    if intent not in orch.NON_LLM_INTENTS or intent_debug.get("source") == "llm":
        return {}
    orch.request_tracer.set_llm_metadata(
        task_id, provider=None, model=None, endpoint=None
    )
    return {
        "llm_runtime": {
            "status": "skipped",
            "error": None,
            "last_success_at": None,
        }
    }


def _evaluate_tool_requirement_and_routing(
    orch: "Orchestrator", task_id: UUID, intent: str
) -> tuple[bool, str, dict[str, object]]:
    tool_required = orch.intent_manager.requires_tool(intent)
    tool_requirement_update: dict[str, object] = {
        "tool_requirement": {"required": tool_required, "intent": intent}
    }
    if orch.request_tracer:
        orch.request_tracer.add_step(
            task_id,
            "DecisionGate",
            "tool_requirement",
            status="ok",
            details=f"Tool required: {tool_required}",
        )

    collector = metrics_module.metrics_collector
    if collector:
        if tool_required:
            collector.increment_tool_required_request()
        else:
            collector.increment_llm_only_request()

    if not tool_required:
        return tool_required, intent, tool_requirement_update

    agent = orch.task_dispatcher.agent_map.get(intent)
    if agent is None or agent.__class__.__name__ == "UnsupportedAgent":
        orch.state_manager.add_log(
            task_id,
            f"Brak narzędzia dla intencji {intent} - routing do UnsupportedAgent",
        )
        if orch.request_tracer:
            orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "route_unsupported",
                status="ok",
                details=f"Tool required but missing for intent={intent}",
            )
        intent = "UNSUPPORTED_TASK"
    return tool_required, intent, tool_requirement_update


async def _broadcast_intent(orch: "Orchestrator", task_id: UUID, intent: str) -> None:
    await orch._broadcast_event(
        event_type="AGENT_THOUGHT",
        message=f"Rozpoznano intencję: {intent}",
        data={"task_id": str(task_id), "intent": intent},
    )


async def _execute_with_stream_callback(
    orch: "Orchestrator", task_id: UUID, intent: str, context: str, request: TaskRequest
):
    stream_callback = orch.streaming_handler.create_stream_callback(task_id)
    stream_token = set_llm_stream_callback(stream_callback)
    try:
        strategy = ExecutionStrategy(orch)
        return await strategy.execute(task_id, intent, context, request)
    finally:
        reset_llm_stream_callback(stream_token)


def append_learning_log(
    orch: "Orchestrator",
    task_id: UUID,
    intent: str,
    prompt: str,
    result: str,
    success: bool,
    error: str = "",
) -> None:
    log_path = getattr(
        sys.modules.get("venom_core.core.orchestrator"),
        "LEARNING_LOG_PATH",
        LEARNING_LOG_PATH,
    )
    entry = {
        "task_id": str(task_id),
        "timestamp": datetime.now().isoformat(),
        "intent": intent,
        "tool_required": False,
        "success": success,
        "need": (prompt or "")[:MAX_LEARNING_SNIPPET],
        "outcome": (result or "")[:MAX_LEARNING_SNIPPET],
        "error": (error or "")[:MAX_LEARNING_SNIPPET],
        "fast_path_hint": "",
        "tags": [intent, "llm_only", "success" if success else "failure"],
    }

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        orch.state_manager.add_log(task_id, f"🧠 Zapisano wpis nauki do {log_path}")
        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_learning_logged()
    except Exception as exc:
        logger.warning("Nie udało się zapisać wpisu nauki: %s", exc)


def ensure_session_summary(orch: "Orchestrator", task_id: UUID, task) -> None:
    try:
        full_history = task.context_history.get("session_history_full") or []
        if not full_history:
            return
        raw_text = "\n".join(
            f"{entry.get('role', '')}: {entry.get('content', '')}"
            for entry in full_history
        )
        if (
            len(full_history) < HISTORY_SUMMARY_TRIGGER_MSGS
            and len(raw_text) < HISTORY_SUMMARY_TRIGGER_CHARS
        ):
            return

        strategy = getattr(SETTINGS, "SUMMARY_STRATEGY", SUMMARY_STRATEGY_DEFAULT)
        if strategy == "heuristic_only":
            summary = orch._heuristic_summary(full_history)
        else:
            summary = orch._summarize_history_llm(raw_text) or orch._heuristic_summary(
                full_history
            )
        if not summary:
            return

        orch.state_manager.update_context(task_id, {"session_summary": summary})
        orch.session_handler._memory_upsert(
            summary,
            metadata={
                "type": "summary",
                "session_id": task.context_history.get("session", {}).get("session_id")
                or "default_session",
                "user_id": DEFAULT_USER_ID,
                "pinned": True,
            },
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Nie udało się wygenerować streszczenia sesji: %s", exc)
