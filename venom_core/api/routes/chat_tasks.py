"""Session-scoped Stop delegates to the existing queue; never global emergency."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from venom_core.api.dependencies import get_orchestrator
from venom_core.api.transport_access import require_operator_request
from venom_core.core.models import TaskStatus
from venom_core.core.orchestrator import Orchestrator

router = APIRouter(
    prefix="/api/v1/chat/tasks",
    tags=["chat-tasks"],
    dependencies=[Depends(require_operator_request)],
)


class CancelChatTask(BaseModel):
    session_id: str = Field(min_length=1, max_length=256)


class ChatTaskCancellation(BaseModel):
    success: bool = True
    task_id: UUID
    status: Literal["cancelled", "already_finished"]


@router.post(
    "/{task_id}/cancel",
    response_model=ChatTaskCancellation,
    responses={
        403: {"description": "Operator access denied"},
        404: {
            "description": "Task does not exist or does not belong to the supplied session"
        },
        409: {
            "description": "Task is not active and cancellation could not be confirmed"
        },
    },
)
async def cancel_chat_task(
    task_id: UUID,
    payload: CancelChatTask,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
):
    task = orchestrator.state_manager.get_task(task_id)
    if task is None:
        raise HTTPException(404, {"reason_code": "chat_task_not_found"})
    session = task.context_history.get("session")
    if not isinstance(session, dict) or session.get("session_id") != payload.session_id:
        raise HTTPException(404, {"reason_code": "chat_task_not_found"})
    if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
        return ChatTaskCancellation(task_id=task_id, status="already_finished")
    result = await orchestrator.abort_task(task_id)
    if result.get("success"):
        return ChatTaskCancellation(task_id=task_id, status="cancelled")
    # A task can finish while Stop awaits the existing queue lock.
    current = orchestrator.state_manager.get_task(task_id)
    if current is not None and current.status in {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
    }:
        return ChatTaskCancellation(task_id=task_id, status="already_finished")
    raise HTTPException(409, {"reason_code": "chat_task_not_active"})
