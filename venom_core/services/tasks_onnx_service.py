"""ONNX task execution helpers for tasks route."""

from __future__ import annotations

from typing import Any, Callable

from venom_core.core.models import TaskStatus
from venom_core.core.tracer import TraceStatus


def trace_onnx_task_start(
    *, tracer: Any | None, task_id: Any, request: Any, runtime: Any
) -> None:
    if tracer is None:
        return
    tracer.create_trace(task_id, request.content, session_id=request.session_id)
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


def trace_onnx_task_success(*, tracer: Any | None, task_id: Any, result: str) -> None:
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
    *, tracer: Any | None, task_id: Any, exc: Exception
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
    state_manager: Any,
    request: Any,
    runtime: Any,
    trace_start_fn: Callable[[Any], None],
    schedule_runner_fn: Callable[[Any], None],
) -> Any:
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
    state_manager: Any,
    task_id: Any,
    request: Any,
    runtime: Any,
    build_messages_fn: Callable[[str, Any], list[dict[str, str]]],
    run_generation_fn: Callable[[list[dict[str, str]], int | None, float | None], Any],
    trace_success_fn: Callable[[Any, str], None],
    trace_failure_fn: Callable[[Any, Exception], None],
    logger: Any,
) -> None:
    try:
        await state_manager.update_status(task_id, TaskStatus.PROCESSING)
        state_manager.add_log(task_id, "ONNX: rozpoczęto przetwarzanie zadania.")
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

        result = (await run_generation_fn(messages, max_tokens, temperature)).strip()
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
        trace_success_fn(task_id, result)
    except Exception as exc:
        logger.exception("Błąd ONNX task execution: %s", exc)
        state_manager.add_log(task_id, f"ONNX: błąd: {exc}")
        await state_manager.update_status(
            task_id, TaskStatus.FAILED, result=f"Błąd: {exc}"
        )
        trace_failure_fn(task_id, exc)
