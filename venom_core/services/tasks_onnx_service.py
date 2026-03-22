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


def _extract_generation_controls(
    generation_params: dict[str, Any] | None,
) -> tuple[int | None, float | None]:
    max_tokens: int | None = None
    temperature: float | None = None
    if not isinstance(generation_params, dict):
        return max_tokens, temperature

    max_tokens_raw = generation_params.get("max_tokens")
    temperature_raw = generation_params.get("temperature")
    if isinstance(max_tokens_raw, (int, float)):
        max_tokens = int(max_tokens_raw)
    if isinstance(temperature_raw, (int, float)):
        temperature = float(temperature_raw)
    return max_tokens, temperature


def _append_user_history(
    *,
    append_session_history_fn: Callable[[Any, str, str, str | None], None] | None,
    task_id: Any,
    request: TaskRequestLike,
) -> None:
    if append_session_history_fn is None:
        return
    append_session_history_fn(
        task_id,
        "user",
        request.content,
        request.session_id,
    )


def _append_assistant_history(
    *,
    append_session_history_fn: Callable[[Any, str, str, str | None], None] | None,
    task_id: Any,
    result: str,
    session_id: str | None,
) -> None:
    if append_session_history_fn is None:
        return
    append_session_history_fn(
        task_id,
        "assistant",
        result,
        session_id,
    )


async def _generate_onnx_result(
    *,
    task_id: Any,
    request: TaskRequestLike,
    messages: list[dict[str, str]],
    max_tokens: int | None,
    temperature: float | None,
    run_generation_fn: Callable[
        [list[dict[str, str]], int | None, float | None], Awaitable[str]
    ],
    state_manager: StateManagerLike,
) -> str:
    if _is_help_request(request.content, request.forced_intent):
        state_manager.add_log(task_id, "ONNX: fast help shortcut (HELP_REQUEST).")
        return _build_fast_help_response()

    result = (await run_generation_fn(messages, max_tokens, temperature)).strip()
    return result or "Brak odpowiedzi z runtime ONNX."


def _append_learning_log_if_needed(
    *,
    append_learning_log_fn: Callable[[Any, str, str, str, bool, str], None] | None,
    task_id: Any,
    request: TaskRequestLike,
    result: str,
) -> None:
    if append_learning_log_fn is None or not bool(request.store_knowledge):
        return

    intent = str(request.forced_intent or "").strip().upper() or "GENERAL_CHAT"
    if intent in {"TIME_REQUEST", "INFRA_STATUS"}:
        return

    append_learning_log_fn(
        task_id,
        intent,
        request.content,
        result,
        True,
        "",
    )


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
        _append_user_history(
            append_session_history_fn=append_session_history_fn,
            task_id=task_id,
            request=request,
        )

        messages = build_messages_fn(request.content, request.forced_intent)
        max_tokens, temperature = _extract_generation_controls(
            request.generation_params
        )
        result = await _generate_onnx_result(
            task_id=task_id,
            request=request,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            run_generation_fn=run_generation_fn,
            state_manager=state_manager,
        )

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
        _append_assistant_history(
            append_session_history_fn=append_session_history_fn,
            task_id=task_id,
            result=result,
            session_id=request.session_id,
        )
        _append_learning_log_if_needed(
            append_learning_log_fn=append_learning_log_fn,
            task_id=task_id,
            request=request,
            result=result,
        )
        trace_success_fn(task_id, result)
    except Exception as exc:
        logger.exception("Błąd ONNX task execution: %s", exc)
        state_manager.add_log(task_id, f"ONNX: błąd: {exc}")
        await state_manager.update_status(
            task_id, TaskStatus.FAILED, result=f"Błąd: {exc}"
        )
        trace_failure_fn(task_id, exc)
