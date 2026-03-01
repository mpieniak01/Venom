"""Minimalny bypass do bezpośredniego streamingu LLM (tryb prosty)."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from venom_core.api.routes import system_deps
from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.config import SETTINGS
from venom_core.core.metrics import get_metrics_collector
from venom_core.core.tracer import TraceStatus
from venom_core.execution.onnx_llm_client import OnnxLlmClient
from venom_core.services import llm_simple_transport
from venom_core.services.llm_simple_payload_service import (
    apply_optional_features_to_payload as _apply_optional_features_to_payload,
)
from venom_core.services.llm_simple_payload_service import (
    apply_output_format_to_payload as _apply_output_format_to_payload,
)
from venom_core.services.llm_simple_payload_service import (
    build_messages as _build_messages,
)
from venom_core.services.llm_simple_payload_service import (
    build_streaming_headers as _build_streaming_headers,
)
from venom_core.services.llm_simple_payload_service import (
    extract_ollama_telemetry as _extract_ollama_telemetry,
)
from venom_core.services.llm_simple_payload_service import (
    extract_sse_contents as _extract_sse_contents,
)
from venom_core.services.llm_simple_payload_service import (
    extract_sse_tool_calls as _extract_sse_tool_calls,
)
from venom_core.services.llm_simple_payload_service import (
    is_retryable_ollama_http_error as _is_retryable_ollama_http_error,
)
from venom_core.services.llm_simple_payload_service import (
    is_retryable_ollama_status as _is_retryable_ollama_status,
)
from venom_core.services.llm_simple_payload_service import (
    normalize_ns_to_ms as _normalize_ns_to_ms,
)
from venom_core.services.llm_simple_payload_service import (
    resolve_output_format as _resolve_output_format,
)
from venom_core.services.llm_simple_stream_service import (
    SimpleStreamState as _SimpleStreamState,
)
from venom_core.services.llm_simple_stream_service import (
    apply_post_attempt_action as _apply_post_attempt_action_impl,
)
from venom_core.services.llm_simple_stream_service import (
    reset_stream_attempt_state as _reset_stream_attempt_state_impl,
)
from venom_core.services.llm_simple_stream_service import (
    resolve_post_attempt_action as _resolve_post_attempt_action_impl,
)
from venom_core.services.llm_simple_stream_service import (
    stream_single_attempt as _stream_single_attempt_impl,
)
from venom_core.services.llm_simple_stream_service import (
    update_stream_state_from_packet as _update_stream_state_from_packet_impl,
)
from venom_core.utils.llm_runtime import (
    _build_chat_completions_url,
    get_active_llm_runtime,
)
from venom_core.utils.ollama_tuning import build_ollama_runtime_options
from venom_core.utils.text import trim_to_char_limit

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])
_SIMPLE_MODE_STEP = "SimpleMode"
_PROMPT_PREVIEW_MAX_CHARS = 200
_CONTEXT_PREVIEW_MAX_CHARS = 2000
_RESPONSE_PREVIEW_MAX_CHARS = 4000
_ONNX_SIMPLE_CLIENT: OnnxLlmClient | None = None
_ONNX_SIMPLE_CLIENT_LOCK = threading.Lock()
httpx = llm_simple_transport.httpx_module()


def _get_onnx_simple_client() -> OnnxLlmClient:
    global _ONNX_SIMPLE_CLIENT
    if _ONNX_SIMPLE_CLIENT is None:
        with _ONNX_SIMPLE_CLIENT_LOCK:
            if _ONNX_SIMPLE_CLIENT is None:
                _ONNX_SIMPLE_CLIENT = OnnxLlmClient()
    return _ONNX_SIMPLE_CLIENT


def release_onnx_simple_client() -> None:
    """Drop warm ONNX simple-mode client to free runtime memory."""
    global _ONNX_SIMPLE_CLIENT
    with _ONNX_SIMPLE_CLIENT_LOCK:
        client = _ONNX_SIMPLE_CLIENT
        _ONNX_SIMPLE_CLIENT = None
    if client is not None:
        try:
            client.close()
        except Exception:
            # Cleanup path must be best-effort; runtime may be partially initialized.
            pass


def _get_simple_context_char_limit(runtime) -> Optional[int]:
    if runtime.provider != "vllm":
        return None
    max_ctx = getattr(SETTINGS, "VLLM_MAX_MODEL_LEN", 0) or 0
    if max_ctx <= 0:
        return None
    reserve = max(64, max_ctx // 4)
    input_tokens = max(32, max_ctx - reserve)
    return input_tokens * 4


def _get_request_tracer():
    return system_deps.get_request_tracer()


def _call_tracer(request_tracer: Any, method_name: str, *args, **kwargs) -> bool:
    if not request_tracer:
        return False
    method = getattr(request_tracer, method_name, None)
    if not callable(method):
        return False
    method(*args, **kwargs)
    return True


def _build_preview(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _trace_simple_request(
    request_id: UUID, request: "SimpleChatRequest", runtime, model_name: str
) -> None:
    request_tracer = _get_request_tracer()
    if not _call_tracer(
        request_tracer,
        "create_trace",
        request_id,
        request.content,
        session_id=request.session_id,
    ):
        return
    _call_tracer(
        request_tracer,
        "set_llm_metadata",
        request_id,
        provider=runtime.provider,
        model=model_name,
        endpoint=runtime.endpoint,
        metadata={
            "config_hash": runtime.config_hash,
            "runtime_id": runtime.runtime_id,
        },
    )
    _call_tracer(request_tracer, "update_status", request_id, TraceStatus.PROCESSING)
    _call_tracer(
        request_tracer,
        "add_step",
        request_id,
        _SIMPLE_MODE_STEP,
        "request",
        details=(
            f"session_id={request.session_id or '-'} "
            f"prompt={_build_preview(request.content, max_chars=_PROMPT_PREVIEW_MAX_CHARS)}"
        ),
    )


def _trace_context_preview(request_id: UUID, messages: list[dict[str, str]]) -> None:
    request_tracer = _get_request_tracer()
    if not request_tracer:
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
    _call_tracer(
        request_tracer,
        "add_step",
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
    request_tracer = _get_request_tracer()
    _call_tracer(
        request_tracer,
        "add_step",
        request_id,
        _SIMPLE_MODE_STEP,
        "error",
        status="error",
        details=error_message,
    )
    _call_tracer(
        request_tracer,
        "set_error_metadata",
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
    _call_tracer(request_tracer, "update_status", request_id, TraceStatus.FAILED)


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
    output_format = _resolve_output_format(
        request_format=request.format,
        response_format=request.response_format,
    )
    _apply_output_format_to_payload(
        payload=payload,
        provider=runtime.provider,
        output_format=output_format,
        response_format=request.response_format,
        request_format=request.format,
        ollama_structured_outputs_enabled=SETTINGS.OLLAMA_ENABLE_STRUCTURED_OUTPUTS,
    )
    _apply_optional_features_to_payload(
        payload=payload,
        provider=runtime.provider,
        tools=request.tools,
        tool_choice=request.tool_choice,
        think=request.think,
        ollama_enable_tool_calling=SETTINGS.OLLAMA_ENABLE_TOOL_CALLING,
        ollama_enable_think=SETTINGS.OLLAMA_ENABLE_THINK,
    )

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
    request_tracer = _get_request_tracer()
    if was_trimmed and request_tracer:
        _call_tracer(
            request_tracer,
            "add_step",
            request_id,
            _SIMPLE_MODE_STEP,
            "prompt_trim",
            status="ok",
            details=f"Trimmed prompt to {available} chars for vLLM limit",
        )
    return trimmed_content


async def _iter_stream_packets(resp: httpx.Response) -> AsyncIterator[dict]:
    async for packet in llm_simple_transport.iter_stream_packets(resp):
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
    request_tracer = _get_request_tracer()
    if not request_tracer:
        return
    elapsed_ms = int((time.perf_counter() - stream_start) * 1000)
    _call_tracer(
        request_tracer,
        "add_step",
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
    request_tracer = _get_request_tracer()
    if not request_tracer:
        return
    total_ms = int((time.perf_counter() - stream_start) * 1000)
    truncated = len(full_text) > _RESPONSE_PREVIEW_MAX_CHARS
    response_text = (
        f"{full_text[:_RESPONSE_PREVIEW_MAX_CHARS]}...(truncated)"
        if truncated
        else full_text
    )
    _call_tracer(
        request_tracer,
        "add_step",
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
    _call_tracer(request_tracer, "update_status", request_id, TraceStatus.COMPLETED)


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
    return await llm_simple_transport.read_http_error_response_text(response)


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
    request_tracer = _get_request_tracer()
    if request_tracer:
        _call_tracer(
            request_tracer,
            "add_step",
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
    return _update_stream_state_from_packet_impl(
        packet=packet,
        runtime=runtime,
        state=state,
        ollama_telemetry=ollama_telemetry,
        extract_ollama_telemetry_fn=_extract_ollama_telemetry,
        extract_sse_tool_calls_fn=_extract_sse_tool_calls,
        extract_sse_contents_fn=_extract_sse_contents,
        on_first_chunk_fn=lambda content: _trace_first_chunk(
            request_id, stream_start, content
        ),
    )


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
    provider_name = str(getattr(runtime, "provider", "") or "llm_runtime")
    emitted = await _stream_single_attempt_impl(
        open_stream_response_fn=llm_simple_transport.open_stream_response,
        iter_stream_packets_fn=_iter_stream_packets,
        completions_url=completions_url,
        payload=payload,
        provider_name=provider_name,
        state=state,
        http_status_error_type=httpx.HTTPStatusError,
        attempt=attempt,
        max_attempts=max_attempts,
        is_retryable_status_fn=_is_retryable_ollama_status,
        runtime_provider=runtime.provider,
        retry_backoff=retry_backoff,
        sleep_fn=asyncio.sleep,
        handle_packet_fn=lambda packet: _update_stream_state_from_packet(
            packet=packet,
            runtime=runtime,
            state=state,
            request_id=request_id,
            stream_start=stream_start,
            ollama_telemetry=ollama_telemetry,
        ),
        emit_http_error_fn=lambda exc: _emit_http_status_error_and_mark_failed(
            exc=exc,
            runtime=runtime,
            request_id=request_id,
            model_name=model_name,
            stream_start=stream_start,
        ),
    )
    if state.retry_requested:
        ollama_telemetry.clear()
    for event in emitted:
        yield event


def _reset_stream_attempt_state(state: _SimpleStreamState) -> None:
    _reset_stream_attempt_state_impl(state)


def _finalize_successful_stream_attempt(
    *,
    runtime,
    request_id: UUID,
    stream_start: float,
    state: _SimpleStreamState,
    ollama_telemetry: dict[str, int],
) -> None:
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
            load_duration_ms=_normalize_ns_to_ms(ollama_telemetry.get("load_duration")),
            prompt_eval_count=ollama_telemetry.get("prompt_eval_count"),
            eval_count=ollama_telemetry.get("eval_count"),
            prompt_eval_duration_ms=_normalize_ns_to_ms(
                ollama_telemetry.get("prompt_eval_duration")
            ),
            eval_duration_ms=_normalize_ns_to_ms(ollama_telemetry.get("eval_duration")),
        )


def _resolve_post_attempt_action(
    *,
    runtime,
    request_id: UUID,
    stream_start: float,
    state: _SimpleStreamState,
    ollama_telemetry: dict[str, int],
) -> str:
    return _resolve_post_attempt_action_impl(
        state=state,
        finalize_success_fn=lambda: _finalize_successful_stream_attempt(
            runtime=runtime,
            request_id=request_id,
            stream_start=stream_start,
            state=state,
            ollama_telemetry=ollama_telemetry,
        ),
    )


def _apply_post_attempt_action(action: str) -> tuple[bool, bool]:
    """Converts action token into retry/done flags for stream control flow."""
    return _apply_post_attempt_action_impl(action)


async def _handle_stream_http_error(
    *,
    exc: httpx.HTTPError,
    runtime,
    request_id: UUID,
    model_name: str,
    stream_start: float,
    attempt: int,
    max_attempts: int,
    retry_backoff: float,
    chunk_count: int,
    ollama_telemetry: dict[str, int],
) -> str:
    if chunk_count == 0 and _is_retryable_ollama_http_error(
        provider=runtime.provider,
        status_code=None,
        attempt_no=attempt,
        max_retries=max_attempts,
    ):
        ollama_telemetry.clear()
        await asyncio.sleep(retry_backoff * attempt)
        return "retry"

    yield_event = _emit_connection_error_and_mark_failed(
        exc=exc,
        runtime=runtime,
        request_id=request_id,
        model_name=model_name,
        stream_start=stream_start,
    )
    return yield_event


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
            _reset_stream_attempt_state(state)
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

            action = _resolve_post_attempt_action(
                runtime=runtime,
                request_id=request_id,
                stream_start=stream_start,
                state=state,
                ollama_telemetry=ollama_telemetry,
            )
            should_retry, should_emit_done = _apply_post_attempt_action(action)
            if should_retry:
                continue
            if should_emit_done:
                yield "event: done\ndata: {}\n\n"
            return

        except httpx.HTTPError as exc:
            result = await _handle_stream_http_error(
                exc=exc,
                runtime=runtime,
                request_id=request_id,
                model_name=model_name,
                stream_start=stream_start,
                attempt=attempt,
                max_attempts=max_attempts,
                retry_backoff=retry_backoff,
                chunk_count=state.chunk_count,
                ollama_telemetry=ollama_telemetry,
            )
            if result == "retry":
                continue

            yield result
            return
        except Exception as exc:
            yield _emit_internal_error_and_mark_failed(
                exc=exc,
                runtime=runtime,
                request_id=request_id,
                stream_start=stream_start,
            )
            return


async def _stream_simple_chunks_onnx(
    *,
    runtime,
    request_id: UUID,
    model_name: str,
    messages: list[dict[str, str]],
    max_tokens: int | None,
    temperature: float | None,
) -> AsyncIterator[str]:
    stream_start = time.perf_counter()
    chunks: list[str] = []
    chunk_count = 0
    first_chunk_seen = False

    yield "event: start\ndata: {}\n\n"
    try:
        # Keep a warm ONNX client in API process to avoid reloading model
        # between consecutive simple-mode requests.
        client = _get_onnx_simple_client()
        for content in client.stream_generate(
            messages=messages,
            max_new_tokens=max_tokens,
            temperature=temperature,
        ):
            if not content:
                continue
            chunk_count += 1
            chunks.append(content)
            if not first_chunk_seen:
                _trace_first_chunk(request_id, stream_start, content)
                first_chunk_seen = True
            yield "event: content\ndata: " + json.dumps({"text": content}) + "\n\n"

        _trace_stream_completion(request_id, "".join(chunks), chunk_count, stream_start)
        collector = get_metrics_collector()
        collector.record_provider_request(
            provider=runtime.provider,
            success=True,
            latency_ms=(time.perf_counter() - stream_start) * 1000.0,
        )
        yield "event: done\ndata: {}\n\n"
    except Exception as exc:
        _record_simple_error(
            request_id,
            error_code="onnx_generation_error",
            error_message=f"Błąd generacji ONNX: {exc}",
            error_details={"provider": "onnx", "model": model_name},
            error_class=exc.__class__.__name__,
            retryable=False,
        )
        collector = get_metrics_collector()
        collector.record_provider_request(
            provider=runtime.provider,
            success=False,
            latency_ms=(time.perf_counter() - stream_start) * 1000.0,
            error_code="onnx_generation_error",
        )
        yield (
            "event: error\ndata: "
            + json.dumps(
                {"code": "onnx_generation_error", "message": f"Błąd ONNX: {exc}"}
            )
            + "\n\n"
        )


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
    request_id: UUID = uuid4()
    _trace_simple_request(request_id, request, runtime, model_name)

    system_prompt = (SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT or "").strip()
    user_content = _trim_user_content_for_runtime(
        request.content, system_prompt, runtime, request_id
    )
    messages = _build_messages(system_prompt, user_content)
    payload = _build_payload(request, runtime, model_name, messages)
    _trace_context_preview(request_id, messages)
    headers = _build_streaming_headers(str(request_id), request.session_id or "")
    runtime_provider = str(getattr(runtime, "provider", "") or "").lower()
    runtime_service_type = str(getattr(runtime, "service_type", "") or "").lower()
    if runtime_provider == "onnx" or runtime_service_type == "onnx":
        return StreamingResponse(
            _stream_simple_chunks_onnx(
                runtime=runtime,
                request_id=request_id,
                model_name=model_name,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            ),
            media_type="text/event-stream",
            headers=headers,
        )

    completions_url = _build_chat_completions_url(runtime)
    if not completions_url:
        raise HTTPException(status_code=503, detail="Brak endpointu LLM.")
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
