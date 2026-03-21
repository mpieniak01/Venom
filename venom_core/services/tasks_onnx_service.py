"""ONNX task execution helpers for tasks route."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from venom_core.core.models import TaskStatus
from venom_core.core.tracer import TraceStatus


class TaskRuntimeLike(Protocol):
    provider: str
    model_name: str
    endpoint: str
    config_hash: str
    runtime_id: str

    def to_payload(self) -> dict[str, Any]: ...


class TaskRequestLike(Protocol):
    content: str
    session_id: str | None
    forced_intent: str | None
    store_knowledge: bool
    generation_params: dict[str, Any] | None


class TaskLike(Protocol):
    id: Any


class StateManagerLike(Protocol):
    def create_task(self, content: str) -> TaskLike: ...

    def update_context(self, task_id: Any, payload: dict[str, Any]) -> None: ...

    def add_log(self, task_id: Any, message: str) -> None: ...

    async def update_status(
        self, task_id: Any, status: TaskStatus, result: str | None = None
    ) -> None: ...


def _is_help_request(content: str, forced_intent: str | None) -> bool:
    if str(forced_intent or "").strip().upper() == "HELP_REQUEST":
        return True
    normalized = str(content or "").strip().lower()
    return normalized in {"pomoc", "help", "help me"} or normalized.startswith("pomoc ")


def _build_fast_help_response() -> str:
    return (
        "Jasne, pomogę. Mogę wspierać Cię w analizie, kodowaniu, testach i "
        "diagnozie problemów. Napisz, czego konkretnie potrzebujesz."
    )


class TracerLike(Protocol):
    def create_trace(self, task_id: Any, content: str, *, session_id: str) -> None: ...

    def set_llm_metadata(
        self,
        task_id: Any,
        *,
        provider: str,
        model: str,
        endpoint: str,
        metadata: dict[str, Any],
    ) -> None: ...

    def update_status(self, task_id: Any, status: TraceStatus) -> None: ...

    def add_step(
        self,
        task_id: Any,
        stage: str,
        action: str,
        *,
        status: str,
        details: str,
    ) -> None: ...

    def set_error_metadata(self, task_id: Any, payload: dict[str, Any]) -> None: ...


def trace_onnx_task_start(
    *,
    tracer: TracerLike | None,
    task_id: Any,
    request: TaskRequestLike,
    runtime: TaskRuntimeLike,
) -> None:
    if tracer is None:
        return
    tracer.create_trace(task_id, request.content, session_id=request.session_id or "")
    tracer.set_llm_metadata(
        task_id,
        provider=runtime.provider,
        model=runtime.model_name,
        endpoint=runtime.endpoint,
        metadata={
            "config_hash": runtime.config_hash,
            "runtime_id": runtime.runtime_id,
        },
    )
    tracer.update_status(task_id, TraceStatus.PROCESSING)
    tracer.add_step(
        task_id,
        "OnnxTask",
        "start_processing",
        status="ok",
        details=f"forced_intent={request.forced_intent or '-'}",
    )


def trace_onnx_task_success(
    *, tracer: TracerLike | None, task_id: Any, result: str
) -> None:
    if tracer is None:
        return
    tracer.add_step(
        task_id,
        "OnnxTask",
        "complete",
        status="ok",
        details=f"result_chars={len(result)}",
    )
    tracer.update_status(task_id, TraceStatus.COMPLETED)


def trace_onnx_task_failure(
    *, tracer: TracerLike | None, task_id: Any, exc: Exception
) -> None:
    if tracer is None:
        return
    tracer.add_step(
        task_id,
        "OnnxTask",
        "error",
        status="error",
        details=str(exc),
    )
    tracer.set_error_metadata(
        task_id,
        {
            "error_code": "onnx_task_error",
            "error_class": exc.__class__.__name__,
            "error_message": str(exc),
            "error_details": {"provider": "onnx"},
            "stage": "onnx_task_execution",
            "retryable": False,
        },
    )
    tracer.update_status(task_id, TraceStatus.FAILED)


def create_and_submit_onnx_task(
    *,
    state_manager: StateManagerLike,
    request: TaskRequestLike,
    runtime: TaskRuntimeLike,
    trace_start_fn: Callable[[Any], None],
    schedule_runner_fn: Callable[[Any], Any],
) -> TaskLike:
    task = state_manager.create_task(request.content)
    state_manager.update_context(
        task.id,
        {
            "session": {"session_id": request.session_id},
            "llm_runtime": runtime.to_payload() | {"status": "ready"},
        },
    )
    trace_start_fn(task.id)
    schedule_runner_fn(task.id)
    return task


async def run_onnx_task(
    *,
    state_manager: StateManagerLike,
    task_id: Any,
    request: TaskRequestLike,
    runtime: TaskRuntimeLike,
    build_messages_fn: Callable[[str, Any], list[dict[str, str]]],
    run_generation_fn: Callable[
        [list[dict[str, str]], int | None, float | None], Awaitable[str]
    ],
    trace_success_fn: Callable[[Any, str], None],
    trace_failure_fn: Callable[[Any, Exception], None],
    append_session_history_fn: Callable[[Any, str, str, str | None], None]
    | None = None,
    append_learning_log_fn: Callable[[Any, str, str, str, bool, str], None]
    | None = None,
    logger: Any,
) -> None:
    try:
        await state_manager.update_status(task_id, TaskStatus.PROCESSING)
        state_manager.add_log(task_id, "ONNX: rozpoczęto przetwarzanie zadania.")
        if append_session_history_fn is not None:
            append_session_history_fn(
                task_id,
                "user",
                request.content,
                request.session_id,
            )

        messages = build_messages_fn(request.content, request.forced_intent)

        max_tokens = None
        temperature = None
        if isinstance(request.generation_params, dict):
            mt = request.generation_params.get("max_tokens")
            temp = request.generation_params.get("temperature")
            if isinstance(mt, (int, float)):
                max_tokens = int(mt)
            if isinstance(temp, (int, float)):
                temperature = float(temp)

        if _is_help_request(request.content, request.forced_intent):
            result = _build_fast_help_response()
            state_manager.add_log(task_id, "ONNX: fast help shortcut (HELP_REQUEST).")
        else:
            result = (
                await run_generation_fn(messages, max_tokens, temperature)
            ).strip()
            if not result:
                result = "Brak odpowiedzi z runtime ONNX."

        state_manager.update_context(
            task_id,
            {
                "llm_runtime": runtime.to_payload() | {"status": "ready"},
                "session": {"session_id": request.session_id},
                "generation_params": request.generation_params or {},
            },
        )
        state_manager.add_log(task_id, "ONNX: zakończono generację.")
        await state_manager.update_status(task_id, TaskStatus.COMPLETED, result=result)
        if append_session_history_fn is not None:
            append_session_history_fn(
                task_id,
                "assistant",
                result,
                request.session_id,
            )
        if append_learning_log_fn is not None and bool(request.store_knowledge):
            intent = str(request.forced_intent or "").strip().upper() or "GENERAL_CHAT"
            if intent not in {"TIME_REQUEST", "INFRA_STATUS"}:
                append_learning_log_fn(
                    task_id,
                    intent,
                    request.content,
                    result,
                    True,
                    "",
                )
        trace_success_fn(task_id, result)
    except Exception as exc:
        logger.exception("Błąd ONNX task execution: %s", exc)
        state_manager.add_log(task_id, f"ONNX: błąd: {exc}")
        await state_manager.update_status(
            task_id, TaskStatus.FAILED, result=f"Błąd: {exc}"
        )
        trace_failure_fn(task_id, exc)
