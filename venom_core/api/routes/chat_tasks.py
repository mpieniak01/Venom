"""Session-scoped Stop delegates to the existing queue; never global emergency."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from venom_core.api.dependencies import get_orchestrator
from venom_core.api.transport_access import require_operator_request
from venom_core.services.chat_tasks import cancel_session_task

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
    orchestrator: Annotated[Any, Depends(get_orchestrator)],
):
    status = await cancel_session_task(task_id, payload.session_id, orchestrator)
    return ChatTaskCancellation(task_id=task_id, status=status)
