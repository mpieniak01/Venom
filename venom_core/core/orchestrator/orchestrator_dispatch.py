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
from venom_core.core.policy_gate import (
    PolicyDecision,
    PolicyEvaluationContext,
    policy_gate,
)
from venom_core.core.tracer import TraceStatus
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
        intent, intent_debug = await _classify_intent_and_log(
            orch, task_id, request, request_content
        )
        context = await _build_context_for_intent(
            orch, task_id, request, request_content, intent, fast_path
        )
        _store_generation_params_if_present(orch, task_id, request)
        _set_non_llm_metadata_if_applicable(orch, task_id, intent, intent_debug)

        tool_required, intent = _evaluate_tool_requirement_and_routing(
            orch, task_id, intent
        )

        if intent not in orch.NON_LEARNING_INTENTS and not tool_required:
            context = await orch.context_builder.enrich_context_with_lessons(
                task_id, context, intent=intent
            )
            context = await orch.context_builder.add_hidden_prompts(
                task_id, context, intent
            )
            _trace_context_preview(orch, task_id, context)

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

        await _broadcast_intent(orch, task_id, intent)
        orch._append_session_history(
            task_id,
            role="user",
            content=request.content,
            session_id=request.session_id,
        )

        # Policy Gate: Check before tool execution
        if policy_gate.enabled and tool_required:
            policy_context = PolicyEvaluationContext(
                content=request.content,
                intent=intent,
                planned_tools=[request.forced_tool] if request.forced_tool else [],
                session_id=request.session_id,
                forced_tool=request.forced_tool,
                forced_provider=request.forced_provider,
            )
            policy_result = policy_gate.evaluate_before_tool_execution(policy_context)

            if policy_result.decision == PolicyDecision.BLOCK:
                logger.warning(
                    f"Policy gate blocked tool execution for task {task_id}: {policy_result.reason_code}"
                )
                orch.state_manager.add_log(
                    task_id,
                    f"🚫 Policy gate blocked tool execution: {policy_result.message}",
                )
                await orch.state_manager.update_status(
                    task_id,
                    TaskStatus.FAILED,
                    result=policy_result.message,
                )

                if orch.request_tracer:
                    orch.request_tracer.update_status(task_id, "failed")
                    orch.request_tracer.add_step(
                        task_id,
                        "PolicyGate",
                        "block_before_tool_execution",
                        status="blocked",
                        details=f"Reason: {policy_result.reason_code}",
                    )

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
    if intent_debug:
        orch.state_manager.update_context(task_id, {"intent_debug": intent_debug})
        if orch.request_tracer:
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


def _store_generation_params_if_present(
    orch: "Orchestrator", task_id: UUID, request: TaskRequest
) -> None:
    if not request.generation_params:
        return
    orch.state_manager.update_context(
        task_id, {"generation_params": request.generation_params}
    )
    logger.info(
        "Zapisano parametry generacji dla zadania %s: %s",
        task_id,
        request.generation_params,
    )


def _set_non_llm_metadata_if_applicable(
    orch: "Orchestrator", task_id: UUID, intent: str, intent_debug: dict
) -> None:
    if not orch.request_tracer:
        return
    if intent not in orch.NON_LLM_INTENTS or intent_debug.get("source") == "llm":
        return
    orch.request_tracer.set_llm_metadata(
        task_id, provider=None, model=None, endpoint=None
    )
    orch.state_manager.update_context(
        task_id,
        {"llm_runtime": {"status": "skipped", "error": None, "last_success_at": None}},
    )


def _evaluate_tool_requirement_and_routing(
    orch: "Orchestrator", task_id: UUID, intent: str
) -> tuple[bool, str]:
    tool_required = orch.intent_manager.requires_tool(intent)
    orch.state_manager.update_context(
        task_id, {"tool_requirement": {"required": tool_required, "intent": intent}}
    )
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
        return tool_required, intent

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
    return tool_required, intent


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
