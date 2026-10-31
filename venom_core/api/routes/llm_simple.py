"""Minimal HTTP adapter for the simple LLM streaming endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from venom_core.api.dependencies import get_session_store
from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services.chat_history import persist_direct_response
from venom_core.services.llm_simple_service import release_onnx_simple_client
from venom_core.services.llm_simple_service import (
    stream_simple_chat as stream_simple_chat_service,
)
from venom_core.services.session_store import SessionStore

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


@router.post(
    "/simple/stream",
    responses={
        400: {"description": "Nieprawidłowe dane wejściowe (np. brak modelu)"},
        503: {"description": "Brak dostępnego endpointu LLM"},
    },
)
async def stream_simple_chat(
    request: SimpleChatRequest,
    session_store: Annotated[SessionStore | None, Depends(get_session_store)] = None,
):
    """Delegate the whole simple-stream flow to the service layer."""
    response = await stream_simple_chat_service(request)
    return persist_direct_response(response, request, session_store)


__all__ = ["release_onnx_simple_client", "router", "stream_simple_chat"]
