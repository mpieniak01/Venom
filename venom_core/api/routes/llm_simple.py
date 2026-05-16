"""Minimal HTTP adapter for the simple LLM streaming endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services.llm_simple_service import release_onnx_simple_client
from venom_core.services.llm_simple_service import (
    stream_simple_chat as stream_simple_chat_service,
)

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


@router.post(
    "/simple/stream",
    responses={
        400: {"description": "Nieprawidłowe dane wejściowe (np. brak modelu)"},
        503: {"description": "Brak dostępnego endpointu LLM"},
    },
)
async def stream_simple_chat(request: SimpleChatRequest):
    """Delegate the whole simple-stream flow to the service layer."""
    return await stream_simple_chat_service(request)


__all__ = ["release_onnx_simple_client", "router", "stream_simple_chat"]
