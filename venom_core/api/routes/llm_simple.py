"""Minimal HTTP adapter for the simple LLM streaming endpoint."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from venom_core.api.dependencies import get_session_store
from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services.chat_history import persist_direct_response
from venom_core.services.llm_simple_service import release_onnx_simple_client
from venom_core.services.llm_simple_service import (
    stream_simple_chat as stream_simple_chat_service,
)
from venom_core.services.session_store import SessionStore
from venom_core.services.studio_normal_chat import prepare_studio_normal

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


@router.post(
    "/simple/stream",
    responses={
        400: {"description": "Nieprawidłowe dane wejściowe (np. brak modelu)"},
        413: {
            "description": "Conversation history or material context exceeds the runtime input limit"
        },
        503: {"description": "Brak dostępnego endpointu LLM"},
    },
)
async def stream_simple_chat(
    request: SimpleChatRequest,
    session_store: Annotated[SessionStore | None, Depends(get_session_store)] = None,
    http_request: Request = cast(Request, None),
):
    """Delegate the whole simple-stream flow to the service layer."""
    if request.studio_normal:
        runtime = (
            getattr(http_request.app.state, "studio_runtime", None)
            if http_request is not None
            else None
        )
        if runtime is None:
            raise HTTPException(400, "studio_normal_requires_studio")
        prepared, system_context = await prepare_studio_normal(
            request, session_store, runtime.get_vector_store
        )
        response = await stream_simple_chat_service(
            prepared, system_context=system_context
        )
    else:
        response = await stream_simple_chat_service(request)
    return persist_direct_response(response, request, session_store)


__all__ = ["release_onnx_simple_client", "router", "stream_simple_chat"]
