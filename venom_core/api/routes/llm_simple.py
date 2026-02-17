"""Minimalny bypass do bezpośredniego streamingu LLM (tryb prosty)."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from venom_core.config import SETTINGS
from venom_core.core.metrics import get_metrics_collector
from venom_core.core.tracer import TraceStatus
from venom_core.utils.llm_runtime import (
    _build_chat_completions_url,
    get_active_llm_runtime,
)
from venom_core.utils.ollama_tuning import build_ollama_runtime_options
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
        payload["options"] = build_ollama_runtime_options(SETTINGS)

    # Keep a deterministic precedence to avoid sending both `response_format` and
    # `format` in one payload:
    # 1) For Ollama we prefer `format` (native structured output support).
    # 2) For non-Ollama providers we prefer client-provided `response_format`.
    # 3) Fallback: `request.format` (if response_format is absent).
    output_format = _resolve_output_format(request)
    _apply_output_format_to_payload(
        payload=payload,
        request=request,
        runtime=runtime,
        output_format=output_format,
    )
    _apply_optional_features_to_payload(
        payload=payload, request=request, runtime=runtime
    )

    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    return payload


def _resolve_output_format(request: "SimpleChatRequest") -> Any:
    output_format = request.format
    if output_format is not None or not isinstance(request.response_format, dict):
        return output_format

    # Compatibility extraction for OpenAI-style shape:
    # response_format.json_schema.schema -> schema object
    schema_block = request.response_format.get("json_schema")
    if not isinstance(schema_block, dict):
        return output_format
    return schema_block.get("schema") or schema_block


def _apply_output_format_to_payload(
    *,
    payload: dict[str, Any],
    request: "SimpleChatRequest",
    runtime,
    output_format: Any,
) -> None:
    if runtime.provider == "ollama":
        if output_format is not None and SETTINGS.OLLAMA_ENABLE_STRUCTURED_OUTPUTS:
            payload["format"] = output_format
            return
        if request.response_format is not None:
            payload["response_format"] = request.response_format
        return

    if request.response_format is not None:
        payload["response_format"] = request.response_format
    elif request.format is not None:
        payload["format"] = request.format


def _ollama_feature_enabled(runtime, enabled_flag: bool) -> bool:
    return runtime.provider != "ollama" or enabled_flag


def _apply_optional_features_to_payload(
    *, payload: dict[str, Any], request: "SimpleChatRequest", runtime
) -> None:
    if request.tools and _ollama_feature_enabled(
        runtime, SETTINGS.OLLAMA_ENABLE_TOOL_CALLING
    ):
        payload["tools"] = request.tools
    if request.tool_choice is not None and _ollama_feature_enabled(
        runtime, SETTINGS.OLLAMA_ENABLE_TOOL_CALLING
    ):
        payload["tool_choice"] = request.tool_choice
    if request.think is not None and _ollama_feature_enabled(
        runtime, SETTINGS.OLLAMA_ENABLE_THINK
    ):
        payload["think"] = request.think


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


def _extract_sse_tool_calls(packet: dict) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    choices = packet.get("choices") or []
    for choice in choices:
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            continue
        delta_tool_calls = delta.get("tool_calls")
        if isinstance(delta_tool_calls, list):
            tool_calls.extend(
                call for call in delta_tool_calls if isinstance(call, dict)
            )
    return tool_calls


def _extract_ollama_telemetry(packet: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in (
        "load_duration",
        "prompt_eval_count",
        "eval_count",
        "prompt_eval_duration",
        "eval_duration",
    ):
        value = packet.get(key)
        if isinstance(value, int):
            out[key] = value
    return out


def _normalize_ns_to_ms(value: Optional[int]) -> Optional[float]:
    if value is None:
        return None
    if value <= 0:
        return 0.0
    return round(value / 1_000_000.0, 2)


async def _iter_stream_packets(resp: httpx.Response) -> AsyncIterator[dict]:
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
        if isinstance(packet, dict):
            yield packet


async def _iter_stream_contents(resp: httpx.Response) -> AsyncIterator[str]:
    async for packet in _iter_stream_packets(resp):
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


def _build_llm_http_error(
    exc: httpx.HTTPStatusError,
    runtime,
    model_name: str,
    *,
    response_text: str = "",
) -> tuple[str, dict, dict]:
    error_message = (
        f"LLM HTTP {exc.response.status_code} dla {runtime.provider}"
        if exc.response
        else f"LLM HTTP error dla {runtime.provider}"
    )
    error_details = {
        "status_code": exc.response.status_code if exc.response else None,
        "response": response_text[:2000],
        "provider": runtime.provider,
        "endpoint": runtime.endpoint,
        "model": model_name,
    }
    error_payload = {
        "code": "llm_http_error",
        "message": (
            f"Błąd LLM ({runtime.provider}): "
            f"{exc.response.status_code if exc.response else 'HTTP'}"
        ),
    }
    return error_message, error_details, error_payload


async def _read_http_error_response_text(response: Optional[httpx.Response]) -> str:
    if response is None:
        return ""
    try:
        body = await response.aread()
    except Exception:
        return ""
    if not body:
        return ""
    encoding = response.encoding or "utf-8"
    return body.decode(encoding, errors="replace")


def _build_streaming_headers(
    request_id: UUID, session_id: Optional[str]
) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Request-Id": str(request_id),
        "X-Session-Id": session_id or "",
    }


@dataclass
class _SimpleStreamState:
    chunks: list[str]
    chunk_count: int = 0
    first_chunk_seen: bool = False
    retry_requested: bool = False
    failed: bool = False
    completed: bool = False


def _is_retryable_ollama_status(
    *,
    runtime,
    status_code: Optional[int],
    attempt: int,
    max_attempts: int,
    chunk_count: int,
) -> bool:
    return bool(
        runtime.provider == "ollama"
        and status_code in {429, 500, 502, 503, 504}
        and attempt < max_attempts
        and chunk_count == 0
    )


def _is_retryable_ollama_http_error(
    *, runtime, attempt: int, max_attempts: int, chunk_count: int
) -> bool:
    return bool(
        runtime.provider == "ollama" and attempt < max_attempts and chunk_count == 0
    )


async def _emit_http_status_error_and_mark_failed(
    *,
    exc: httpx.HTTPStatusError,
    runtime,
    request_id: UUID,
    model_name: str,
    stream_start: float,
) -> str:
    status_code = exc.response.status_code if exc.response else None
    response_text = await _read_http_error_response_text(exc.response)
    error_message, error_details, error_payload = _build_llm_http_error(
        exc, runtime, model_name, response_text=response_text
    )
    _record_simple_error(
        request_id,
        error_code="llm_http_error",
        error_message=error_message,
        error_details=error_details,
        error_class=exc.__class__.__name__,
        retryable=False,
    )
    collector = get_metrics_collector()
    collector.record_provider_request(
        provider=runtime.provider,
        success=False,
        latency_ms=(time.perf_counter() - stream_start) * 1000.0,
        error_code=f"http_{status_code or 'error'}",
    )
    return f"event: error\ndata: {json.dumps(error_payload)}\n\n"


def _emit_connection_error_and_mark_failed(
    *,
    exc: httpx.HTTPError,
    runtime,
    request_id: UUID,
    model_name: str,
    stream_start: float,
) -> str:
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
    collector = get_metrics_collector()
    collector.record_provider_request(
        provider=runtime.provider,
        success=False,
        latency_ms=(time.perf_counter() - stream_start) * 1000.0,
        error_code="connection_error",
    )
    error_payload = {
        "code": "llm_connection_error",
        "message": f"Błąd połączenia z LLM ({runtime.provider}): {exc}",
    }
    return f"event: error\ndata: {json.dumps(error_payload)}\n\n"


def _emit_internal_error_and_mark_failed(
    *, exc: Exception, runtime, request_id: UUID, stream_start: float
) -> str:
    if _request_tracer:
        _request_tracer.add_step(
            request_id,
            _SIMPLE_MODE_STEP,
            "error",
            status="error",
            details=str(exc),
        )
    collector = get_metrics_collector()
    collector.record_provider_request(
        provider=runtime.provider,
        success=False,
        latency_ms=(time.perf_counter() - stream_start) * 1000.0,
        error_code="internal_error",
    )
    error_payload = {
        "code": "internal_error",
        "message": f"Nieoczekiwany błąd: {exc}",
    }
    return f"event: error\ndata: {json.dumps(error_payload)}\n\n"


def _update_stream_state_from_packet(
    *,
    packet: dict[str, Any],
    runtime,
    state: _SimpleStreamState,
    request_id: UUID,
    stream_start: float,
    ollama_telemetry: dict[str, int],
) -> list[str]:
    emitted_events: list[str] = []
    if runtime.provider == "ollama":
        telemetry = _extract_ollama_telemetry(packet)
        if telemetry:
            ollama_telemetry.update(telemetry)

    tool_calls = _extract_sse_tool_calls(packet)
    if tool_calls:
        emitted_events.append(
            "event: tool_calls\ndata: "
            + json.dumps({"tool_calls": tool_calls})
            + "\n\n"
        )

    for content in _extract_sse_contents(packet):
        state.chunk_count += 1
        state.chunks.append(content)
        if not state.first_chunk_seen:
            _trace_first_chunk(request_id, stream_start, content)
            state.first_chunk_seen = True
        event_payload = {"text": content}
        emitted_events.append(
            "event: content\ndata: " + json.dumps(event_payload) + "\n\n"
        )

    return emitted_events


async def _stream_single_attempt(
    *,
    completions_url: str,
    payload: dict,
    runtime,
    request_id: UUID,
    model_name: str,
    stream_start: float,
    attempt: int,
    max_attempts: int,
    retry_backoff: float,
    state: _SimpleStreamState,
    ollama_telemetry: dict[str, int],
) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", completions_url, json=payload) as resp:
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response else None
                if _is_retryable_ollama_status(
                    runtime=runtime,
                    status_code=status_code,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    chunk_count=state.chunk_count,
                ):
                    state.retry_requested = True
                    ollama_telemetry.clear()
                    await asyncio.sleep(retry_backoff * attempt)
                    return
                state.failed = True
                yield await _emit_http_status_error_and_mark_failed(
                    exc=exc,
                    runtime=runtime,
                    request_id=request_id,
                    model_name=model_name,
                    stream_start=stream_start,
                )
                return

            async for packet in _iter_stream_packets(resp):
                for event in _update_stream_state_from_packet(
                    packet=packet,
                    runtime=runtime,
                    state=state,
                    request_id=request_id,
                    stream_start=stream_start,
                    ollama_telemetry=ollama_telemetry,
                ):
                    yield event

    state.completed = True


async def _stream_simple_chunks(
    *,
    completions_url: str,
    payload: dict,
    runtime,
    request_id: UUID,
    model_name: str,
) -> AsyncIterator[str]:
    state = _SimpleStreamState(chunks=[])
    stream_start = time.perf_counter()
    ollama_telemetry: dict[str, int] = {}

    yield "event: start\ndata: {}\n\n"

    max_attempts = (
        max(1, int(SETTINGS.OLLAMA_RETRY_MAX_ATTEMPTS))
        if runtime.provider == "ollama"
        else 1
    )
    retry_backoff = max(0.0, float(SETTINGS.OLLAMA_RETRY_BACKOFF_SECONDS))

    for attempt in range(1, max_attempts + 1):
        try:
            state.retry_requested = False
            state.failed = False
            state.completed = False
            async for event in _stream_single_attempt(
                completions_url=completions_url,
                payload=payload,
                runtime=runtime,
                request_id=request_id,
                model_name=model_name,
                stream_start=stream_start,
                attempt=attempt,
                max_attempts=max_attempts,
                retry_backoff=retry_backoff,
                state=state,
                ollama_telemetry=ollama_telemetry,
            ):
                yield event

            if state.retry_requested:
                continue
            if state.failed:
                return
            if not state.completed:
                continue

            _trace_stream_completion(
                request_id, "".join(state.chunks), state.chunk_count, stream_start
            )
            total_ms = (time.perf_counter() - stream_start) * 1000.0
            collector = get_metrics_collector()
            collector.record_provider_request(
                provider=runtime.provider,
                success=True,
                latency_ms=total_ms,
                tokens=(
                    int(ollama_telemetry.get("prompt_eval_count", 0))
                    + int(ollama_telemetry.get("eval_count", 0))
                ),
            )
            if runtime.provider == "ollama":
                collector.record_ollama_runtime_sample(
                    load_duration_ms=_normalize_ns_to_ms(
                        ollama_telemetry.get("load_duration")
                    ),
                    prompt_eval_count=ollama_telemetry.get("prompt_eval_count"),
                    eval_count=ollama_telemetry.get("eval_count"),
                    prompt_eval_duration_ms=_normalize_ns_to_ms(
                        ollama_telemetry.get("prompt_eval_duration")
                    ),
                    eval_duration_ms=_normalize_ns_to_ms(
                        ollama_telemetry.get("eval_duration")
                    ),
                )
            yield "event: done\ndata: {}\n\n"
            return

        except httpx.HTTPError as exc:
            if _is_retryable_ollama_http_error(
                runtime=runtime,
                attempt=attempt,
                max_attempts=max_attempts,
                chunk_count=state.chunk_count,
            ):
                ollama_telemetry.clear()
                await asyncio.sleep(retry_backoff * attempt)
                continue

            yield _emit_connection_error_and_mark_failed(
                exc=exc,
                runtime=runtime,
                request_id=request_id,
                model_name=model_name,
                stream_start=stream_start,
            )
            return
        except Exception as exc:
            yield _emit_internal_error_and_mark_failed(
                exc=exc,
                runtime=runtime,
                request_id=request_id,
                stream_start=stream_start,
            )
            return


class SimpleChatRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    response_format: Optional[dict[str, Any] | str] = None
    format: Optional[dict[str, Any] | str] = None
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[dict[str, Any] | str] = None
    think: Optional[bool] = None
    session_id: Optional[str] = None


@router.post(
    "/simple/stream",
    responses={
        400: {"description": "Nieprawidłowe dane wejściowe (np. brak modelu)"},
        503: {"description": "Brak dostępnego endpointu LLM"},
    },
)
async def stream_simple_chat(request: SimpleChatRequest):
    await asyncio.sleep(0)
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
    headers = _build_streaming_headers(request_id, request.session_id)
    return StreamingResponse(
        _stream_simple_chunks(
            completions_url=completions_url,
            payload=payload,
            runtime=runtime,
            request_id=request_id,
            model_name=model_name,
        ),
        media_type="text/event-stream",
        headers=headers,
    )
