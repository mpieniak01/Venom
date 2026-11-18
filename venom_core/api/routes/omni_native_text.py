"""Explicit selection of installed native Omni text adapters; no quality promotion."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from venom_core.services import omni_native_text

router = APIRouter(prefix="/native-text", tags=["llm"])


class SelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str | None = Field(
        default=None, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"
    )
    expected_runtime_id: str | None = Field(default=None, max_length=256)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_runtime_id: str | None = Field(default=None, max_length=256)


@router.get("/state")
async def state():
    return omni_native_text.state()


@router.get("/catalog")
async def catalog():
    return {"adapters": omni_native_text.catalog()}


@router.put("/selection")
async def select(request: SelectionRequest):
    return await omni_native_text.switch(
        request.adapter_id, expected_runtime_id=request.expected_runtime_id
    )


@router.post("/rollback")
async def rollback(request: RollbackRequest):
    return await omni_native_text.rollback(
        expected_runtime_id=request.expected_runtime_id
    )
