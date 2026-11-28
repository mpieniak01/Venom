"""Service-layer entrypoint for the simple LLM streaming flow.

This mirrors the API route implementation so other services can reuse the
streaming logic without importing ``venom_core.api.routes``.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from venom_core.api.schemas.llm_simple import MAX_CHAT_HISTORY_CHARS, SimpleChatRequest
from venom_core.config import DEFAULT_SIMPLE_MODE_SYSTEM_PROMPT, SETTINGS
from venom_core.core.metrics import get_metrics_collector
from venom_core.core.tracer import TraceStatus
from venom_core.services import llm_simple_transport
from venom_core.services.chat_grounding import (
    PUBLIC_SOURCE_BLOCK,
    is_current_news_request,
)
from venom_core.services.chat_policy.direct_calculator import (
    execute_calculator,
    plan_calculator,
)
from venom_core.services.chat_policy.direct_drafts import (
    role_consent_reply,
    short_message_hint,
)
from venom_core.services.chat_policy.direct_text import (
    prepare_omni_history,
    simple_system_prompt,
)
from venom_core.services.chat_policy.qualified_chat import (
    GENERATION_TRUNCATED,
    CalendarClaimStream,
    QualifiedReply,
    prepare_reply,
    prepare_studio_reply,
)
from venom_core.services.chat_policy.qualified_chat_explanations import explanation_hint
from venom_core.services.chat_policy.qualified_chat_fit import (
    fit_bounds_hint,
    fit_bounds_reply,
    fit_hint,
)
from venom_core.services.chat_policy.qualified_chat_options import (
    CountRequirement,
    requested_count,
)
from venom_core.services.chat_policy.qualified_chat_quote import (
    english_translation_hint,
)
from venom_core.services.chat_policy.qualified_chat_revisions import (
    source_revision_hint,
)
from venom_core.services.chat_policy.qualified_chat_rss import RSSSummary
from venom_core.services.chat_policy.qualified_chat_writing import (
    ordinary_reply_hint,
    writing_hint,
)
from venom_core.services.chat_policy.review_draft import (
    REVIEW_RETRY_INSTRUCTION,
    ReviewDraft,
    parse_review_draft,
)
from venom_core.services.chat_policy.studio_calculator import plan_studio_calculation
from venom_core.services.chat_policy.studio_claims import (
    prepare_studio_claim_check,
    stated_packaging_reply,
    topic_only_sms,
)
from venom_core.services.chat_policy.studio_dialog import studio_dialog
from venom_core.services.chat_policy.studio_dialog_compare import studio_comparison
from venom_core.services.chat_policy.studio_followup import (
    studio_concise_hint,
    studio_followup,
)
from venom_core.services.chat_policy.studio_publication import (
    publication_check,
    publication_heading,
)
from venom_core.services.chat_policy.studio_quantity import studio_quantity
from venom_core.services.chat_policy.studio_revision import studio_revision
from venom_core.services.chat_policy.studio_visibility import studio_visibility
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
    extract_runtime_telemetry as _extract_runtime_telemetry,
)
from venom_core.services.llm_simple_payload_service import (
    extract_sse_contents as _extract_sse_contents,
)
from venom_core.services.llm_simple_payload_service import (
    extract_sse_tool_calls as _extract_sse_tool_calls,
)
from venom_core.services.llm_simple_payload_service import (
    is_retryable_runtime_http_error as _is_retryable_runtime_http_error,
)
from venom_core.services.llm_simple_payload_service import (
    is_retryable_runtime_status as _is_retryable_runtime_status,
)
from venom_core.services.llm_simple_payload_service import (
    normalize_ns_to_ms as _normalize_ns_to_ms,
)
from venom_core.services.llm_simple_payload_service import (
    resolve_output_format as _resolve_output_format,
)
from venom_core.services.llm_simple_payload_service import (
    token_usage_from_telemetry as _token_usage_from_telemetry,
)
from venom_core.services.llm_simple_stream_service import (
    SimpleStreamState as _SimpleStreamState,
)
from venom_core.services.llm_simple_stream_service import (
    StreamRetryConfig as _StreamRetryConfig,
)
from venom_core.services.llm_simple_stream_service import (
    StreamTransportConfig as _StreamTransportConfig,
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
from venom_core.services.ollama_audio import is_host_ollama
from venom_core.services.ollama_text_adapter import (
    QUALIFIED_MODEL,
    OllamaTextProfile,
    completed_native_draft,
    local_direct_model,
    native_chat_url,
    native_draft_payload,
    plain_text_rewrite,
    qualified_profile,
)
from venom_core.services.runtime_dependencies import (
    get_model_manager,
    get_request_tracer,
)
from venom_core.services.runtime_switch_gate import (
    assert_runtime_request_allowed,
    runtime_request_guard,
)
from venom_core.utils.llm_runtime import (
    LLMRuntimeInfo,
    _build_chat_completions_url,
    get_active_llm_runtime,
)
from venom_core.utils.logger import get_logger
from venom_core.utils.ollama_tuning import (
    build_ollama_runtime_options,
    normalize_ollama_keep_alive,
)
from venom_core.utils.runtime_names import is_multi_runtime
from venom_core.utils.text import trim_to_char_limit

logger = get_logger(__name__)

_SIMPLE_MODE_STEP = "SimpleMode"
_PROMPT_PREVIEW_MAX_CHARS = 200
_CONTEXT_PREVIEW_MAX_CHARS = 2000
_RESPONSE_PREVIEW_MAX_CHARS = 4000
_VAST_RUNTIME_PREFIX = "ollama@vast:"
_SSE_EVENT_START = "event: start\ndata: {}\n\n"
_SSE_EVENT_DONE = "event: done\ndata: {}\n\n"
_SSE_CONTENT_PREFIX = "event: content\ndata: "
_SSE_MEDIA_TYPE = "text/event-stream"
_NON_STREAM_INVALID_RESPONSE_CODE = "llm_invalid_response"
httpx = llm_simple_transport.httpx_module()


def release_onnx_simple_client() -> None:
    """Compatibility shutdown hook; Simple owns no in-process ONNX resources.

    Worker lifecycle belongs to its component controller, not this API hook.
    """


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
    return get_request_tracer()


async def _get_active_adapter_id() -> str | None:
    manager = get_model_manager()
    if manager is None:
        return None
    info_getter = getattr(manager, "get_active_adapter_info", None)
    if not callable(info_getter):
        return None
    try:
        active = info_getter()
        if asyncio.iscoroutine(active):
            active = await active
    except (TypeError, ValueError, RuntimeError):
        return None
    if not isinstance(active, dict):
        return None
    adapter_id = str(active.get("adapter_id") or "").strip()
    return adapter_id or None


def _resolve_model_name_for_simple_request(
    *,
    request_model: str | None,
    runtime_model: str | None,
    active_adapter_id: str | None,
) -> str:
    requested = str(request_model or "").strip()
    runtime_selected = str(runtime_model or "").strip()
    adapter_prefix = "venom-adapter-"
    runtime_is_adapter = runtime_selected.startswith(adapter_prefix)
    request_is_adapter = requested.startswith(adapter_prefix)
    if active_adapter_id:
        expected_adapter_model = f"{adapter_prefix}{active_adapter_id}"
        if request_is_adapter:
            return requested
        if runtime_is_adapter:
            return runtime_selected
        return expected_adapter_model
    return requested or runtime_selected


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
    adapter_prefix = "venom-adapter-"
    adapter_applied = str(model_name or "").startswith(adapter_prefix)
    adapter_id = (
        str(model_name or "")[len(adapter_prefix) :].strip()
        if adapter_applied
        else None
    )
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
            "adapter_applied": adapter_applied,
            "adapter_id": adapter_id,
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


def _trace_context_preview(request_id: UUID, messages: list[dict[str, Any]]) -> None:
    request_tracer = _get_request_tracer()
    if not request_tracer:
        return
    preview_parts = []
    for message in messages:
        role = (message.get("role") or "").upper()
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "") if item.get("type") == "text" else "[image]"
                for item in content
                if isinstance(item, dict)
            )
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
    messages: list[dict[str, Any]],
    *,
    stream: bool = True,
) -> dict:
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": stream,
    }
    if stream and runtime.provider in {"ollama", "vllm", "openai", "onnx"}:
        payload["stream_options"] = {"include_usage": True}
    from venom_core.services.vast_chat_runtime import is_remote

    if runtime.provider == "ollama" and not is_remote(runtime):
        payload["keep_alive"] = normalize_ollama_keep_alive(SETTINGS.LLM_KEEP_ALIVE)
        payload["options"] = build_ollama_runtime_options(SETTINGS)

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
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.seed is not None:
        payload["seed"] = request.seed
    if request.logprobs is not None:
        payload["logprobs"] = bool(request.logprobs)
    if request.top_logprobs is not None:
        payload["top_logprobs"] = int(request.top_logprobs)
    return payload


def _extract_logprobs_telemetry(data: dict[str, Any]) -> dict[str, Any] | None:
    content = _extract_logprobs_content(data)
    if content is None:
        return None
    normalized = _normalize_logprobs_content(content)
    if not normalized:
        return None
    return {
        "kind": "logprobs",
        "content": normalized,
    }


def _extract_logprobs_content(data: dict[str, Any]) -> list[Any] | None:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    logprobs = first_choice.get("logprobs")
    if not isinstance(logprobs, dict):
        return None
    content = logprobs.get("content")
    return content if isinstance(content, list) else None


def _normalize_logprobs_content(content: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in content[:128]:
        normalized_item = _normalize_logprobs_item(item)
        if normalized_item is not None:
            normalized.append(normalized_item)
    return normalized


def _normalize_logprobs_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    raw_logprob = item.get("logprob")
    if not isinstance(raw_logprob, (int, float)):
        return None
    return {
        "token": str(item.get("token") or ""),
        "logprob": float(raw_logprob),
        "top_logprobs": _normalize_top_logprobs(item.get("top_logprobs")),
    }


def _normalize_top_logprobs(top_logprobs_raw: Any) -> list[dict[str, Any]]:
    if not isinstance(top_logprobs_raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for top_item in top_logprobs_raw[:8]:
        normalized_item = _normalize_top_logprobs_item(top_item)
        if normalized_item is not None:
            normalized.append(normalized_item)
    return normalized


def _normalize_top_logprobs_item(top_item: Any) -> dict[str, Any] | None:
    if not isinstance(top_item, dict):
        return None
    top_logprob = top_item.get("logprob")
    if not isinstance(top_logprob, (int, float)):
        return None
    return {"token": str(top_item.get("token") or ""), "logprob": float(top_logprob)}


def _first_completion_choice(data: dict[str, object]) -> dict[str, Any] | None:
    choices = data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0]
    return None


def _extract_message_content(data: dict[str, object], fallback_text: str = "") -> str:
    first_choice = _first_completion_choice(data)
    if first_choice is None:
        return fallback_text
    message = first_choice.get("message", {})
    if isinstance(message, dict):
        content = message.get("content", "")
        if isinstance(content, str):
            content = content.strip()
            if content:
                return content
    text = first_choice.get("text", "")
    if isinstance(text, str):
        text = text.strip()
        if text:
            return text
    return fallback_text


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


async def _iter_stream_packets(resp: Any) -> AsyncIterator[dict]:
    async for packet in llm_simple_transport.iter_stream_packets(resp):
        yield packet


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
    exc: Any,
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


async def _read_http_error_response_text(response: Optional[Any]) -> str:
    return await llm_simple_transport.read_http_error_response_text(response)


async def _emit_http_status_error_and_mark_failed(
    *,
    exc: Any,
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
    exc: Any,
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
    _record_simple_error(
        request_id,
        error_code="internal_error",
        error_message=f"Nieoczekiwany błąd: {exc}",
        error_details={
            "provider": getattr(runtime, "provider", "unknown"),
            "endpoint": getattr(runtime, "endpoint", None),
            "exception": exc.__class__.__name__,
        },
        error_class=exc.__class__.__name__,
        retryable=False,
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
    state: _SimpleStreamState,
    request_id: UUID,
    stream_start: float,
    runtime_telemetry: dict[str, int],
    extract_visible_contents: Callable[
        [dict[str, Any]], list[str]
    ] = _extract_sse_contents,
) -> list[str]:
    return _update_stream_state_from_packet_impl(
        packet=packet,
        state=state,
        runtime_telemetry=runtime_telemetry,
        extract_runtime_telemetry_fn=_extract_runtime_telemetry,
        extract_sse_tool_calls_fn=_extract_sse_tool_calls,
        extract_sse_contents_fn=extract_visible_contents,
        on_first_chunk_fn=lambda content: _trace_first_chunk(
            request_id, stream_start, content
        ),
    )


def _visible_stream_contents(
    packet: dict[str, Any], guard: CalendarClaimStream | None
) -> list[str]:
    contents = _extract_sse_contents(packet)
    if guard is None:
        return contents
    text = guard.push("".join(contents))
    return [text] if text else []


def _stream_final_text(
    state: _SimpleStreamState,
    guard: CalendarClaimStream | None,
    report_length: bool,
) -> str | None:
    if not state.completed or (guard is None and not report_length):
        return None
    if guard is not None:
        return guard.finish(truncated=state.length_limited)
    return f"\n\n{GENERATION_TRUNCATED}" if state.length_limited else ""


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
    runtime_telemetry: dict[str, int],
    guard_calendar: bool = False,
    report_length: bool = False,
) -> AsyncIterator[str]:
    provider_name = str(getattr(runtime, "provider", "") or "llm_runtime")
    transport = _StreamTransportConfig(
        open_stream_response_fn=llm_simple_transport.open_stream_response,
        iter_stream_packets_fn=_iter_stream_packets,
        completions_url=completions_url,
        payload=payload,
        provider_name=provider_name,
    )
    retry = _StreamRetryConfig(
        http_status_error_type=llm_simple_transport.httpx_module().HTTPStatusError,
        max_attempts=max_attempts,
        is_retryable_status_fn=_is_retryable_runtime_status,
        runtime_provider=runtime.provider,
        retry_backoff=retry_backoff,
        sleep_fn=asyncio.sleep,
    )
    guard = CalendarClaimStream() if guard_calendar else None
    async for event in _stream_single_attempt_impl(
        transport=transport,
        retry=retry,
        state=state,
        attempt=attempt,
        handle_packet_fn=lambda packet: _update_stream_state_from_packet(
            packet=packet,
            state=state,
            request_id=request_id,
            stream_start=stream_start,
            runtime_telemetry=runtime_telemetry,
            extract_visible_contents=lambda packet: _visible_stream_contents(
                packet, guard
            ),
        ),
        emit_http_error_fn=lambda exc: _emit_http_status_error_and_mark_failed(
            exc=exc,
            runtime=runtime,
            request_id=request_id,
            model_name=model_name,
            stream_start=stream_start,
        ),
    ):
        yield event
    final = _stream_final_text(state, guard, report_length)
    if final is not None:
        for event in _update_stream_state_from_packet(
            packet={"choices": [{"delta": {"content": final}}]},
            state=state,
            request_id=request_id,
            stream_start=stream_start,
            runtime_telemetry=runtime_telemetry,
        ):
            yield event
    if state.retry_requested:
        runtime_telemetry.clear()


def _reset_stream_attempt_state(state: _SimpleStreamState) -> None:
    _reset_stream_attempt_state_impl(state)


def _build_done_event(
    runtime_telemetry: dict[str, int], *, length_limited: bool = False
) -> str:
    """Keep the done event and attach provider usage or an observed length limit."""
    details: dict[str, Any] = {}
    if usage := _token_usage_from_telemetry(runtime_telemetry):
        details.update(usage=usage, usage_source="upstream")
    if length_limited:
        details["finish_reason"] = "length"
    return (
        "event: done\ndata: " + json.dumps(details) + "\n\n"
        if details
        else _SSE_EVENT_DONE
    )


def _finalize_successful_stream_attempt(
    *,
    runtime,
    request_id: UUID,
    stream_start: float,
    state: _SimpleStreamState,
    runtime_telemetry: dict[str, int],
) -> None:
    _trace_stream_completion(
        request_id, "".join(state.chunks), state.chunk_count, stream_start
    )
    total_ms = (time.perf_counter() - stream_start) * 1000.0
    usage = _token_usage_from_telemetry(runtime_telemetry)
    collector = get_metrics_collector()
    collector.record_provider_request(
        provider=runtime.provider,
        success=True,
        latency_ms=total_ms,
        tokens=usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
    )
    if runtime.provider == "ollama":
        collector.record_runtime_sample(
            load_duration_ms=_normalize_ns_to_ms(
                runtime_telemetry.get("load_duration")
            ),
            prompt_eval_count=runtime_telemetry.get("prompt_eval_count"),
            eval_count=runtime_telemetry.get("eval_count"),
            prompt_eval_duration_ms=_normalize_ns_to_ms(
                runtime_telemetry.get("prompt_eval_duration")
            ),
            eval_duration_ms=_normalize_ns_to_ms(
                runtime_telemetry.get("eval_duration")
            ),
        )


def _resolve_post_attempt_action(
    *,
    runtime,
    request_id: UUID,
    stream_start: float,
    state: _SimpleStreamState,
    runtime_telemetry: dict[str, int],
) -> str:
    return _resolve_post_attempt_action_impl(
        state=state,
        finalize_success_fn=lambda: _finalize_successful_stream_attempt(
            runtime=runtime,
            request_id=request_id,
            stream_start=stream_start,
            state=state,
            runtime_telemetry=runtime_telemetry,
        ),
    )


def _apply_post_attempt_action(action: str) -> tuple[bool, bool]:
    return _apply_post_attempt_action_impl(action)


async def _handle_stream_http_error(
    *,
    exc: Any,
    runtime,
    request_id: UUID,
    model_name: str,
    stream_start: float,
    attempt: int,
    max_attempts: int,
    retry_backoff: float,
    chunk_count: int,
    runtime_telemetry: dict[str, int],
) -> str:
    status_code = (
        getattr(getattr(exc, "response", None), "status_code", None)
        if exc is not None
        else None
    )
    if chunk_count == 0 and _is_retryable_runtime_http_error(
        provider=runtime.provider,
        status_code=status_code,
        attempt_no=attempt,
        max_retries=max_attempts,
    ):
        runtime_telemetry.clear()
        await asyncio.sleep(retry_backoff * attempt)
        return "retry"

    if isinstance(status_code, int) and 400 <= status_code <= 599:
        return await _emit_http_status_error_and_mark_failed(
            exc=exc,
            runtime=runtime,
            request_id=request_id,
            model_name=model_name,
            stream_start=stream_start,
        )

    return _emit_connection_error_and_mark_failed(
        exc=exc,
        runtime=runtime,
        request_id=request_id,
        model_name=model_name,
        stream_start=stream_start,
    )


def _expected_vast_identity(runtime) -> tuple[Optional[str], Optional[str]]:
    if not str(getattr(runtime, "runtime_id", "")).startswith(_VAST_RUNTIME_PREFIX):
        return None, None
    return runtime.runtime_id, runtime.config_hash


def _simple_stream_max_attempts(runtime) -> int:
    is_vast = str(getattr(runtime, "runtime_id", "") or "").startswith(
        _VAST_RUNTIME_PREFIX
    )
    if runtime.provider == "ollama" and not is_vast:
        return max(1, int(SETTINGS.OLLAMA_RETRY_MAX_ATTEMPTS))
    return 1


async def _stream_simple_chunks(
    *,
    completions_url: str,
    payload: dict,
    runtime,
    request_id: UUID,
    model_name: str,
    guard_calendar: bool = False,
    report_length: bool = False,
) -> AsyncIterator[str]:
    expected_runtime_id, expected_config_hash = _expected_vast_identity(runtime)
    async with runtime_request_guard(
        request_kind="simple_chat_stream",
        provider=runtime.provider,
        model=model_name,
        expected_runtime_id=expected_runtime_id,
        expected_config_hash=expected_config_hash,
        runtime_identity=runtime.runtime_id,
    ):
        state = _SimpleStreamState(chunks=[])
        stream_start = time.perf_counter()
        runtime_telemetry: dict[str, int] = {}

        yield _SSE_EVENT_START

        max_attempts = _simple_stream_max_attempts(runtime)
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
                    guard_calendar=guard_calendar,
                    report_length=report_length,
                    runtime_telemetry=runtime_telemetry,
                ):
                    yield event

                action = _resolve_post_attempt_action(
                    runtime=runtime,
                    request_id=request_id,
                    stream_start=stream_start,
                    state=state,
                    runtime_telemetry=runtime_telemetry,
                )
                should_retry, should_emit_done = _apply_post_attempt_action(action)
                if should_retry:
                    continue
                if should_emit_done:
                    yield _build_done_event(
                        runtime_telemetry,
                        length_limited=report_length and state.length_limited,
                    )
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
                    runtime_telemetry=runtime_telemetry,
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


async def _read_non_stream_data(
    runtime: LLMRuntimeInfo,
    url: str,
    payload: dict[str, Any],
) -> Any:
    async with llm_simple_transport.open_stream_response(
        provider_name=runtime.provider,
        completions_url=url,
        payload=payload,
    ) as response:
        response.raise_for_status()
        aread = getattr(response, "aread", None)
        if callable(aread):
            raw = await aread()
            return json.loads(raw.decode("utf-8", errors="replace")) if raw else {}
        reader = getattr(response, "json", None)
        return reader() if callable(reader) else {}


def _draft_truncated(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    choice = _first_completion_choice(data)
    if choice is not None:
        return choice.get("finish_reason") == "length"
    return data.get("done") is True and data.get("done_reason") == "length"


def _plain_native_response(data: Any) -> bool:
    if not isinstance(data, dict) or data.get("error") is not None:
        return False
    message = data.get("message")
    return isinstance(message, dict) and not message.get("tool_calls")


async def _retry_review_draft(
    review: ReviewDraft, runtime: LLMRuntimeInfo, url: str, payload: dict[str, Any]
) -> str | None:
    system, *history = payload["messages"]
    instruction = REVIEW_RETRY_INSTRUCTION
    if review.requested_feedback or review.pending_pdf:
        instruction += (
            " Dodaj osobne zdanie z jawnie zleconą prośbą lub warunkiem zgody."
        )
    retry_system = {
        **system,
        "content": f"{system['content']}\n\n{instruction}",
    }
    replacement = await _read_non_stream_data(
        runtime, url, {**payload, "messages": [retry_system, *history]}
    )
    if not _plain_native_response(replacement):
        return None
    if _draft_truncated(replacement):
        return GENERATION_TRUNCATED
    draft = completed_native_draft(replacement)
    return review.publish_retry(draft) if draft.strip() else None


async def _retry_truncated_studio_draft(
    reply: QualifiedReply, runtime: LLMRuntimeInfo, url: str, payload: dict[str, Any]
) -> str:
    system, *history = payload["messages"]
    retry_system = {
        **system,
        "content": (
            f"{system['content']}\n\n"
            "Podaj krótką, kompletną odpowiedź od razu. Pomiń wstęp i powtórzenia. "
            "Zachowaj wszystkie wymagane fakty, warunki, korekty i format. "
            "Oddziel fakty potwierdzone od planów i danych nieznanych. "
            "Jeżeli liczysz, sprawdź zgodność wyniku z działaniem."
        ),
    }
    replacement = await _read_non_stream_data(
        runtime, url, {**payload, "messages": [retry_system, *history]}
    )
    if not _plain_native_response(replacement) or _draft_truncated(replacement):
        return GENERATION_TRUNCATED
    content = completed_native_draft(replacement)
    return reply.publish(content) if content.strip() else GENERATION_TRUNCATED


async def _publish_qualified_draft(
    reply: QualifiedReply,
    data: dict[str, Any],
    runtime: LLMRuntimeInfo,
    url: str,
    payload: dict[str, Any],
) -> str | None:
    content = completed_native_draft(data)
    if reply.review_draft is not None:
        if not _plain_native_response(data):
            return None
        if _draft_truncated(data):
            return await _retry_review_draft(reply.review_draft, runtime, url, payload)
    if reply.rss is not None:
        return (
            GENERATION_TRUNCATED
            if _draft_truncated(data)
            else reply.rss.publish(content)
        )
    repair = reply.repair(content)
    if repair is None:
        if _draft_truncated(data):
            if (
                reply.retry_truncated
                and reply.schema is None
                and _plain_native_response(data)
            ):
                return await _retry_truncated_studio_draft(reply, runtime, url, payload)
            return GENERATION_TRUNCATED
        if not content.strip():
            return "Nie udało się uzyskać kompletnej odpowiedzi."
        answer = reply.publish(content)
        return (
            reply.review_draft.publish_initial(answer) if reply.review_draft else answer
        )
    kept, schema = repair
    request = {
        "role": "user",
        "content": (
            "Uzupełnij wyłącznie brakujące, samodzielne i zgodne propozycje. "
            "Zachowaj wszystkie warunki. Zaakceptowane opcje: "
            + json.dumps(kept, ensure_ascii=False)
        ),
    }
    replacement = await _read_non_stream_data(
        runtime,
        url,
        {**payload, "format": schema, "messages": [*payload["messages"], request]},
    )
    return reply.publish(
        content,
        completed_native_draft(replacement),
        truncated=_draft_truncated(data) or _draft_truncated(replacement),
    )


async def _stream_simple_chunks_non_stream(
    *,
    completions_url: str,
    payload: dict,
    runtime,
    request_id: UUID,
    model_name: str,
    qualified_reply: QualifiedReply | None = None,
    report_length: bool = False,
) -> AsyncIterator[str]:
    expected_runtime_id, expected_config_hash = _expected_vast_identity(runtime)
    async with runtime_request_guard(
        request_kind="simple_chat_non_stream",
        provider=runtime.provider,
        model=model_name,
        expected_runtime_id=expected_runtime_id,
        expected_config_hash=expected_config_hash,
        runtime_identity=runtime.runtime_id,
    ):
        stream_start = time.perf_counter()
        chunks: list[str] = []

        yield _SSE_EVENT_START
        if qualified_reply is not None and qualified_reply.local_text is not None:
            content = qualified_reply.local_text
            _trace_first_chunk(request_id, stream_start, content)
            _trace_stream_completion(request_id, content, 1, stream_start)
            yield _SSE_CONTENT_PREFIX + json.dumps({"text": content}) + "\n\n"
            yield _SSE_EVENT_DONE
            return
        try:
            data = await _read_non_stream_data(runtime, completions_url, payload)

            if not isinstance(data, dict):
                _trace_stream_completion(request_id, "", 0, stream_start)
                _record_simple_error(
                    request_id,
                    error_code=_NON_STREAM_INVALID_RESPONSE_CODE,
                    error_message=(
                        f"Nieprawidłowa odpowiedź LLM ({runtime.provider}): "
                        "oczekiwano obiektu JSON."
                    ),
                    error_details={
                        "provider": runtime.provider,
                        "model": model_name,
                        "response_type": type(data).__name__,
                    },
                    error_class=type(data).__name__,
                    retryable=False,
                )
                collector = get_metrics_collector()
                collector.record_provider_request(
                    provider=runtime.provider,
                    success=False,
                    latency_ms=(time.perf_counter() - stream_start) * 1000.0,
                    error_code=_NON_STREAM_INVALID_RESPONSE_CODE,
                )
                yield (
                    "event: error\ndata: "
                    + json.dumps(
                        {
                            "code": _NON_STREAM_INVALID_RESPONSE_CODE,
                            "message": (
                                "Nieprawidłowa odpowiedź z aktywnego runtime LLM."
                            ),
                        }
                    )
                    + "\n\n"
                )
                return

            runtime_telemetry = _extract_runtime_telemetry(data)
            usage = _token_usage_from_telemetry(runtime_telemetry)
            content = (
                await _publish_qualified_draft(
                    qualified_reply, data, runtime, completions_url, payload
                )
                if qualified_reply is not None
                else _extract_message_content(data, fallback_text="")
            )
            if content is None:
                code = "review_draft_unverified"
                message = "Nie udało się zweryfikować treści ponowionej odpowiedzi."
                _record_simple_error(
                    request_id,
                    error_code=code,
                    error_message=message,
                    error_details={"model": model_name},
                    retryable=False,
                )
                yield (
                    "event: error\ndata: "
                    + json.dumps({"code": code, "message": message})
                    + "\n\n"
                )
                return
            logprobs_telemetry = _extract_logprobs_telemetry(data)
            if logprobs_telemetry is not None:
                yield (
                    "event: telemetry\ndata: "
                    + json.dumps(logprobs_telemetry, ensure_ascii=False)
                    + "\n\n"
                )
            if content:
                chunks.append(content)
                _trace_first_chunk(request_id, stream_start, content)
                yield _SSE_CONTENT_PREFIX + json.dumps({"text": content}) + "\n\n"

            _trace_stream_completion(
                request_id, "".join(chunks), len(chunks), stream_start
            )
            collector = get_metrics_collector()
            collector.record_provider_request(
                provider=runtime.provider,
                success=True,
                latency_ms=(time.perf_counter() - stream_start) * 1000.0,
                tokens=usage.get("prompt_tokens", 0)
                + usage.get("completion_tokens", 0),
            )
            yield _build_done_event(
                runtime_telemetry,
                length_limited=report_length
                and (
                    content == GENERATION_TRUNCATED
                    if qualified_reply is not None
                    else _draft_truncated(data)
                ),
            )
        except httpx.HTTPStatusError as exc:
            result = await _emit_http_status_error_and_mark_failed(
                exc=exc,
                runtime=runtime,
                request_id=request_id,
                model_name=model_name,
                stream_start=stream_start,
            )
            yield result
        except httpx.HTTPError as exc:
            yield _emit_connection_error_and_mark_failed(
                exc=exc,
                runtime=runtime,
                request_id=request_id,
                model_name=model_name,
                stream_start=stream_start,
            )
        except Exception as exc:
            yield _emit_internal_error_and_mark_failed(
                exc=exc,
                runtime=runtime,
                request_id=request_id,
                stream_start=stream_start,
            )


def _validate_simple_chat_runtime(runtime) -> str:
    runtime_provider = str(getattr(runtime, "provider", "") or "").lower()
    runtime_service_type = str(getattr(runtime, "service_type", "") or "").lower()
    if runtime_provider == "onnx" or runtime_service_type == "onnx":
        if not SETTINGS.ONNX_LLM_ENABLED:
            raise HTTPException(
                status_code=503,
                detail="ONNX_LLM_ENABLED=false: runtime ONNX jest wyłączony.",
            )
        if not runtime.endpoint:
            raise HTTPException(
                status_code=503,
                detail="Brak endpointu workera ONNX. Skonfiguruj ONNX_LLM_ENDPOINT.",
            )
    return runtime_provider


async def stream_simple_chat(request: SimpleChatRequest, *, system_context: str = ""):
    assert_runtime_request_allowed(request_kind="simple_chat")
    from venom_core.services import omni_native_text, openrouter_runtime

    native_response = await omni_native_text.route_response(
        request, system_context=system_context
    )
    if native_response is not None:
        return native_response
    if openrouter_runtime.selection() is not None:
        if request.studio_normal:
            raise HTTPException(400, "studio_normal_requires_local_ollama")
        from venom_core.services.openrouter_chat import response

        return await response(request)
    return await _stream_non_openrouter_chat(request, system_context=system_context)


def _material_turn_text_length(turn: dict[str, Any]) -> int:
    content = turn["content"]
    return (
        len(content)
        if isinstance(content, str)
        else sum(len(part.get("text", "")) for part in content)
    )


async def _include_simple_request_context(
    request: SimpleChatRequest,
    runtime,
    model_name: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from venom_core.services.chat_material_payload import (
        direct_material_messages,
        has_materials,
    )

    if has_materials(request):
        # Explicit references must survive runtime trimming and quote accounting.
        turns = await direct_material_messages(request, runtime, model_name)
        char_limit = _get_simple_context_char_limit(runtime)
        if char_limit:
            text_length = sum(_material_turn_text_length(turn) for turn in turns)
            if text_length + len(system_prompt) + 32 > char_limit:
                raise HTTPException(413, {"reason_code": "material_context_limit"})
        return [*messages[:-1], *turns]
    if not request.history:
        return messages
    history = _plain_request_history(
        request, runtime, system_prompt, messages[-1]["content"]
    )
    return [*messages[:-1], *history, messages[-1]]


def _plain_request_history(
    request: SimpleChatRequest, runtime: Any, system_prompt: str, current_content: str
) -> list[dict[str, Any]]:
    """Reject oversized history before provider I/O without silently dropping prior turns."""
    history_length = sum(len(item.content) for item in request.history)
    if history_length > MAX_CHAT_HISTORY_CHARS:
        raise HTTPException(status_code=400, detail="vast_chat_history_limit")
    char_limit = _get_simple_context_char_limit(runtime)
    if (
        char_limit
        and history_length + len(system_prompt) + len(current_content) + 32 > char_limit
    ):
        raise HTTPException(413, {"reason_code": "material_context_limit"})
    return [item.model_dump(exclude={"material_ids"}) for item in request.history]


def _prepare_local_direct_prompt(
    request: SimpleChatRequest,
    runtime: LLMRuntimeInfo,
    model_name: str,
    system_context: str,
) -> tuple[SimpleChatRequest, str]:
    direct_model = local_direct_model(request, runtime, model_name)
    if direct_model == "omni":
        request = prepare_omni_history(request)
    return request, simple_system_prompt(
        request,
        system_context,
        plain_omni=direct_model == "omni",
        plain_gemma=direct_model == "gemma",
    )


def _plain_text_request(request: SimpleChatRequest) -> bool:
    from venom_core.services.chat_material_payload import has_materials

    return (
        not has_materials(request)
        and request.tools is None
        and request.tool_choice is None
        and request.format is None
        and request.response_format is None
        and not request.logprobs
        and request.top_logprobs is None
    )


def _qualified_request(request: SimpleChatRequest, runtime: LLMRuntimeInfo) -> bool:
    return (
        SETTINGS.ACADEMY_QUALIFIED_CHAT_ENABLED
        and is_host_ollama(runtime)
        and _plain_text_request(request)
    )


def _qualified_studio_request(
    request: SimpleChatRequest, profile: OllamaTextProfile | None
) -> bool:
    return request.studio_normal and not request.use_notes and profile is not None


_STUDIO_ORDINARY_DRAFT_POLICY = (
    "Odpowiadaj krótko i od razu w żądanej formie, bez wstępu, podsumowania "
    "ani kilku wersji, chyba że użytkownik ich chce. Bez wskazania formy zwykle "
    "wystarczą najwyżej trzy krótkie zdania. "
    "Przy korekcie zachowaj wszystkie pozostałe ustalenia, liczby i warunki. "
    "Obowiązek dotyczy wyłącznie wskazanej osoby lub rzeczy. Gdy ją usunięto, "
    "usuń także przypisany do niej obowiązek. "
    "Plan, warunkowa zgoda, brak dowodu i wykonanie to odrębne stany. "
    "Brak dowodu nie przesądza, że działanie się nie odbyło. "
    "Zachowaj sens ograniczeń, np. „najwcześniej”, „tylko jeśli”, „co najmniej” "
    "i przybliżenia. W opisie planu użyj słowa „plan” lub „zamierza”. "
    "Po zmianie warunku porównaj możliwości od nowa według celu użytkownika. "
    "Najpierw uwzględnij warunek wykonalności, a później wygodę. "
    "Zachowaj nazwy i rozróżnienia z podanego opisu. "
    "W razie braku rozstrzygającego faktu zaznacz warunek lub dopytaj. "
    "Pełna odpowiedź ma zachować wymagane szczegóły także wtedy, gdy jest krótka."
)


def _prepare_qualified_reply(
    request: SimpleChatRequest,
    runtime: LLMRuntimeInfo,
    model_name: str,
) -> QualifiedReply | None:
    if not _qualified_request(request, runtime):
        return None
    profile = qualified_profile(model_name)
    if _qualified_studio_request(request, profile):
        if request._studio_public_scope_reply:
            return QualifiedReply(local_text=request._studio_public_scope_reply)
        if request._studio_user_fact_reply:
            return QualifiedReply(local_text=request._studio_user_fact_reply)
        if request._studio_rss_headlines:
            count = requested_count(request.content)
            return QualifiedReply(
                rss=RSSSummary(
                    request._studio_rss_headlines, count or CountRequirement("exact", 1)
                )
            )
        if (
            SETTINGS.ACADEMY_GEMMA_REVIEW_RETRY_ENABLED
            and model_name.casefold() == QUALIFIED_MODEL
        ):
            if heading := publication_heading(request.content, request.history):
                return QualifiedReply(local_text=heading)
            if check := publication_check(request.content, request.history):
                return QualifiedReply(
                    claim_check=check,
                    hint=_STUDIO_ORDINARY_DRAFT_POLICY,
                    retry_truncated=SETTINGS.ACADEMY_GEMMA_STUDIO_TRUNCATION_RETRY_ENABLED,
                )
        if reply := prepare_studio_reply(
            request.content, request.history, token_budget=request.max_tokens
        ):
            return reply
        if (
            SETTINGS.ACADEMY_GEMMA_REVIEW_RETRY_ENABLED
            and model_name.casefold() == QUALIFIED_MODEL
        ):
            content, history = request.content, request.history
            answer = (
                studio_followup(content, history)
                or topic_only_sms(content, history)
                or stated_packaging_reply(content, history)
                or studio_revision(content, history)
                or studio_visibility(content, history)
                or studio_dialog(content, history)
                or studio_comparison(content, history)
                or studio_quantity(content, history)
            )
            if answer is not None:
                return QualifiedReply(local_text=answer)
        if is_current_news_request(request.content):
            return None
    if profile is None or not profile.direct_drafts:
        return None
    original = prepare_reply(request.content, request.history)
    if model_name.casefold() != QUALIFIED_MODEL or not _qualified_studio_request(
        request, profile
    ):
        return original
    if SETTINGS.ACADEMY_GEMMA_REVIEW_RETRY_ENABLED:
        if not original.requires_complete_draft:
            review = parse_review_draft(
                request.content,
                check_initial=not any(turn.role == "user" for turn in request.history),
            )
            if review is not None:
                return replace(original, review_draft=review)
            if claim_check := prepare_studio_claim_check(
                request.content, request.history
            ):
                return replace(original, claim_check=claim_check)
        hint = studio_concise_hint(request.content, original.count is not None)
        if hint:
            original = replace(
                original, hint=" ".join(filter(None, (original.hint, hint)))
            )
    if (
        SETTINGS.ACADEMY_GEMMA_STUDIO_TRUNCATION_RETRY_ENABLED
        and not original.requires_complete_draft
    ):
        return replace(
            original,
            hint=" ".join(filter(None, (original.hint, _STUDIO_ORDINARY_DRAFT_POLICY))),
            retry_truncated=True,
        )
    return original


async def _resolve_non_openrouter_runtime(request: SimpleChatRequest):
    await asyncio.sleep(0)
    from venom_core.services.vast_chat_runtime import preflight

    await preflight()
    runtime = get_active_llm_runtime()
    from venom_core.services.vast_chat_runtime import assert_identity, is_remote

    if request.studio_normal and (runtime.provider != "ollama" or is_remote(runtime)):
        raise HTTPException(400, "studio_normal_requires_local_ollama")
    assert_identity(runtime, request.expected_runtime_id, request.expected_config_hash)
    if is_remote(runtime) and request.model not in {None, runtime.model_name}:
        raise HTTPException(status_code=409, detail="vast_chat_model_selection_changed")
    runtime_provider = _validate_simple_chat_runtime(runtime)
    model_name = _resolve_model_name_for_simple_request(
        request_model=request.model,
        runtime_model=runtime.model_name,
        active_adapter_id=None
        if is_remote(runtime)
        else await _get_active_adapter_id(),
    )
    if not model_name:
        raise HTTPException(status_code=400, detail="Brak nazwy modelu LLM.")
    return runtime, runtime_provider, model_name


def _apply_qualified_reply_prompt(
    system_context: str,
    system_prompt: str,
    qualified_reply: QualifiedReply | None,
    complete_reply: QualifiedReply | None,
) -> str:
    if qualified_reply is not None and (
        complete_reply is not None or qualified_reply.hint
    ):
        configured = (SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT or "").strip()
        custom = configured if configured != DEFAULT_SIMPLE_MODE_SYSTEM_PROMPT else ""
        system_prompt = qualified_reply.prompt(
            "\n\n".join(filter(None, (custom, system_context)))
        )
    return system_prompt


def _apply_studio_prompt_hints(
    request: SimpleChatRequest,
    runtime,
    model_name: str,
    system_context: str,
    system_prompt: str,
    complete_reply: QualifiedReply | None,
) -> str:
    qualified_studio = _qualified_studio_request(
        request, qualified_profile(model_name)
    ) and _qualified_request(request, runtime)
    if qualified_studio and complete_reply is None:
        hint = explanation_hint(
            request.content, request.history, token_budget=request.max_tokens
        )
        system_prompt = "\n\n".join(
            filter(
                None,
                (
                    system_prompt,
                    hint,
                    fit_hint(request.content, request.history),
                    source_revision_hint(request.content),
                    writing_hint(request.content),
                    ordinary_reply_hint(request.content)
                    if (request.max_tokens or 256) <= 96
                    and PUBLIC_SOURCE_BLOCK not in system_context
                    else "",
                    english_translation_hint(request.content),
                ),
            )
        )
    return system_prompt


def _qualified_stream_prompt(
    request: SimpleChatRequest, runtime, model_name: str, system_context: str
):
    request, system_prompt = _prepare_local_direct_prompt(
        request, runtime, model_name, system_context
    )
    qualified_reply = _prepare_qualified_reply(request, runtime, model_name)
    complete_reply = (
        qualified_reply
        if qualified_reply is not None
        and (qualified_reply.requires_complete_draft or request.stream is False)
        else None
    )
    system_prompt = _apply_qualified_reply_prompt(
        system_context, system_prompt, qualified_reply, complete_reply
    )
    system_prompt = _apply_studio_prompt_hints(
        request, runtime, model_name, system_context, system_prompt, complete_reply
    )
    if (
        qualified_reply is None
        and not request.studio_normal
        and not system_context
        and _plain_text_request(request)
    ):
        hint = short_message_hint(request.content, request.history) or fit_bounds_hint(
            request.content, request.history
        )
        if hint and is_host_ollama(runtime):
            system_prompt = "\n\n".join(filter(None, (system_prompt, hint)))
    if (
        complete_reply is None
        and qualified_reply is not None
        and qualified_reply.retry_truncated
        and request.stream is None
    ):
        complete_reply = qualified_reply
    return request, system_prompt, qualified_reply, complete_reply


async def _non_openrouter_messages(
    request: SimpleChatRequest,
    runtime,
    model_name: str,
    system_prompt: str,
    complete_reply: QualifiedReply | None,
    request_id: UUID,
) -> list[dict[str, Any]]:
    rewrite = complete_reply.rewrite if complete_reply else None
    if complete_reply is not None and complete_reply.rss is not None:
        return complete_reply.rss.messages(request.content)
    if rewrite is not None:
        return rewrite.messages(plain_text=plain_text_rewrite(model_name))
    user_content = _trim_user_content_for_runtime(
        request.content, system_prompt, runtime, request_id
    )
    messages = _build_messages(system_prompt, user_content)
    return await _include_simple_request_context(
        request, runtime, model_name, system_prompt, messages
    )


def _stream_non_openrouter_response(
    request: SimpleChatRequest,
    runtime,
    runtime_provider,
    model_name: str,
    messages: list[dict[str, Any]],
    request_id: UUID,
    complete_reply: QualifiedReply | None,
    qualified_reply: QualifiedReply | None,
):
    headers = _build_streaming_headers(str(request_id), request.session_id or "")
    completions_url = _build_chat_completions_url(runtime)
    if complete_reply is not None:
        completions_url = native_chat_url(runtime)
    force_non_stream = request.stream is False or complete_reply is not None
    if is_multi_runtime(runtime_provider) or force_non_stream:
        if not completions_url:
            raise HTTPException(status_code=503, detail="Brak endpointu LLM.")
        payload = (
            native_draft_payload(request, messages, complete_reply, model_name)
            if complete_reply is not None
            else _build_payload(request, runtime, model_name, messages, stream=False)
        )
        return StreamingResponse(
            _stream_simple_chunks_non_stream(
                completions_url=completions_url,
                payload=payload,
                runtime=runtime,
                request_id=request_id,
                model_name=model_name,
                qualified_reply=complete_reply,
                report_length=request.studio_normal,
            ),
            media_type=_SSE_MEDIA_TYPE,
            headers=headers,
        )
    if not completions_url:
        raise HTTPException(status_code=503, detail="Brak endpointu LLM.")
    guard_options = {"guard_calendar": True} if qualified_reply is not None else {}
    if request.studio_normal:
        guard_options["report_length"] = True
    return StreamingResponse(
        _stream_simple_chunks(
            completions_url=completions_url,
            payload=_build_payload(request, runtime, model_name, messages),
            runtime=runtime,
            request_id=request_id,
            model_name=model_name,
            **guard_options,
        ),
        media_type=_SSE_MEDIA_TYPE,
        headers=headers,
    )


def _local_direct_stream(
    request: SimpleChatRequest,
    runtime: LLMRuntimeInfo,
    model_name: str,
    request_id: UUID,
    reply: Callable[[], dict[str, Any]],
) -> StreamingResponse:
    _plain_request_history(request, runtime, "", request.content)

    async def chunks() -> AsyncIterator[str]:
        async with runtime_request_guard(
            request_kind="simple_chat_stream",
            provider=runtime.provider,
            model=model_name,
            runtime_identity=runtime.runtime_id,
        ):
            result = reply()
        # Synchronous local work has finished before any stream yield can be cancelled.
        text = result.pop("text")
        yield _SSE_EVENT_START
        yield (
            _SSE_CONTENT_PREFIX
            + json.dumps({"text": text}, ensure_ascii=False)
            + "\n\n"
        )
        yield "event: done\ndata: " + json.dumps(result) + "\n\n"

    return StreamingResponse(
        chunks(),
        media_type=_SSE_MEDIA_TYPE,
        headers=_build_streaming_headers(str(request_id), request.session_id or ""),
    )


def _allows_local_direct_reply(request: SimpleChatRequest, system_context: str) -> bool:
    configured = (SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT or "").strip()
    return (
        not request.studio_normal
        and not system_context
        and request.max_tokens is None
        and configured in ("", DEFAULT_SIMPLE_MODE_SYSTEM_PROMPT)
        and _plain_text_request(request)
    )


def _direct_calculator_response(
    request: SimpleChatRequest,
    runtime: LLMRuntimeInfo,
    model_name: str,
    request_id: UUID,
    system_context: str,
) -> StreamingResponse | None:
    if (
        SETTINGS.ACADEMY_GEMMA_REVIEW_RETRY_ENABLED
        and model_name.casefold() == QUALIFIED_MODEL
        and request.studio_normal
        and not request.use_notes
        and not request._studio_public_scope_reply
        and PUBLIC_SOURCE_BLOCK not in system_context
        and _qualified_request(request, runtime)
    ):
        studio_plan = plan_studio_calculation(request.content, request.history)
        if studio_plan is not None:
            return _local_direct_stream(
                request, runtime, model_name, request_id, studio_plan.publish
            )
    if not _allows_local_direct_reply(request, system_context):
        return None
    history = [turn.model_dump(include={"role", "content"}) for turn in request.history]
    plan = plan_calculator(request.content, history)
    if plan is None or not is_host_ollama(runtime):
        return None
    return _local_direct_stream(
        request, runtime, model_name, request_id, lambda: execute_calculator(plan)
    )


def _direct_policy_response(
    request: SimpleChatRequest,
    runtime: LLMRuntimeInfo,
    model_name: str,
    request_id: UUID,
    system_context: str,
) -> StreamingResponse | None:
    if not _allows_local_direct_reply(request, system_context):
        return None
    text = role_consent_reply(request.content) or fit_bounds_reply(
        request.content, request.history
    )
    if (
        text is None
        or not is_host_ollama(runtime)
        or _prepare_qualified_reply(request, runtime, model_name) is not None
    ):
        return None
    return _local_direct_stream(
        request,
        runtime,
        model_name,
        request_id,
        lambda: {"text": text, "response_source": "direct_policy"},
    )


async def _stream_non_openrouter_chat(
    request: SimpleChatRequest, *, system_context: str = ""
):
    runtime, runtime_provider, model_name = await _resolve_non_openrouter_runtime(
        request
    )
    request_id: UUID = uuid4()
    calculator = _direct_calculator_response(
        request, runtime, model_name, request_id, system_context
    )
    if calculator is not None:
        return calculator
    policy = _direct_policy_response(
        request, runtime, model_name, request_id, system_context
    )
    if policy is not None:
        return policy
    _trace_simple_request(request_id, request, runtime, model_name)
    request, system_prompt, qualified_reply, complete_reply = _qualified_stream_prompt(
        request, runtime, model_name, system_context
    )
    messages = await _non_openrouter_messages(
        request, runtime, model_name, system_prompt, complete_reply, request_id
    )
    _trace_context_preview(request_id, messages)
    return _stream_non_openrouter_response(
        request,
        runtime,
        runtime_provider,
        model_name,
        messages,
        request_id,
        complete_reply,
        qualified_reply,
    )
