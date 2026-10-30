"""Metadata-only OpenRouter administration and admitted selection."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from venom_core.api.operator_origin import require_operator_origin
from venom_core.api.routes.system_config import require_localhost_request
from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services import openrouter_runtime as runtime
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

router = APIRouter(
    prefix="/openrouter", dependencies=[Depends(require_localhost_request)]
)


@router.get("/status")
async def status():
    return runtime.status()


@router.get("/catalog")
async def catalog():
    value = runtime.status()
    return {k: value[k] for k in ("models", "pricing_as_of", "available", "reason")}


@router.post("/quote")
async def quote(request: SimpleChatRequest):
    from venom_core.services.openrouter_chat import quote as create_quote

    return create_quote(request)


@admitted_operation("runtime_switch", mutation=True)
async def activate(request, switch_source):
    assert_runtime_switch_source_allowed(switch_source)
    assert_runtime_switch_ownership_token(request.ownership_token)
    from venom_core.utils.llm_runtime import get_active_llm_runtime

    active = get_active_llm_runtime()
    gate = begin_runtime_switch(
        source=switch_source,
        from_runtime=active.provider,
        to_runtime="openrouter",
        reason="select_openrouter_chat",
    )
    try:
        if not await wait_for_runtime_requests_to_drain(timeout_seconds=30):
            raise HTTPException(409, "runtime_requests_not_drained")
        result = runtime.select_model(request.model)
        from venom_core.services.vast_chat_runtime import clear_selection, selection

        if selection() is not None:
            clear_selection()
        return result
    finally:
        finish_runtime_switch(switch_id=gate.switch_id)


class ModelConnectionRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=300)


@router.get("/models/search")
async def search_models(
    q: Annotated[str, Query(max_length=120)] = "",
    purpose: Literal["chat", "tasks", "programming"] = "chat",
    category: str = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    free_only: bool = False,
):
    from venom_core.services import openrouter_model_catalog as catalog

    return await catalog.search(
        q, purpose, category, offset, limit, free_only=free_only
    )


@router.get("/models/connected")
async def connected_models():
    from venom_core.services import openrouter_model_catalog as catalog

    return catalog.connected()


@router.post("/models/connect")
async def connect_model(request: ModelConnectionRequest):
    from venom_core.services import openrouter_model_catalog as catalog

    return await catalog.connect(request.model_id)


@router.post("/models/disconnect")
async def disconnect_model(request: ModelConnectionRequest):
    from venom_core.services import openrouter_model_catalog as catalog

    return catalog.disconnect(request.model_id)


@router.get("/billing")
def billing(
    period: Literal["7d", "30d", "month", "all"] = "30d",
    from_utc: date | None = None,
    to_utc: date | None = None,
):
    from venom_core.services.openrouter_billing import BillingError, OpenRouterBilling

    try:
        return OpenRouterBilling().view(period, from_utc, to_utc)
    except BillingError:
        raise HTTPException(422, "openrouter_invalid_billing_window") from None


def billing_operator(request: Request) -> None:
    require_localhost_request(request)
    require_operator_origin(request, "openrouter_billing_local_operator_required")


@router.post("/billing/sync", dependencies=[Depends(billing_operator)])
def sync_billing():
    from venom_core.services.openrouter_billing import OpenRouterBilling

    if not runtime.is_enabled() or not runtime.cloud_allowed():
        raise HTTPException(403, "openrouter_billing_disabled")
    OpenRouterBilling().sync()
    return {"ok": True}
