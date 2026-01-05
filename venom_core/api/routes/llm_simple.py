"""Minimalny bypass do bezpośredniego streamingu z Ollama (tryb prosty)."""

from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

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
    if runtime.provider != "ollama":
        raise HTTPException(
            status_code=409,
            detail="Tryb prosty wspiera tylko lokalny runtime Ollama.",
        )
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

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": request.content}],
        "stream": True,
    }
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature

    async def _stream_chunks() -> AsyncIterator[str]:
        full_text = ""
        chunk_count = 0
        stream_start = time.perf_counter()
        first_chunk_at: Optional[float] = None
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", completions_url, json=payload) as resp:
                    resp.raise_for_status()
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
                preview = (
                    (full_text[:200] + "...") if len(full_text) > 200 else full_text
                )
                _request_tracer.add_step(
                    request_id,
                    "SimpleMode",
                    "response",
                    details=f"chunks={chunk_count} total_ms={total_ms} chars={len(full_text)} preview={preview}",
                )
                _request_tracer.update_status(request_id, TraceStatus.COMPLETED)
        except httpx.HTTPError as exc:
            if _request_tracer:
                _request_tracer.update_status(request_id, TraceStatus.FAILED)
            raise HTTPException(
                status_code=502, detail=f"Błąd połączenia z Ollama: {exc}"
            ) from exc

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Request-Id": str(request_id),
        "X-Session-Id": request.session_id or "",
    }
    return StreamingResponse(_stream_chunks(), media_type="text/plain", headers=headers)
