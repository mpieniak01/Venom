"""Session-owned cancellation over the host orchestrator; API adapters stay thin."""

from typing import Literal
from uuid import UUID

from fastapi import HTTPException

from venom_core.core.models import TaskStatus
from venom_core.core.orchestrator import Orchestrator


async def cancel_session_task(
    task_id: UUID, session_id: str, orchestrator: Orchestrator
) -> Literal["cancelled", "already_finished"]:
    """Cancel only a session-owned task and recheck completion after the queue lock."""
    task = orchestrator.state_manager.get_task(task_id)
    if task is None:
        raise HTTPException(404, {"reason_code": "chat_task_not_found"})
    session = task.context_history.get("session")
    if not isinstance(session, dict) or session.get("session_id") != session_id:
        raise HTTPException(404, {"reason_code": "chat_task_not_found"})
    if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
        return "already_finished"
    result = await orchestrator.abort_task(task_id)
    if result.get("success"):
        return "cancelled"
    # A task can finish while Stop awaits the existing queue lock.
    current = orchestrator.state_manager.get_task(task_id)
    if current is not None and current.status in {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
    }:
        return "already_finished"
    raise HTTPException(409, {"reason_code": "chat_task_not_active"})
