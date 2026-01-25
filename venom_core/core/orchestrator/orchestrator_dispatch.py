"""Task execution and dispatch logic for Orchestrator."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from venom_core.agents.base import reset_llm_stream_callback, set_llm_stream_callback
from venom_core.config import SETTINGS
from venom_core.core import metrics as metrics_module
from venom_core.core.flows.campaign import CampaignFlow
from venom_core.core.hidden_prompts import build_hidden_prompts_context
from venom_core.core.models import TaskExtraContext, TaskRequest, TaskStatus
from venom_core.core.slash_commands import (
    normalize_forced_provider,
    parse_slash_command,
    resolve_forced_intent,
)
from venom_core.core.tracer import TraceStatus
from venom_core.utils.llm_runtime import compute_llm_config_hash, get_active_llm_runtime
from venom_core.utils.logger import get_logger
from venom_core.utils.text import trim_to_char_limit

from .constants import (
    DEFAULT_USER_ID,
    HISTORY_SUMMARY_TRIGGER_CHARS,
    HISTORY_SUMMARY_TRIGGER_MSGS,
    LEARNING_LOG_PATH,
    MAX_CONTEXT_CHARS,
    MAX_HIDDEN_PROMPTS_IN_CONTEXT,
    MAX_LEARNING_SNIPPET,
    SUMMARY_STRATEGY_DEFAULT,
)

if TYPE_CHECKING:
    from .orchestrator_core import Orchestrator

logger = get_logger(__name__)


async def run_task(
    orch: "Orchestrator",
    task_id: UUID,
    request: TaskRequest,
    fast_path: bool = False,
) -> None:
    context = request.content
    intent = "UNKNOWN"
    result = ""
    tool_required = False
    hidden_context = ""
    forced_tool = request.forced_tool
    forced_provider = request.forced_provider
    forced_intent = request.forced_intent

    try:
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
            asyncio.create_task(
                orch._trace_step_async(
                    task_id, "Orchestrator", "start_processing", status="ok"
                )
            )

        asyncio.create_task(
            orch._broadcast_event(
                event_type="TASK_STARTED",
                message=f"Rozpoczynam przetwarzanie zadania {task_id}",
                data={"task_id": str(task_id)},
            )
        )

        logger.info("Rozpoczynam przetwarzanie zadania %s", task_id)

        orch._persist_session_context(task_id, request)
        orch._append_session_history(
            task_id,
            role="user",
            content=context,
            session_id=request.session_id,
        )

        if not forced_tool and not forced_provider:
            parsed = parse_slash_command(context)
            if parsed and parsed.cleaned != context:
                context = parsed.cleaned
                request.content = parsed.cleaned
                forced_tool = parsed.forced_tool
                forced_provider = parsed.forced_provider
                if not forced_intent:
                    forced_intent = parsed.forced_intent
                if parsed.session_reset:
                    request.session_id = request.session_id or f"session-{uuid4()}"
                    orch.state_manager.update_context(
                        task_id,
                        {
                            "session_history": [],
                            "session_history_full": [],
                            "session_summary": None,
                        },
                    )
                    if orch.session_handler.session_store and request.session_id:
                        try:
                            orch.session_handler.session_store.clear_session(
                                request.session_id
                            )
                        except Exception as exc:  # pragma: no cover
                            logger.warning(
                                "Nie udalo sie wyczyscic SessionStore: %s", exc
                            )
                    orch.state_manager.add_log(
                        task_id, "Wyczyszczono kontekst sesji (/clear)."
                    )

        if forced_tool and not forced_intent:
            forced_intent = resolve_forced_intent(forced_tool)

        if forced_tool or forced_provider or forced_intent:
            orch.state_manager.update_context(
                task_id,
                {
                    "forced_route": {
                        "tool": forced_tool,
                        "provider": forced_provider,
                        "intent": forced_intent,
                    }
                },
            )
            if orch.request_tracer:
                if forced_tool or forced_provider:
                    orch.request_tracer.set_forced_route(
                        task_id,
                        forced_tool=forced_tool,
                        forced_provider=forced_provider,
                    )
                orch.request_tracer.add_step(
                    task_id,
                    "DecisionGate",
                    "forced_route",
                    status="ok",
                    details=(
                        f"tool={forced_tool}, provider={forced_provider}, intent={forced_intent}"
                    ),
                )

        context_task = asyncio.create_task(prepare_context(orch, task_id, request))
        session_block_task = asyncio.to_thread(
            orch._build_session_context_block,
            request,
            task_id,
            include_memory=not fast_path,
        )
        context, session_block = await asyncio.gather(context_task, session_block_task)
        if session_block:
            context = session_block + "\n\n" + context
        context, trimmed = trim_to_char_limit(context, MAX_CONTEXT_CHARS)
        if trimmed:
            orch.state_manager.add_log(
                task_id,
                (
                    "Obcięto kontekst do "
                    f"{MAX_CONTEXT_CHARS} znaków (historia/przygotowanie promptu)."
                ),
            )
        runtime_info = get_active_llm_runtime()
        runtime_limit = orch._get_runtime_context_char_limit(runtime_info)
        if runtime_limit < MAX_CONTEXT_CHARS:
            context, trimmed = trim_to_char_limit(context, runtime_limit)
            if trimmed:
                orch.state_manager.add_log(
                    task_id,
                    f"Obcięto kontekst do {runtime_limit} znaków (limit runtime).",
                )
        dispatch_context = context

        if request.generation_params:
            orch.state_manager.update_context(
                task_id, {"generation_params": request.generation_params}
            )
            logger.info(
                "Zapisano parametry generacji dla zadania %s: %s",
                task_id,
                request.generation_params,
            )

        if is_perf_test_prompt(orch, context):
            await complete_perf_test_task(orch, task_id)
            return

        if forced_tool and not forced_intent:
            envelope = orch._build_error_envelope(
                error_code="forced_tool_unknown",
                error_message=f"Nieznane narzędzie w dyrektywie /{forced_tool}",
                error_details={"forced_tool": forced_tool},
                stage="intent_detection",
                retryable=False,
            )
            orch._set_runtime_error(task_id, envelope)
            raise RuntimeError("forced_tool_unknown")

        intent_context = request.content if orch._testing_mode else context
        if forced_intent:
            intent = forced_intent
            intent_debug = {"source": "forced", "intent": forced_intent}
        else:
            intent = await orch.intent_manager.classify_intent(intent_context)
            intent_debug = getattr(orch.intent_manager, "last_intent_debug", {})
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
            task_id,
            {"tool_requirement": {"required": tool_required, "intent": intent}},
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

        kernel_required = tool_required or intent in orch.KERNEL_FUNCTION_INTENTS
        if orch.request_tracer:
            orch.request_tracer.add_step(
                task_id,
                "DecisionGate",
                "requirements_resolved",
                status="ok",
                details=f"tool_required={tool_required}, kernel_required={kernel_required}",
            )
        if kernel_required and not getattr(orch.task_dispatcher, "kernel", None):
            if orch.request_tracer:
                orch.request_tracer.add_step(
                    task_id,
                    "DecisionGate",
                    "capability_required",
                    status="ok",
                    details="kernel",
                )
                orch.request_tracer.add_step(
                    task_id,
                    "DecisionGate",
                    "requirements_missing",
                    status="error",
                    details="missing=kernel",
                )
                orch.request_tracer.add_step(
                    task_id,
                    "Execution",
                    "execution_contract_violation",
                    status="error",
                    details="kernel_required",
                )
            envelope = orch._build_error_envelope(
                error_code="execution_contract_violation",
                error_message="Missing required capability: kernel",
                error_details={"missing": ["kernel"]},
                stage="agent_precheck",
                retryable=False,
            )
            orch._set_runtime_error(task_id, envelope)
            raise RuntimeError("execution_contract_violation")

        runtime_info = get_active_llm_runtime()
        normalized_forced_provider = normalize_forced_provider(forced_provider)
        if (
            normalized_forced_provider
            and runtime_info.provider != normalized_forced_provider
        ):
            envelope = orch._build_error_envelope(
                error_code="forced_provider_mismatch",
                error_message=(
                    "Wymuszony provider nie jest aktywny. "
                    f"Aktywny={runtime_info.provider}, wymagany={normalized_forced_provider}."
                ),
                error_details={
                    "active_provider": runtime_info.provider,
                    "required_provider": normalized_forced_provider,
                },
                stage="routing_validation",
                retryable=False,
            )
            orch._set_runtime_error(task_id, envelope)
            raise RuntimeError("forced_provider_mismatch")
        expected_hash = request.expected_config_hash or SETTINGS.LLM_CONFIG_HASH
        expected_runtime_id = request.expected_runtime_id
        actual_hash = runtime_info.config_hash or compute_llm_config_hash(
            runtime_info.provider, runtime_info.endpoint, runtime_info.model_name
        )
        if orch.request_tracer:
            orch.request_tracer.add_step(
                task_id,
                "Orchestrator",
                "routing_resolved",
                status="ok",
                details=(
                    f"provider={runtime_info.provider}, model={runtime_info.model_name}, "
                    f"endpoint={runtime_info.endpoint}, hash={actual_hash}, runtime={runtime_info.runtime_id}"
                ),
            )
        mismatch = False
        mismatch_details = []
        if expected_hash and actual_hash != expected_hash:
            mismatch = True
            mismatch_details.append(
                f"expected_hash={expected_hash}, actual_hash={actual_hash}"
            )
        if expected_runtime_id and runtime_info.runtime_id != expected_runtime_id:
            mismatch = True
            mismatch_details.append(
                f"expected_runtime={expected_runtime_id}, actual_runtime={runtime_info.runtime_id}"
            )
        if mismatch:
            if orch.request_tracer:
                orch.request_tracer.add_step(
                    task_id,
                    "Orchestrator",
                    "routing_mismatch",
                    status="error",
                    details="; ".join(mismatch_details),
                )
            envelope = orch._build_error_envelope(
                error_code="routing_mismatch",
                error_message="Active runtime does not match expected configuration.",
                error_details={
                    "expected_hash": expected_hash,
                    "actual_hash": actual_hash,
                    "expected_runtime": expected_runtime_id,
                    "actual_runtime": runtime_info.runtime_id,
                },
                stage="routing",
                retryable=False,
            )
            orch._set_runtime_error(task_id, envelope)
            raise RuntimeError("routing_mismatch")

        if intent not in orch.NON_LEARNING_INTENTS and not tool_required:
            context = await orch.lessons_manager.add_lessons_to_context(
                task_id, context
            )
            runtime_info = get_active_llm_runtime()
            runtime_limit = orch._get_runtime_context_char_limit(runtime_info)
            include_hidden = True
            max_ctx_raw = getattr(SETTINGS, "VLLM_MAX_MODEL_LEN", None)
            max_ctx = int(max_ctx_raw) if isinstance(max_ctx_raw, int) else 0
            if runtime_info.provider == "vllm" and max_ctx and max_ctx <= 512:
                include_hidden = False
            hidden_context = (
                build_hidden_prompts_context(
                    intent=intent, limit=MAX_HIDDEN_PROMPTS_IN_CONTEXT
                )
                if include_hidden
                else ""
            )
            if hidden_context:
                context = hidden_context + "\n\n" + context
            orch.state_manager.add_log(
                task_id,
                (
                    "Dołączono hidden prompts do kontekstu"
                    if hidden_context
                    else "Pominięto hidden prompts (mały kontekst vLLM)"
                ),
            )
            if runtime_limit < MAX_CONTEXT_CHARS:
                context, trimmed = trim_to_char_limit(context, runtime_limit)
                if trimmed:
                    orch.state_manager.add_log(
                        task_id,
                        f"Obcięto kontekst do {runtime_limit} znaków (limit runtime).",
                    )
            if orch.request_tracer:
                orch.request_tracer.add_step(
                    task_id,
                    "DecisionGate",
                    "hidden_prompts",
                    status="ok",
                    details=f"Hidden prompts: {MAX_HIDDEN_PROMPTS_IN_CONTEXT}",
                )
        if orch.request_tracer:
            hidden_count = hidden_context.count("[Hidden ")
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
                        "hidden_prompts_count": hidden_count,
                    },
                    ensure_ascii=False,
                ),
            )

        orch.state_manager.add_log(
            task_id,
            f"Sklasyfikowana intencja: {intent} - {datetime.now().isoformat()}",
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

        stream_callback = orch.streaming_handler.create_stream_callback(task_id)
        stream_token = set_llm_stream_callback(stream_callback)

        try:
            if intent == "START_CAMPAIGN":
                orch.state_manager.add_log(
                    task_id, "🚀 Uruchamiam Tryb Kampanii (Campaign Mode)"
                )
                if orch.request_tracer:
                    orch.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "route_campaign",
                        status="ok",
                        details="🚀 Routing to Campaign Mode",
                    )
                if orch._campaign_flow is None:
                    orch._campaign_flow = CampaignFlow(
                        state_manager=orch.state_manager,
                        orchestrator_submit_task=orch.submit_task,
                        event_broadcaster=orch.event_broadcaster,
                    )
                campaign_result = await orch._campaign_flow.execute(
                    goal_store=orch.task_dispatcher.goal_store
                )
                result = campaign_result.get("summary", str(campaign_result))
            elif intent == "HELP_REQUEST":
                orch.state_manager.add_log(task_id, "❓ Generuję informacje pomocy")
                if orch.request_tracer:
                    orch.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "route_help",
                        status="ok",
                        details="❓ Routing to Help System",
                    )
                result = await orch._generate_help_response(task_id)
            elif orch._should_use_council(request.content, intent):
                orch.state_manager.add_log(
                    task_id,
                    "🏛️ Zadanie wymaga współpracy - aktywuję The Council",
                )
                if orch.request_tracer:
                    orch.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "select_council_mode",
                        status="ok",
                        details=(
                            f"🏛️ Complex task detected (intent={intent}) -> Council Mode"
                        ),
                    )
                orch._trace_llm_start(task_id, intent)
                result = await orch.run_council(task_id, context)
            elif intent == "CODE_GENERATION":
                if orch.request_tracer:
                    orch.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "select_code_review_loop",
                        status="ok",
                        details="💻 Routing to Coder-Critic Review Loop",
                    )
                orch._trace_llm_start(task_id, intent)
                result = await orch._code_generation_with_review(
                    task_id, dispatch_context
                )
            elif intent == "COMPLEX_PLANNING":
                orch.state_manager.add_log(
                    task_id,
                    (
                        "Zadanie sklasyfikowane jako COMPLEX_PLANNING "
                        "- delegacja do Architekta"
                    ),
                )
                if orch.request_tracer:
                    orch.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "route_to_architect",
                        status="ok",
                        details="🏗️ Routing to Architect for Complex Planning",
                    )
                await orch._broadcast_event(
                    event_type="AGENT_ACTION",
                    message="Przekazuję zadanie do Architekta (Complex Planning)",
                    agent="Architect",
                    data={"task_id": str(task_id)},
                )
                orch._trace_llm_start(task_id, intent)
                if request.generation_params:
                    result = await orch.task_dispatcher.dispatch(
                        intent,
                        context,
                        generation_params=request.generation_params,
                    )
                else:
                    result = await orch.task_dispatcher.dispatch(intent, context)
            else:
                if orch.request_tracer:
                    agent = orch.task_dispatcher.agent_map.get(intent)
                    agent_name = agent.__class__.__name__ if agent else "UnknownAgent"
                    orch.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "route_to_agent",
                        status="ok",
                        details=f"📤 Routing to {agent_name} (intent={intent})",
                    )
                orch._trace_llm_start(task_id, intent)
                if request.generation_params:
                    result = await orch.task_dispatcher.dispatch(
                        intent,
                        context,
                        generation_params=request.generation_params,
                    )
                else:
                    result = await orch.task_dispatcher.dispatch(intent, context)
        finally:
            reset_llm_stream_callback(stream_token)

        result = await orch._apply_preferred_language(task_id, request, result)

        agent = orch.task_dispatcher.agent_map.get(intent)
        if agent is not None:
            agent_name = agent.__class__.__name__
            orch.state_manager.add_log(
                task_id,
                f"Agent {agent_name} przetworzył zadanie - {datetime.now().isoformat()}",
            )
            if orch.request_tracer:
                orch.request_tracer.add_step(
                    task_id,
                    agent_name,
                    "process_task",
                    status="ok",
                    details="Task processed successfully",
                )
            collector = metrics_module.metrics_collector
            if collector:
                collector.increment_agent_usage(agent_name)

            formatted_result = ""
            if isinstance(result, (dict, list)):
                try:
                    formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                except Exception:
                    formatted_result = str(result)
            else:
                formatted_result = str(result)

            if formatted_result.strip():
                await orch._broadcast_event(
                    event_type="AGENT_ACTION",
                    message=formatted_result,
                    agent=agent_name,
                    data={"task_id": str(task_id), "intent": intent},
                )
        else:
            logger.error(
                "Nie znaleziono agenta dla intencji '%s' podczas logowania zadania %s",
                intent,
                task_id,
            )

        if request.session_id and result:
            orch.session_handler._memory_upsert(
                str(result),
                metadata={
                    "type": "fact",
                    "session_id": request.session_id,
                    "user_id": "user_default",
                    "pinned": True,
                },
            )
        await orch.state_manager.update_status(
            task_id, TaskStatus.COMPLETED, result=result
        )
        orch._append_session_history(
            task_id,
            role="assistant",
            content=str(result),
            session_id=request.session_id,
        )
        orch.state_manager.add_log(
            task_id, f"Zakończono przetwarzanie: {datetime.now().isoformat()}"
        )
        orch.state_manager.update_context(
            task_id,
            {
                "llm_runtime": {
                    "status": "ready",
                    "error": None,
                    "last_success_at": datetime.now().isoformat(),
                }
            },
        )

        if orch.request_tracer:
            orch.request_tracer.update_status(task_id, TraceStatus.COMPLETED)
            orch.request_tracer.add_step(
                task_id, "System", "complete", status="ok", details="Response sent"
            )

        if orch._should_store_lesson(request, intent=intent, agent=agent):
            await orch.lessons_manager.save_task_lesson(
                task_id=task_id,
                context=context,
                intent=intent,
                result=result,
                success=True,
                agent=agent,
                request=request,
            )
        else:
            logger.info(
                "Skipping lesson save for task %s (Knowledge Storage Disabled)", task_id
            )

        if orch.lessons_manager.should_log_learning(
            request, intent=intent, tool_required=tool_required, agent=agent
        ):
            orch.lessons_manager.append_learning_log(
                task_id=task_id,
                intent=intent,
                prompt=request.content,
                result=result,
                success=True,
            )

        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_task_completed()

        await orch._broadcast_event(
            event_type="TASK_COMPLETED",
            message=f"Zadanie {task_id} zakończone sukcesem",
            data={"task_id": str(task_id), "result_length": len(result)},
        )

        logger.info("Zadanie %s zakończone sukcesem", task_id)

    except Exception as exc:
        logger.error("Błąd podczas przetwarzania zadania %s: %s", task_id, exc)
        task = orch.state_manager.get_task(task_id)
        existing_error = None
        if task:
            runtime_ctx = task.context_history.get("llm_runtime", {}) or {}
            if isinstance(runtime_ctx, dict):
                existing_error = runtime_ctx.get("error")
        error_details: dict[str, object] = {"exception": exc.__class__.__name__}
        error_message_text = str(exc) or ""
        try:
            import re

            token_match = re.search(
                r"maximum context length is (\\d+) tokens.*request has (\\d+) input tokens \\((\\d+) > (\\d+) - (\\d+)\\)",
                error_message_text,
            )
            if token_match:
                max_ctx = int(token_match.group(1))
                input_tokens = int(token_match.group(2))
                requested_tokens = int(token_match.group(3))
                error_details.update(
                    {
                        "max_context_tokens": max_ctx,
                        "input_tokens": input_tokens,
                        "requested_max_tokens": requested_tokens,
                    }
                )
            elif (
                "input tokens" in error_message_text
                or "max_tokens" in error_message_text
            ):
                error_details["raw_token_error"] = error_message_text
        except Exception:
            pass

        if request and getattr(request, "content", None):
            error_details.setdefault(
                "prompt_preview",
                request.content[:400] + ("..." if len(request.content) > 400 else ""),
            )
        if "context" in locals() and isinstance(context, str) and context:
            max_len = 4000
            truncated = len(context) > max_len
            error_details.setdefault(
                "prompt_context",
                context[:max_len] + ("...(truncated)" if truncated else ""),
            )
            error_details.setdefault("prompt_context_truncated", truncated)
        if not (isinstance(existing_error, dict) and existing_error.get("error_code")):
            envelope = orch._build_error_envelope(
                error_code="agent_error",
                error_message=str(exc) or "Unhandled agent error",
                error_details=error_details,
                stage="agent_runtime",
                retryable=False,
            )
            orch._set_runtime_error(task_id, envelope)

        if orch.request_tracer:
            orch.request_tracer.update_status(task_id, TraceStatus.FAILED)
            orch.request_tracer.add_step(
                task_id,
                "System",
                "error",
                status="error",
                details=f"Error: {str(exc)}",
            )

        agent = orch.task_dispatcher.agent_map.get(intent)
        if orch._should_store_lesson(request, intent=intent, agent=agent):
            await orch.lessons_manager.save_task_lesson(
                task_id=task_id,
                context=context,
                intent=intent,
                result=f"Błąd: {str(exc)}",
                success=False,
                error=str(exc),
                agent=agent,
                request=request,
            )
        else:
            logger.info(
                "Skipping lesson save for task %s (Knowledge Storage Disabled)", task_id
            )

        if orch.lessons_manager.should_log_learning(
            request, intent=intent, tool_required=tool_required, agent=agent
        ):
            orch.lessons_manager.append_learning_log(
                task_id=task_id,
                intent=intent,
                prompt=request.content,
                result=f"Błąd: {str(exc)}",
                success=False,
                error=str(exc),
            )

        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_task_failed()

        await orch._broadcast_event(
            event_type="TASK_FAILED",
            message=f"Zadanie {task_id} nie powiodło się: {str(exc)}",
            data={"task_id": str(task_id), "error": str(exc)},
        )

        try:
            await orch.state_manager.update_status(
                task_id, TaskStatus.FAILED, result=f"Błąd: {str(exc)}"
            )
            orch.state_manager.add_log(
                task_id,
                f"Błąd przetwarzania: {str(exc)} - {datetime.now().isoformat()}",
            )
        except Exception as log_error:
            logger.error(
                "Nie udało się zapisać błędu zadania %s: %s", task_id, log_error
            )


def is_perf_test_prompt(orch: "Orchestrator", content: str) -> bool:
    keywords = getattr(orch.intent_manager, "PERF_TEST_KEYWORDS", ())
    normalized = (content or "").lower()
    return any(keyword in normalized for keyword in keywords)


async def complete_perf_test_task(orch: "Orchestrator", task_id: UUID) -> None:
    result_text = "✅ Backend perf pipeline OK"
    orch.state_manager.add_log(
        task_id,
        "⚡ Wykryto prompt testu wydajności – pomijam kosztowne agentów i zamykam zadanie natychmiast.",
    )
    await orch.state_manager.update_status(
        task_id, TaskStatus.COMPLETED, result=result_text
    )
    orch.state_manager.add_log(
        task_id, f"Zakończono test wydajności: {datetime.now().isoformat()}"
    )

    if orch.request_tracer:
        orch.request_tracer.update_status(task_id, TraceStatus.COMPLETED)
        orch.request_tracer.add_step(
            task_id,
            "System",
            "perf_test_shortcut",
            status="ok",
            details="Perf test zakończony bez agentów",
        )

    collector = metrics_module.metrics_collector
    if collector:
        collector.increment_task_completed()

    await orch._broadcast_event(
        event_type="TASK_COMPLETED",
        message=f"Zadanie {task_id} zakończone (perf test)",
        data={"task_id": str(task_id), "result_length": len(result_text)},
    )

    logger.info("Zadanie %s zakończone w trybie perf-test", task_id)


async def prepare_context(
    orch: "Orchestrator", task_id: UUID, request: TaskRequest
) -> str:
    context = request.content

    if request.images:
        orch.state_manager.add_log(
            task_id, f"Analizuję {len(request.images)} obrazów..."
        )

        for i, image in enumerate(request.images, 1):
            try:
                description = await orch.eyes.analyze_image(
                    image,
                    prompt=(
                        "Opisz szczegółowo co widzisz na tym obrazie, "
                        "szczególnie zwróć uwagę na tekst, błędy lub problemy."
                    ),
                )
                context += f"\n\n[OBRAZ {i}]: {description}"
                orch.state_manager.add_log(
                    task_id, f"Obraz {i} przeanalizowany pomyślnie"
                )
            except Exception as exc:
                logger.error("Błąd podczas analizy obrazu %s: %s", i, exc)
                orch.state_manager.add_log(
                    task_id, f"Nie udało się przeanalizować obrazu {i}: {exc}"
                )

    if request.extra_context:
        extra_block = format_extra_context(request.extra_context)
        if extra_block:
            context += f"\n\n[DODATKOWE DANE]\n{extra_block}"

    return context


def format_extra_context(extra_context: TaskExtraContext) -> str:
    sections: list[str] = []

    def add_section(label: str, items: Optional[list[str]]) -> None:
        cleaned = [item.strip() for item in (items or []) if item and item.strip()]
        if not cleaned:
            return
        section = [f"{label}:"]
        section.extend(f"- {item}" for item in cleaned)
        sections.append("\n".join(section))

    add_section("Pliki", extra_context.files)
    add_section("Linki", extra_context.links)
    add_section("Ścieżki", extra_context.paths)
    add_section("Notatki", extra_context.notes)

    return "\n\n".join(sections)


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
