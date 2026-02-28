"""Domain helpers for task stream/event logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from venom_core.core.models import TaskStatus, VenomTask


def get_llm_runtime(task: VenomTask) -> dict[str, Any]:
    context = getattr(task, "context_history", {}) or {}
    runtime = context.get("llm_runtime", {}) or {}
    return runtime


def extract_task_context(task: Optional[VenomTask]) -> dict[str, Any]:
    if task is None:
        return {}
    return getattr(task, "context_history", {}) or {}


def serialize_context_used(task: Optional[VenomTask]) -> Optional[dict[str, Any]]:
    if task is None or not hasattr(task, "context_used") or not task.context_used:
        return None
    context_used = task.context_used
    if isinstance(context_used, dict):
        return context_used
    if hasattr(context_used, "model_dump"):
        return context_used.model_dump()
    if hasattr(context_used, "dict"):
        return context_used.dict()
    if hasattr(context_used, "__dict__"):
        return dict(context_used.__dict__)
    return None


def should_emit_stream_event(
    *,
    status_changed: bool,
    logs_delta: list[str],
    result_changed: bool,
    ticks_since_emit: int,
    heartbeat_every_ticks: int,
) -> bool:
    return (
        status_changed
        or bool(logs_delta)
        or result_changed
        or ticks_since_emit >= heartbeat_every_ticks
    )


def resolve_stream_event_name(
    *, status_changed: bool, logs_delta: list[str], result_changed: bool
) -> str:
    if status_changed or logs_delta or result_changed:
        return "task_update"
    return "heartbeat"


def resolve_poll_interval(
    *,
    previous_result: Optional[str],
    status: TaskStatus,
    fast_poll_interval_seconds: float,
    poll_interval_seconds: float,
) -> float:
    if previous_result is None and status == TaskStatus.PROCESSING:
        return fast_poll_interval_seconds
    return poll_interval_seconds


def build_stream_payload(task: VenomTask, logs_delta: list[str]) -> dict[str, Any]:
    runtime_info = get_llm_runtime(task)
    return {
        "task_id": str(task.id),
        "status": task.status,
        "logs": logs_delta,
        "result": task.result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_provider": runtime_info.get("provider"),
        "llm_model": runtime_info.get("model"),
        "llm_endpoint": runtime_info.get("endpoint"),
        "llm_status": runtime_info.get("status"),
        "context_history": task.context_history,
    }


def build_task_finished_payload(task: VenomTask) -> dict[str, Any]:
    runtime_info = get_llm_runtime(task)
    return {
        "task_id": str(task.id),
        "status": task.status,
        "result": task.result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_provider": runtime_info.get("provider"),
        "llm_model": runtime_info.get("model"),
        "llm_endpoint": runtime_info.get("endpoint"),
        "llm_status": runtime_info.get("status"),
        "context_history": task.context_history,
    }


def build_missing_task_payload(task_id: UUID) -> dict[str, Any]:
    return {
        "task_id": str(task_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "gone",
        "detail": "Task no longer available in StateManager",
    }


def is_terminal_status(status: TaskStatus) -> bool:
    return status in (TaskStatus.COMPLETED, TaskStatus.FAILED)


def build_onnx_task_messages(
    content: str, forced_intent: str | None
) -> list[dict[str, str]]:
    system_prompt = "Jesteś operacyjnym asystentem Venom."
    if forced_intent == "COMPLEX_PLANNING":
        system_prompt += (
            " Odpowiadaj planem krok po kroku: analiza, plan, ryzyka, wykonanie."
        )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]
