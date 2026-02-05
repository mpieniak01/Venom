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


async def run_task(
    orch: "Orchestrator",
    task_id: UUID,
    request: TaskRequest,
    fast_path: bool = False,
) -> None:
    context = request.content
    tool_required = False

    try:
        # --- 0. Init & Logging ---
        task = orch.state_manager.get_task(task_id)
        if task is None:
            logger.error("Zadanie %s nie istnieje", task_id)
            return

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

        orch._persist_session_context(task_id, request)

        # --- 1. Request Preprocessing ---
        await orch.context_builder.preprocess_request(task_id, request)
        request_content = request.content  # Update context after slash commands

        # --- 1.5. Perf Test Shortcut (Early) ---
        if orch._is_perf_test_prompt(request_content):
            await orch._complete_perf_test_task(task_id)
            logger.info("Zadanie %s zakończone w trybie perf-test", task_id)
            return

        # --- 2. Intent Classification (Early) ---
        orch.validator.validate_forced_tool(
            task_id, request.forced_tool, request.forced_intent
        )

        if request.forced_intent:
            intent = request.forced_intent
            intent_debug = {"source": "forced", "intent": request.forced_intent}
        else:
            # Optimize: Classify on request content instead of full context
            intent = await orch.intent_manager.classify_intent(request_content)
            intent_debug = getattr(orch.intent_manager, "last_intent_debug", {})

        # Intent Debug Logging
        if intent_debug:
            orch.state_manager.update_context(task_id, {"intent_debug": intent_debug})
            if orch.request_tracer:
                try:
                    details = json.dumps(intent_debug, ensure_ascii=False)
                except Exception:
                    details = str(intent_debug)
                orch.request_tracer.add_step(
                    task_id,
                    "DecisionGate",
                    "intent_debug",
                    status="ok",
                    details=details,
                )

        # --- 3. Build Context (Conditional) ---
        if intent in STATIC_INTENTS:
            # Fast Path: Skip heavy context building for templates
            context = request_content
            logger.info(f"Fast path: Skipping context build for intent {intent}")
            orch.state_manager.add_log(
                task_id, "🚀 Fast Path: Pominięto budowanie kontekstu"
            )
        else:
            # Normal Path: Full context with history/memory
            context = await orch.context_builder.build_context(
                task_id, request, fast_path
            )

        # Capture generation params log
        if request.generation_params:
            orch.state_manager.update_context(
                task_id, {"generation_params": request.generation_params}
            )
            logger.info(
                "Zapisano parametry generacji dla zadania %s: %s",
                task_id,
                request.generation_params,
            )

        # NON-LLM tracing metadata
        if (
            orch.request_tracer
            and intent in orch.NON_LLM_INTENTS
            and intent_debug.get("source") != "llm"
        ):
            orch.request_tracer.set_llm_metadata(
                task_id, provider=None, model=None, endpoint=None
            )
            orch.state_manager.update_context(
                task_id,
                {
                    "llm_runtime": {
                        "status": "skipped",
                        "error": None,
                        "last_success_at": None,
                    }
                },
            )

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

        # Metrics: Tool Required
        collector = metrics_module.metrics_collector
        if collector:
            if tool_required:
                collector.increment_tool_required_request()
            else:
                collector.increment_llm_only_request()

        # Handle Unsupported Agent
        if tool_required:
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

        # Validate Capabilities & Routing (Disabled for now as it causes regressions)
        # kernel_required = tool_required or intent in orch.KERNEL_FUNCTION_INTENTS
        # orch.validator.validate_capabilities(task_id, kernel_required, tool_required)
        # orch.validator.validate_routing(task_id, request, request.forced_provider)

        # --- 4. Context Enrichment (Lessons & Hidden Prompts) ---
        if intent not in orch.NON_LEARNING_INTENTS and not tool_required:
            context = await orch.context_builder.enrich_context_with_lessons(
                task_id, context
            )
            context = await orch.context_builder.add_hidden_prompts(
                task_id, context, intent
            )

            # Simple context preview trace
            if orch.request_tracer:
                max_len = 2000
                truncated = len(context) > max_len
                context_preview = (
                    context[:max_len] + "...(truncated)" if truncated else context
                )
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

        await orch._broadcast_event(
            event_type="AGENT_THOUGHT",
            message=f"Rozpoznano intencję: {intent}",
            data={"task_id": str(task_id), "intent": intent},
        )

        # --- 5. Execution ---
        orch._append_session_history(
            task_id,
            role="user",
            content=request.content,
            session_id=request.session_id,
        )

        stream_callback = orch.streaming_handler.create_stream_callback(task_id)
        stream_token = set_llm_stream_callback(stream_callback)

        try:
            strategy = ExecutionStrategy(orch)
            result = await strategy.execute(task_id, intent, context, request)
        finally:
            reset_llm_stream_callback(stream_token)

        # --- 6. Processing Results ---
        await orch.result_processor.process_success(
            task_id, result, intent, context, request, tool_required
        )

    except Exception as exc:
        await orch.result_processor.process_error(task_id, exc, request, context)


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
