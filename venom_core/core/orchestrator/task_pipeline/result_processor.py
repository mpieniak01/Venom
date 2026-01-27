from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from venom_core.core import metrics as metrics_module
from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.tracer import TraceStatus
from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from venom_core.core.orchestrator.orchestrator_core import Orchestrator

logger = get_logger(__name__)


class ResultProcessor:
    """Handles task result processing, persistence, learning logging, and error handling."""

    def __init__(self, orch: "Orchestrator"):
        self.orch = orch

    async def process_success(
        self,
        task_id: UUID,
        result: Any,
        intent: str,
        context: str,
        request: TaskRequest,
        tool_required: bool,
    ) -> None:
        # 1. Apply language translation if needed
        result = await self.orch._apply_preferred_language(task_id, request, result)

        # 2. Log agent usage
        agent = self.orch.task_dispatcher.agent_map.get(intent)
        agent_name = agent.__class__.__name__ if agent else "UnknownAgent"

        if agent is not None:
            await self._log_agent_action(task_id, agent_name, intent, result)
        else:
            logger.error(
                "Nie znaleziono agenta dla intencji '%s' podczas logowania zadania %s",
                intent,
                task_id,
            )

        # 3. Session Store Upsert (Facts)
        if request.session_id and result:
            self.orch.session_handler._memory_upsert(
                str(result),
                metadata={
                    "type": "fact",
                    "session_id": request.session_id,
                    "user_id": "user_default",
                    "pinned": True,
                },
            )

        # 4. Update Status & History
        await self.orch.state_manager.update_status(
            task_id, TaskStatus.COMPLETED, result=result
        )
        self.orch._append_session_history(
            task_id,
            role="assistant",
            content=str(result),
            session_id=request.session_id,
        )
        self.orch.state_manager.add_log(
            task_id, f"Zakończono przetwarzanie: {datetime.now().isoformat()}"
        )

        # 5. Update Runtime Status
        self.orch.state_manager.update_context(
            task_id,
            {
                "llm_runtime": {
                    "status": "ready",
                    "error": None,
                    "last_success_at": datetime.now().isoformat(),
                }
            },
        )

        # 6. Tracer Update
        if self.orch.request_tracer:
            self.orch.request_tracer.update_status(task_id, TraceStatus.COMPLETED)
            self.orch.request_tracer.add_step(
                task_id, "System", "complete", status="ok", details="Response sent"
            )

        # 7. Save Lessons (Knowledge)
        if self.orch._should_store_lesson(request, intent=intent, agent=agent):
            await self.orch.lessons_manager.save_task_lesson(
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

        # 8. Learning Logs (RL)
        if self.orch.lessons_manager.should_log_learning(
            request, intent=intent, tool_required=tool_required, agent=agent
        ):
            self.orch.lessons_manager.append_learning_log(
                task_id=task_id,
                intent=intent,
                prompt=request.content,
                result=result,
                success=True,
            )

        # 9. Metrics
        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_task_completed()

        # 10. Broadcast Completion
        await self.orch._broadcast_event(
            event_type="TASK_COMPLETED",
            message=f"Zadanie {task_id} zakończone sukcesem",
            data={"task_id": str(task_id), "result_length": len(str(result))},
        )

        logger.info("Zadanie %s zakończone sukcesem", task_id)

    async def process_error(
        self,
        task_id: UUID,
        exc: Exception,
        request: Optional[TaskRequest],
        context: Optional[str] = None,
    ) -> None:
        logger.error("Błąd podczas przetwarzania zadania %s: %s", task_id, exc)

        task = self.orch.state_manager.get_task(task_id)
        existing_error = None
        if task:
            runtime_ctx = task.context_history.get("llm_runtime", {}) or {}
            if isinstance(runtime_ctx, dict):
                existing_error = runtime_ctx.get("error")

        error_details = self._extract_error_details(exc, request, context)

        if not (isinstance(existing_error, dict) and existing_error.get("error_code")):
            envelope = self.orch._build_error_envelope(
                error_code="agent_error",
                error_message=str(exc) or "Unhandled agent error",
                error_details=error_details,
                stage="agent_runtime",
                retryable=False,
            )
            self.orch._set_runtime_error(task_id, envelope)

        if self.orch.request_tracer:
            self.orch.request_tracer.update_status(task_id, TraceStatus.FAILED)
            self.orch.request_tracer.add_step(
                task_id,
                "System",
                "error",
                status="error",
                details=str(exc),
            )

        # Appending learning log for failure
        # Note: In original code, learning log seems to handle failure?
        # Check original: append_learning_log is called in process_success equivalent,
        # but is NOT called in 'except' block in original run_task.
        # Wait, usually RL needs negative feedback too.
        # But I must stick to original behavior: No learning log call in catch block in original code.

        await self.orch._broadcast_event(
            event_type="TASK_FAILED",
            message=f"Błąd zadania {task_id}: {exc}",
            data={"task_id": str(task_id), "error": str(exc)},
        )

        await self.orch.state_manager.update_status(
            task_id, TaskStatus.FAILED, result=f"Błąd: {exc}"
        )

    async def _log_agent_action(
        self, task_id: UUID, agent_name: str, intent: str, result: Any
    ) -> None:
        self.orch.state_manager.add_log(
            task_id,
            f"Agent {agent_name} przetworzył zadanie - {datetime.now().isoformat()}",
        )
        if self.orch.request_tracer:
            self.orch.request_tracer.add_step(
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
            await self.orch._broadcast_event(
                event_type="AGENT_ACTION",
                message=formatted_result,
                agent=agent_name,
                data={"task_id": str(task_id), "intent": intent},
            )

    def _extract_error_details(
        self, exc: Exception, request: Optional[TaskRequest], context: Optional[str]
    ) -> dict:
        error_details: dict[str, Any] = {"exception": exc.__class__.__name__}
        error_message_text = str(exc) or ""
        try:
            import re

            token_match = re.search(
                r"maximum context length is (\\d+) tokens.*request has (\\d+) input tokens \\((\\d+) > (\\d+) - (\\d+)\\)",
                error_message_text,
            )
            if token_match:
                error_details.update(
                    {
                        "max_context_tokens": int(token_match.group(1)),
                        "input_tokens": int(token_match.group(2)),
                        "requested_max_tokens": int(token_match.group(3)),
                    }
                )
            elif (
                "input tokens" in error_message_text
                or "max_tokens" in error_message_text
            ):
                error_details["raw_token_error"] = error_message_text
        except Exception:
            # Ignorujemy błędy parsowania - dane token mogą być niepełne
            pass

        if request and getattr(request, "content", None):
            error_details.setdefault(
                "prompt_preview",
                request.content[:400] + ("..." if len(request.content) > 400 else ""),
            )
        if context and isinstance(context, str):
            max_len = 4000
            truncated = len(context) > max_len
            error_details.setdefault(
                "prompt_context",
                context[:max_len] + ("...(truncated)" if truncated else ""),
            )
            error_details.setdefault("prompt_context_truncated", truncated)
        return error_details
