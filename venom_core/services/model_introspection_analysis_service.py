"""Optional live model analysis for Inspector model-introspection flows."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator
from uuid import UUID

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services.llm_simple_service import stream_simple_chat
from venom_core.services.model_introspection_service import (
    build_model_introspection_snapshot,
)
from venom_core.services.runtime_dependencies import get_request_tracer
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def _iter_sse_events(chunk_text: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for block in chunk_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip() or "message"
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        events.append((event_name, "\n".join(data_lines)))
    return events


def _serialize_sse_event(event_name: str, data: Any) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_request_id(raw_request_id: Any) -> UUID | None:
    if raw_request_id is None:
        return None
    try:
        return UUID(str(raw_request_id).strip())
    except Exception:
        return None


def _get_response_header(response: Any, header_name: str) -> Any:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    return getter(header_name)


def _parse_trace_step_details(step: Any) -> dict[str, Any]:
    details = getattr(step, "details", None)
    payload: dict[str, Any] = {
        "component": getattr(step, "component", None),
        "action": getattr(step, "action", None),
        "status": getattr(step, "status", None),
        "details": details,
    }
    action = str(getattr(step, "action", "") or "")
    if action == "response" and isinstance(details, str):
        try:
            parsed = json.loads(details)
        except Exception:
            parsed = {}
        payload.update(
            {
                "chunks": parsed.get("chunks"),
                "total_ms": parsed.get("total_ms"),
                "chars": parsed.get("chars"),
                "truncated": parsed.get("truncated"),
            }
        )
    elif action == "first_chunk" and isinstance(details, str):
        elapsed_ms = None
        for fragment in details.split():
            if fragment.startswith("elapsed_ms="):
                try:
                    elapsed_ms = float(fragment.split("=", 1)[1])
                except Exception:
                    elapsed_ms = None
        payload["elapsed_ms"] = elapsed_ms
    elif action == "context_preview" and isinstance(details, str):
        try:
            parsed = json.loads(details)
        except Exception:
            parsed = {}
        payload["prompt_context_truncated"] = parsed.get("prompt_context_truncated")
        payload["hidden_prompts_count"] = parsed.get("hidden_prompts_count")
    elif action == "prompt_trim" and isinstance(details, str):
        payload["prompt_trimmed"] = True
    return payload


def _summarize_request_trace(request_id: UUID | None) -> dict[str, Any] | None:
    if request_id is None:
        return None
    request_tracer = get_request_tracer()
    if request_tracer is None:
        return None
    trace = request_tracer.get_trace(request_id)
    if trace is None:
        return None

    steps = [_parse_trace_step_details(step) for step in trace.steps]
    response_step = next(
        (step for step in steps if step.get("action") == "response"), {}
    )
    first_chunk_step = next(
        (step for step in steps if step.get("action") == "first_chunk"),
        {},
    )
    context_preview_step = next(
        (step for step in steps if step.get("action") == "context_preview"),
        {},
    )
    prompt_trimmed = any(step.get("action") == "prompt_trim" for step in steps)
    response_chars = response_step.get("chars")
    total_ms = response_step.get("total_ms")
    response_chunks = response_step.get("chunks")
    chars_per_second = None
    if (
        isinstance(response_chars, int)
        and isinstance(total_ms, (int, float))
        and total_ms > 0
    ):
        chars_per_second = round((response_chars / total_ms) * 1000.0, 2)

    return {
        "request_id": str(trace.request_id),
        "status": str(getattr(trace.status, "value", trace.status)),
        "step_count": len(steps),
        "trace_step_count": len(steps),
        "steps": steps,
        "first_chunk_ms": first_chunk_step.get("elapsed_ms"),
        "response_chunks": response_chunks,
        "response_chars": response_chars,
        "total_ms": total_ms,
        "chars_per_second": chars_per_second,
        "response_truncated": response_step.get("truncated"),
        "prompt_trimmed": prompt_trimmed,
        "context_preview_truncated": context_preview_step.get(
            "prompt_context_truncated"
        ),
        "adapter_applied": trace.adapter_applied,
        "adapter_id": trace.adapter_id,
    }


def _build_skipped_analysis_result(
    prompt: str, runtime: dict[str, Any]
) -> dict[str, Any]:
    return {
        "analysis_enabled": False,
        "status": "skipped",
        "skipped_reason": "live_analysis_disabled",
        "analysis": {
            "prompt": prompt,
            "response": "",
            "chunk_count": 0,
            "events": [],
            "timeline_step_count": 1,
            "timeline": [
                {
                    "id": "analysis_disabled",
                    "label": "Live analysis disabled",
                    "status": "skipped",
                    "detail": "Snapshot-only mode",
                    "at_ms": 0.0,
                }
            ],
            "elapsed_ms": 0.0,
            "provider": runtime["provider"],
            "model": runtime["model"],
            "runtime_label": runtime["label"],
        },
    }


def _build_running_analysis_result(
    *,
    prompt: str,
    runtime: dict[str, Any],
    request_ready_at_ms: float,
) -> dict[str, Any]:
    return {
        "analysis_enabled": True,
        "status": "running",
        "snapshot_after": None,
        "analysis": {
            "prompt": prompt,
            "response": "",
            "chunk_count": 0,
            "events": [],
            "timeline_step_count": 3,
            "timeline": [
                {
                    "id": "snapshot_before",
                    "label": "Snapshot captured",
                    "status": "done",
                    "detail": runtime["label"],
                    "at_ms": 0.0,
                },
                {
                    "id": "request_ready",
                    "label": "Prompt prepared",
                    "status": "done",
                    "detail": prompt,
                    "at_ms": request_ready_at_ms,
                },
                {
                    "id": "stream_opened",
                    "label": "Stream opened",
                    "status": "running",
                    "detail": "Awaiting streamed content",
                    "at_ms": request_ready_at_ms,
                },
            ],
            "elapsed_ms": 0.0,
            "provider": runtime["provider"],
            "model": runtime["model"],
            "runtime_label": runtime["label"],
            "request_ready_ms": request_ready_at_ms,
            "response_received_ms": None,
            "snapshot_after_ms": None,
        },
    }


async def _collect_streaming_response(response: Any) -> dict[str, Any]:
    content_parts: list[str] = []
    events: list[str] = []
    chunk_count = 0
    first_content_at_ms: float | None = None
    stream_started_at = time.perf_counter()

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        return {
            "response_text": "",
            "chunk_count": 0,
            "events": [],
            "raw_chunks": [],
            "first_content_at_ms": None,
        }

    raw_chunks: list[str] = []
    async for chunk in body_iterator:
        chunk_at_ms = (time.perf_counter() - stream_started_at) * 1000.0
        chunk_text = (
            chunk.decode("utf-8", errors="replace")
            if isinstance(chunk, bytes)
            else str(chunk)
        )
        raw_chunks.append(chunk_text)
        for event_name, payload in _iter_sse_events(chunk_text):
            events.append(event_name)
            if event_name == "content" and payload:
                try:
                    parsed = json.loads(payload)
                except Exception:
                    continue
                text = str(parsed.get("text") or "")
                if text:
                    content_parts.append(text)
                    chunk_count += 1
                    if first_content_at_ms is None:
                        first_content_at_ms = chunk_at_ms
            elif event_name == "error":
                raise RuntimeError(payload or "analysis stream failed")

    return {
        "response_text": "".join(content_parts),
        "chunk_count": chunk_count,
        "events": events,
        "raw_chunks": raw_chunks,
        "first_content_at_ms": first_content_at_ms,
    }


def _build_analysis_timeline(
    *,
    prompt: str,
    runtime: dict[str, Any],
    stream_payload: dict[str, Any],
    elapsed_ms: float,
    refreshed_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = [
        {
            "id": "snapshot_before",
            "label": "Snapshot captured",
            "status": "done",
            "detail": runtime["label"],
            "at_ms": 0.0,
            "progress": 0,
        },
        {
            "id": "request_ready",
            "label": "Prompt prepared",
            "status": "done",
            "detail": prompt,
            "at_ms": 0.0,
            "progress": 10,
        },
        {
            "id": "stream_opened",
            "label": "Stream opened",
            "status": "done",
            "detail": f"{len(stream_payload.get('events', []))} event(s) observed",
            "at_ms": float(stream_payload.get("first_content_at_ms") or 0.0),
            "progress": 20,
        },
    ]

    if stream_payload.get("first_content_at_ms") is not None:
        timeline.append(
            {
                "id": "first_chunk",
                "label": "First content chunk",
                "status": "done",
                "detail": f"{stream_payload.get('chunk_count', 0)} chunk(s) total",
                "at_ms": float(stream_payload.get("first_content_at_ms") or 0.0),
                "progress": 40,
            }
        )

    timeline.append(
        {
            "id": "response_finalized",
            "label": "Response assembled",
            "status": "done",
            "detail": f"{len(stream_payload.get('response_text', ''))} chars",
            "at_ms": elapsed_ms,
            "progress": 90,
        }
    )

    if refreshed_snapshot is not None:
        timeline.append(
            {
                "id": "snapshot_after",
                "label": "Snapshot refreshed",
                "status": "done",
                "detail": f"{len(refreshed_snapshot.get('available_packages', []))} packages available",
                "at_ms": elapsed_ms,
                "progress": 100,
            }
        )

    return timeline


async def stream_model_introspection_analysis(
    *,
    prompt: str,
    live_analysis_enabled: bool = False,
    max_tokens: int | None = 128,
    temperature: float | None = 0.2,
    model_manager: Any = None,
    settings: Any = None,
) -> AsyncIterator[str]:
    """Stream introspection analysis as SSE, including live model chunks."""

    flow_started_at = time.perf_counter()
    snapshot = await build_model_introspection_snapshot(
        model_manager=model_manager, settings=settings
    )
    runtime = snapshot["runtime"]
    if not live_analysis_enabled:
        skipped_result = _build_skipped_analysis_result(prompt, runtime)
        yield _serialize_sse_event("analysis_start", skipped_result)
        yield _serialize_sse_event("analysis_done", skipped_result)
        return

    if not prompt.strip():
        raise ValueError("prompt cannot be empty")

    request = SimpleChatRequest(
        content=prompt,
        model=runtime["model"],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    request_ready_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
    running_result = _build_running_analysis_result(
        prompt=prompt,
        runtime=runtime,
        request_ready_at_ms=request_ready_at_ms,
    )
    yield _serialize_sse_event("analysis_start", running_result)

    response = await stream_simple_chat(request)
    request_id = _parse_request_id(_get_response_header(response, "X-Request-Id"))
    response_received_at_ms = (time.perf_counter() - flow_started_at) * 1000.0

    content_parts: list[str] = []
    events: list[str] = []
    chunk_count = 0
    first_content_at_ms: float | None = None

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        raise RuntimeError("analysis stream response does not expose a body iterator")

    async for chunk in body_iterator:
        chunk_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
        chunk_text = (
            chunk.decode("utf-8", errors="replace")
            if isinstance(chunk, bytes)
            else str(chunk)
        )
        for event_name, payload in _iter_sse_events(chunk_text):
            events.append(event_name)
            if event_name == "content" and payload:
                try:
                    parsed = json.loads(payload)
                except Exception:
                    parsed = {}
                text = str(parsed.get("text") or "")
                if text:
                    content_parts.append(text)
                    chunk_count += 1
                    if first_content_at_ms is None:
                        first_content_at_ms = chunk_at_ms
            elif event_name == "error":
                raise RuntimeError(payload or "analysis stream failed")
        yield chunk_text

    elapsed_ms = (time.perf_counter() - flow_started_at) * 1000.0
    refreshed_snapshot = await build_model_introspection_snapshot(
        model_manager=model_manager, settings=settings
    )
    snapshot_after_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
    process_trace = _summarize_request_trace(request_id)
    stream_payload = {
        "response_text": "".join(content_parts),
        "chunk_count": chunk_count,
        "events": events,
        "first_content_at_ms": first_content_at_ms,
    }
    analysis_timeline = _build_analysis_timeline(
        prompt=prompt,
        runtime=runtime,
        stream_payload=stream_payload,
        elapsed_ms=elapsed_ms,
        refreshed_snapshot=refreshed_snapshot,
    )
    final_result = {
        "analysis_enabled": True,
        "status": "completed",
        "snapshot": snapshot,
        "snapshot_after": refreshed_snapshot,
        "analysis": {
            "prompt": prompt,
            "response": stream_payload["response_text"],
            "chunk_count": chunk_count,
            "events": events,
            "timeline_step_count": len(analysis_timeline),
            "timeline": analysis_timeline,
            "elapsed_ms": elapsed_ms,
            "provider": runtime["provider"],
            "model": runtime["model"],
            "runtime_label": runtime["label"],
            "request_ready_ms": request_ready_at_ms,
            "response_received_ms": response_received_at_ms,
            "snapshot_after_ms": snapshot_after_at_ms,
            "process": process_trace,
        },
    }
    yield _serialize_sse_event("analysis_done", final_result)


async def analyze_model_with_optional_live_run(
    *,
    prompt: str,
    live_analysis_enabled: bool = False,
    max_tokens: int | None = 128,
    temperature: float | None = 0.2,
    model_manager: Any = None,
    settings: Any = None,
) -> dict[str, Any]:
    """Build snapshot and optionally execute the active model for a prompt."""

    flow_started_at = time.perf_counter()
    snapshot = await build_model_introspection_snapshot(
        model_manager=model_manager, settings=settings
    )
    runtime = snapshot["runtime"]
    if not live_analysis_enabled:
        result = _build_skipped_analysis_result(prompt, runtime)
        result["snapshot"] = snapshot
        return result

    if not prompt.strip():
        raise ValueError("prompt cannot be empty")

    request = SimpleChatRequest(
        content=prompt,
        model=runtime["model"],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    request_ready_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
    result: dict[str, Any] = {
        "analysis_enabled": True,
        "status": "running",
        "snapshot": snapshot,
        "analysis": None,
    }
    response = await stream_simple_chat(request)
    request_id = _parse_request_id(_get_response_header(response, "X-Request-Id"))
    response_received_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
    stream_payload = await _collect_streaming_response(response)
    elapsed_ms = (time.perf_counter() - flow_started_at) * 1000.0
    refreshed_snapshot = await build_model_introspection_snapshot(
        model_manager=model_manager, settings=settings
    )
    snapshot_after_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
    process_trace = _summarize_request_trace(request_id)
    analysis_timeline = _build_analysis_timeline(
        prompt=prompt,
        runtime=runtime,
        stream_payload=stream_payload,
        elapsed_ms=elapsed_ms,
        refreshed_snapshot=refreshed_snapshot,
    )

    result.update(
        {
            "status": "completed",
            "snapshot_after": refreshed_snapshot,
            "analysis": {
                "prompt": prompt,
                "response": stream_payload["response_text"],
                "chunk_count": stream_payload["chunk_count"],
                "events": stream_payload["events"],
                "timeline_step_count": len(analysis_timeline),
                "timeline": analysis_timeline,
                "elapsed_ms": elapsed_ms,
                "provider": runtime["provider"],
                "model": runtime["model"],
                "runtime_label": runtime["label"],
                "request_ready_ms": request_ready_at_ms,
                "response_received_ms": response_received_at_ms,
                "snapshot_after_ms": snapshot_after_at_ms,
                "process": process_trace,
            },
        }
    )
    return result
