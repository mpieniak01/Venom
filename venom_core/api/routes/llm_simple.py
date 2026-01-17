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

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])
_request_tracer = None


def set_dependencies(request_tracer):
    global _request_tracer
    _request_tracer = request_tracer


class SimpleChatRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    session_id: Optional[str] = None


@router.post("/simple/stream")
async def stream_simple_chat(request: SimpleChatRequest):
    runtime = get_active_llm_runtime()
    model_name = request.model or runtime.model_name
    if not model_name:
        raise HTTPException(status_code=400, detail="Brak nazwy modelu LLM.")
    completions_url = _build_chat_completions_url(runtime)
    if not completions_url:
        raise HTTPException(status_code=503, detail="Brak endpointu LLM.")
    request_id: UUID = uuid4()
    if _request_tracer:
        prompt_preview = (
            request.content[:200] + "..."
            if len(request.content) > 200
            else request.content
        )
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
            "SimpleMode",
            "request",
            details=f"session_id={request.session_id or '-'} prompt={prompt_preview}",
        )

    messages = [{"role": "user", "content": request.content}]
    system_prompt = (SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT or "").strip()
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
    }
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if _request_tracer:
        preview_parts = []
        for message in messages:
            role = (message.get("role") or "").upper()
            content = message.get("content") or ""
            preview_parts.append(f"{role}:\n{content}")
        full_context = "\n\n".join(preview_parts).strip()
        max_len = 2000
        truncated = len(full_context) > max_len
        context_preview = (
            full_context[:max_len] + "...(truncated)" if truncated else full_context
        )
        _request_tracer.add_step(
            request_id,
            "SimpleMode",
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
            "SimpleMode",
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

    async def _stream_chunks() -> AsyncIterator[str]:
        full_text = ""
        chunk_count = 0
        stream_start = time.perf_counter()
        first_chunk_at: Optional[float] = None
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
                        raise HTTPException(
                            status_code=502,
                            detail=(
                                f"Błąd LLM ({runtime.provider}): "
                                f"{exc.response.status_code if exc.response else 'HTTP'}"
                            ),
                        ) from exc
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
                        choices = packet.get("choices") or []
                        for choice in choices:
                            delta = choice.get("delta") or {}
                            if not isinstance(delta, dict):
                                continue
                            content = delta.get("content")
                            if content:
                                chunk_count += 1
                                full_text += content
                                if first_chunk_at is None:
                                    first_chunk_at = time.perf_counter()
                                    if _request_tracer:
                                        elapsed_ms = int(
                                            (first_chunk_at - stream_start) * 1000
                                        )
                                        preview = (
                                            content[:200] + "..."
                                            if len(content) > 200
                                            else content
                                        )
                                        _request_tracer.add_step(
                                            request_id,
                                            "SimpleMode",
                                            "first_chunk",
                                            details=f"elapsed_ms={elapsed_ms} preview={preview}",
                                        )
                                yield content
            if _request_tracer:
                total_ms = int((time.perf_counter() - stream_start) * 1000)
                max_chars = 4000
                response_text = full_text
                truncated = False
                if len(response_text) > max_chars:
                    response_text = response_text[:max_chars] + "...(truncated)"
                    truncated = True
                _request_tracer.add_step(
                    request_id,
                    "SimpleMode",
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
        except httpx.HTTPError as exc:
            _record_simple_error(
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
            raise HTTPException(
                status_code=502,
                detail=f"Błąd połączenia z LLM ({runtime.provider}): {exc}",
            ) from exc

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Request-Id": str(request_id),
        "X-Session-Id": request.session_id or "",
    }
    return StreamingResponse(_stream_chunks(), media_type="text/plain", headers=headers)
