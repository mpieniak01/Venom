"""Local operator VAST management. No implicit rental on GET or startup."""

from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from venom_core.api.routes.system_config import require_localhost_request
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.services import vast_management


def local_operator(request: Request) -> None:
    require_localhost_request(request)
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (
        origin and urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise HTTPException(403, "vast.management_local_operator_required")


router = APIRouter(prefix="/vast/environments", dependencies=[Depends(local_operator)])
PlanId = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_minutes: int = Field(ge=1, le=1440)


class PlanRequest(SearchRequest):
    offer_id: int = Field(gt=0)
    max_hourly_usd: Decimal = Field(gt=0, le=100, allow_inf_nan=False)
    max_total_usd: Decimal = Field(gt=0, le=1000, allow_inf_nan=False)


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]


class OrderRequest(Confirmation):
    accept_new_host_key: bool = False


def invoke(method, *args):
    try:
        return method(*args)
    except VastError as error:
        status = (
            503
            if error.code
            in {
                "vast.management_disabled",
                "vast.missing_api_key",
                "vast.management_profile_invalid",
            }
            else 409
        )
        raise HTTPException(status, error.code) from None
    except (OSError, ValueError):
        raise HTTPException(503, "vast.management_unavailable") from None


@router.get("")
def overview():
    return invoke(vast_management.manager().overview)


@router.post("/search")
def search(request: SearchRequest):
    return invoke(vast_management.manager().search, request.duration_minutes)


@router.post("/plans")
def plan(request: PlanRequest):
    return invoke(
        vast_management.manager().plan,
        request.offer_id,
        request.duration_minutes,
        request.max_hourly_usd,
        request.max_total_usd,
    )


@router.post("/{plan_id}/order", status_code=202)
def order(plan_id: PlanId, request: OrderRequest):
    return invoke(vast_management.manager().order, plan_id, request.accept_new_host_key)


@router.post("/{plan_id}/refresh")
def refresh(plan_id: PlanId):
    return invoke(vast_management.manager().refresh, plan_id)


@router.post("/{plan_id}/stop")
def stop(plan_id: PlanId, request: Confirmation):
    return invoke(vast_management.manager().change, plan_id, "stop")


@router.post("/{plan_id}/destroy")
def destroy(plan_id: PlanId, request: Confirmation):
    return invoke(vast_management.manager().change, plan_id, "destroy")
