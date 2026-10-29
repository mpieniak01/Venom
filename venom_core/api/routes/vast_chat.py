"""Local manual transport administration; no rental or model installation."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from venom_core.api.routes.system_config import require_localhost_request
from venom_core.services import vast_chat_runtime
from venom_core.services.runtime_admission import admitted_operation
from venom_core.services.runtime_switch_gate import (
    begin_runtime_switch,
    finish_runtime_switch,
    wait_for_runtime_requests_to_drain,
)
from venom_core.services.runtime_switch_telemetry import (
    assert_runtime_switch_ownership_token,
    assert_runtime_switch_source_allowed,
)

router = APIRouter()


class DetachRequest(BaseModel):
    plan_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class AttachRequest(BaseModel):
    plan_id: str = Field(pattern=r"^[a-f0-9]{32}$")


@router.get("/system/vast-chat", dependencies=[Depends(require_localhost_request)])
async def status():
    return await asyncio.to_thread(vast_chat_runtime.connection().status, refresh=True)


@router.post(
    "/system/vast-chat/attach",
    dependencies=[Depends(require_localhost_request)],
    responses={
        409: {
            "description": "Select the local runtime before attaching another target."
        }
    },
)
@admitted_operation("runtime_command", mutation=True)
async def attach(request: AttachRequest):
    selected = vast_chat_runtime.selection()
    if selected is not None and not selected.get("target_id", "").startswith(
        "ollama@vast:" + request.plan_id + ":"
    ):
        raise HTTPException(
            status_code=409, detail="vast_chat_select_local_before_reattach"
        )
    return await asyncio.to_thread(
        vast_chat_runtime.connection().attach, request.plan_id
    )


@router.post(
    "/system/vast-chat/detach", dependencies=[Depends(require_localhost_request)]
)
@admitted_operation("runtime_command", mutation=True)
async def detach(request: DetachRequest | None = None):
    # Keep selected identity: a later generation fails instead of falling back.
    if request is not None and request.plan_id is not None:
        return await asyncio.to_thread(
            vast_chat_runtime.connection().detach, request.plan_id
        )
    return await asyncio.to_thread(vast_chat_runtime.connection().detach)


@admitted_operation("runtime_switch", mutation=True)
async def activate(request, switch_source: str):
    assert_runtime_switch_source_allowed(switch_source)
    assert_runtime_switch_ownership_token(request.ownership_token)
    from venom_core.utils.llm_runtime import get_active_llm_runtime

    active = get_active_llm_runtime()
    gate = begin_runtime_switch(
        source=switch_source,
        from_runtime=vast_chat_runtime.server_name(active),
        to_runtime=vast_chat_runtime.SERVER,
        reason="select_vast_chat",
    )
    try:
        if not await wait_for_runtime_requests_to_drain(timeout_seconds=30):
            raise HTTPException(status_code=409, detail="runtime_requests_not_drained")
        return await vast_chat_runtime.select_model(request.model)
    finally:
        finish_runtime_switch(switch_id=gate.switch_id)
