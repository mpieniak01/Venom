"""Minimalny bypass do bezpośredniego streamingu LLM (tryb prosty)."""

from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from venom_core.config import SETTINGS
from venom_core.core.tracer import TraceStatus
from venom_core.utils.llm_runtime import (
    _build_chat_completions_url,
    get_active_llm_runtime,
)
from venom_core.utils.text import trim_to_char_limit

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])
_request_tracer = None
_SIMPLE_MODE_STEP = "SimpleMode"
_PROMPT_PREVIEW_MAX_CHARS = 200
_CONTEXT_PREVIEW_MAX_CHARS = 2000
_RESPONSE_PREVIEW_MAX_CHARS = 4000


def _get_simple_context_char_limit(runtime) -> Optional[int]:
    if runtime.provider != "vllm":
        return None
    max_ctx = getattr(SETTINGS, "VLLM_MAX_MODEL_LEN", 0) or 0
    if max_ctx <= 0:
        return None
    reserve = max(64, max_ctx // 4)
    input_tokens = max(32, max_ctx - reserve)
    return input_tokens * 4


def set_dependencies(request_tracer):
    global _request_tracer
    _request_tracer = request_tracer


def _build_preview(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _trace_simple_request(
    request_id: UUID, request: "SimpleChatRequest", runtime, model_name: str
) -> None:
    if not _request_tracer:
        return
    _request_tracer.create_trace(
        request_id,
        request.content,
        session_id=request.session_id,
    )
    _request_tracer.set_llm_metadata(
        request_id,
        provider=runtime.provider,
        model=model_name,
        endpoint=runtime.endpoint,
        metadata={
            "config_hash": runtime.config_hash,
            "runtime_id": runtime.runtime_id,
        },
    )
    _request_tracer.update_status(request_id, TraceStatus.PROCESSING)
    _request_tracer.add_step(
        request_id,
        _SIMPLE_MODE_STEP,
        "request",
        details=(
            f"session_id={request.session_id or '-'} "
            f"prompt={_build_preview(request.content, max_chars=_PROMPT_PREVIEW_MAX_CHARS)}"
        ),
    )


def _trace_context_preview(request_id: UUID, messages: list[dict[str, str]]) -> None:
    if not _request_tracer:
        return
    preview_parts = []
    for message in messages:
        role = (message.get("role") or "").upper()
        content = message.get("content") or ""
        preview_parts.append(f"{role}:\n{content}")
    full_context = "\n\n".join(preview_parts).strip()
    truncated = len(full_context) > _CONTEXT_PREVIEW_MAX_CHARS
    context_preview = (
        f"{full_context[:_CONTEXT_PREVIEW_MAX_CHARS]}...(truncated)"
        if truncated
        else full_context
    )
    _request_tracer.add_step(
        request_id,
        _SIMPLE_MODE_STEP,
        "context_preview",
        status="ok",
        details=json.dumps(
            {
                "mode": "direct",
                "prompt_context_preview": context_preview,
                "prompt_context_truncated": truncated,
                "hidden_prompts_count": 0,
            }
        ),
    )


def _record_simple_error(
    request_id: UUID,
    *,
    error_code: str,
    error_message: str,
    error_details: dict,
    error_class: Optional[str] = None,
    retryable: bool = True,
) -> None:
    if not _request_tracer:
        return
    _request_tracer.add_step(
        request_id,
        _SIMPLE_MODE_STEP,
        "error",
        status="error",
        details=error_message,
    )
    _request_tracer.set_error_metadata(
        request_id,
        {
            "error_code": error_code,
            "error_class": error_class or error_code,
            "error_message": error_message,
            "error_details": error_details,
            "stage": "simple_mode",
            "retryable": retryable,
        },
    )
    _request_tracer.update_status(request_id, TraceStatus.FAILED)


def _build_messages(system_prompt: str, user_content: str) -> list[dict[str, str]]:
    messages = [{"role": "user", "content": user_content}]
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})
    return messages


def _build_payload(
    request: "SimpleChatRequest",
    runtime,
    model_name: str,
    messages: list[dict[str, str]],
) -> dict:
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
    }
    if runtime.provider == "ollama":
        payload["keep_alive"] = SETTINGS.LLM_KEEP_ALIVE
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    return payload


def _trim_user_content_for_runtime(
    user_content: str,
    system_prompt: str,
    runtime,
    request_id: UUID,
) -> str:
    char_limit = _get_simple_context_char_limit(runtime)
    if not char_limit:
        return user_content

    overhead = len(system_prompt) + 32 if system_prompt else 0
    available = max(0, char_limit - overhead)
    trimmed_content, was_trimmed = trim_to_char_limit(user_content, available)
    if was_trimmed and _request_tracer:
        _request_tracer.add_step(
            request_id,
            _SIMPLE_MODE_STEP,
            "prompt_trim",
            status="ok",
            details=f"Trimmed prompt to {available} chars for vLLM limit",
        )
    return trimmed_content


def _extract_sse_contents(packet: dict) -> list[str]:
    contents: list[str] = []
    choices = packet.get("choices") or []
    for choice in choices:
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            continue
        content = delta.get("content")
        if content:
            contents.append(content)
    return contents


async def _iter_stream_contents(resp: httpx.Response) -> AsyncIterator[str]:
    async for line in resp.aiter_lines():
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data:
            continue
        if data == "[DONE]":
            break
        try:
            packet = json.loads(data)
        except json.JSONDecodeError:
            continue
        for content in _extract_sse_contents(packet):
            yield content


def _trace_first_chunk(
    request_id: UUID,
    stream_start: float,
    content: str,
) -> None:
    if not _request_tracer:
        return
    elapsed_ms = int((time.perf_counter() - stream_start) * 1000)
    _request_tracer.add_step(
        request_id,
        _SIMPLE_MODE_STEP,
        "first_chunk",
        details=(
            f"elapsed_ms={elapsed_ms} "
            f"preview={_build_preview(content, max_chars=_PROMPT_PREVIEW_MAX_CHARS)}"
        ),
    )


def _trace_stream_completion(
    request_id: UUID, full_text: str, chunk_count: int, stream_start: float
) -> None:
    if not _request_tracer:
        return
    total_ms = int((time.perf_counter() - stream_start) * 1000)
    truncated = len(full_text) > _RESPONSE_PREVIEW_MAX_CHARS
    response_text = (
        f"{full_text[:_RESPONSE_PREVIEW_MAX_CHARS]}...(truncated)"
        if truncated
        else full_text
    )
    _request_tracer.add_step(
        request_id,
        _SIMPLE_MODE_STEP,
        "response",
        details=json.dumps(
            {
                "chunks": chunk_count,
                "total_ms": total_ms,
                "chars": len(full_text),
                "response": response_text,
                "truncated": truncated,
            }
        ),
    )
    _request_tracer.update_status(request_id, TraceStatus.COMPLETED)


class SimpleChatRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    session_id: Optional[str] = None


@router.post(
    "/simple/stream",
    responses={
        400: {"description": "Nieprawidłowe dane wejściowe (np. brak modelu)"},
        503: {"description": "Brak dostępnego endpointu LLM"},
    },
)
def stream_simple_chat(request: SimpleChatRequest):
    runtime = get_active_llm_runtime()
    model_name = request.model or runtime.model_name
    if not model_name:
        raise HTTPException(status_code=400, detail="Brak nazwy modelu LLM.")
    completions_url = _build_chat_completions_url(runtime)
    if not completions_url:
        raise HTTPException(status_code=503, detail="Brak endpointu LLM.")
    request_id: UUID = uuid4()
    _trace_simple_request(request_id, request, runtime, model_name)

    system_prompt = (SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT or "").strip()
    user_content = _trim_user_content_for_runtime(
        request.content, system_prompt, runtime, request_id
    )
    messages = _build_messages(system_prompt, user_content)
    payload = _build_payload(request, runtime, model_name, messages)
    _trace_context_preview(request_id, messages)

    async def _stream_chunks() -> AsyncIterator[str]:
        full_text = ""
        chunk_count = 0
        stream_start = time.perf_counter()
        first_chunk_seen = False

        # Send initial event
        yield "event: start\ndata: {}\n\n"

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", completions_url, json=payload) as resp:
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        response_text = (
                            (exc.response.text or "") if exc.response else ""
                        )
                        _record_simple_error(
                            request_id,
                            error_code="llm_http_error",
                            error_message=(
                                f"LLM HTTP {exc.response.status_code} dla {runtime.provider}"
                                if exc.response
                                else f"LLM HTTP error dla {runtime.provider}"
                            ),
                            error_details={
                                "status_code": (
                                    exc.response.status_code if exc.response else None
                                ),
                                "response": response_text[:2000],
                                "provider": runtime.provider,
                                "endpoint": runtime.endpoint,
                                "model": model_name,
                            },
                            error_class=exc.__class__.__name__,
                            retryable=False,
                        )
                        # Instead of raising exception breaking the stream, yield error event
                        error_payload = {
                            "code": "llm_http_error",
                            "message": f"Błąd LLM ({runtime.provider}): {exc.response.status_code if exc.response else 'HTTP'}",
                        }
                        yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
                        return

                    async for content in _iter_stream_contents(resp):
                        chunk_count += 1
                        full_text += content
                        if not first_chunk_seen:
                            _trace_first_chunk(request_id, stream_start, content)
                            first_chunk_seen = True
                        event_payload = {"text": content}
                        yield f"event: content\ndata: {json.dumps(event_payload)}\n\n"

            _trace_stream_completion(request_id, full_text, chunk_count, stream_start)

            # End of stream
            yield "event: done\ndata: {}\n\n"

        except httpx.HTTPError as exc:
            _record_simple_error(
                request_id,
                error_code="llm_connection_error",
                error_message=f"Błąd połączenia z LLM ({runtime.provider}): {exc}",
                error_details={
                    "provider": runtime.provider,
                    "endpoint": runtime.endpoint,
                    "model": model_name,
                },
                error_class=exc.__class__.__name__,
                retryable=True,
            )
            # Yield error event instead of raising
            error_payload = {
                "code": "llm_connection_error",
                "message": f"Błąd połączenia z LLM ({runtime.provider}): {exc}",
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
        except Exception as exc:
            # Catch-all for other errors
            if _request_tracer:
                _request_tracer.add_step(
                    request_id,
                    _SIMPLE_MODE_STEP,
                    "error",
                    status="error",
                    details=str(exc),
                )
            error_payload = {
                "code": "internal_error",
                "message": f"Nieoczekiwany błąd: {exc}",
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Request-Id": str(request_id),
        "X-Session-Id": request.session_id or "",
    }
    return StreamingResponse(
        _stream_chunks(), media_type="text/event-stream", headers=headers
    )
