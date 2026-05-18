"""Optional live model analysis for Inspector model-introspection flows."""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator
from uuid import UUID, uuid4

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services.llm_simple_service import stream_simple_chat
from venom_core.services.model_introspection_attention_service import (
    build_attention_payload,
)
from venom_core.services.model_introspection_logit_lens_service import (
    build_logit_lens_payload,
)
from venom_core.services.model_introspection_operator_trends_service import (
    record_operator_run,
)
from venom_core.services.model_introspection_rag_focus_service import (
    build_rag_focus_payload,
)
from venom_core.services.model_introspection_saliency_service import (
    build_saliency_payload,
)
from venom_core.services.model_introspection_service import (
    build_model_introspection_snapshot,
)
from venom_core.services.runtime_dependencies import get_request_tracer
from venom_core.services.runtime_switch_telemetry import emit_runtime_model_event
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
_ANALYSIS_STREAM_FAILED = "analysis stream failed"
_TIMELINE_LABEL_SNAPSHOT_CAPTURED = "Snapshot captured"
_TIMELINE_LABEL_PROMPT_PREPARED = "Prompt prepared"
_TIMELINE_LABEL_STREAM_OPENED = "Stream opened"
_TIMELINE_LABEL_LOGIT_LENS = "Logit lens probe"
_TIMELINE_LABEL_ATTENTION = "Attention probe"
_TIMELINE_LABEL_SALIENCY = "Saliency probe"
_STREAM_DELAYED_THRESHOLD_MS = 1000.0
_STREAM_BUFFERED_WINDOW_MS = 250.0
_TRAFFIC_CONTROL_DEGRADED_ERROR = "Traffic control is in degraded mode"
_MODEL_DRIFT_DETECTED_ERROR = "MODEL_DRIFT_DETECTED"
_DEGRADED_POLICY_BLOCK = "DEGRADED_POLICY_BLOCK"
_DEGRADED_CIRCUIT_OPEN = "DEGRADED_CIRCUIT_OPEN"
_DEGRADED_ENDPOINT_UNREACHABLE = "DEGRADED_ENDPOINT_UNREACHABLE"


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


def _drain_sse_events(buffer: str) -> tuple[list[tuple[str, str]], str]:
    buffer = buffer.replace("\r\n", "\n").replace("\r", "\n")
    events: list[tuple[str, str]] = []
    blocks = buffer.split("\n\n")
    tail = blocks.pop() if blocks else ""
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        events.extend(_iter_sse_events(block + "\n\n"))
    return events, tail


def parse_sse_events(chunk_text: str) -> list[tuple[str, str]]:
    """Public SSE parsing helper used by tests and probes."""
    events, _ = _drain_sse_events(f"{chunk_text}\n\n")
    return events


def _serialize_sse_event(event_name: str, data: Any) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_json_dict(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_content_text(payload: str) -> str:
    if not payload:
        return ""
    parsed = _parse_json_dict(payload)
    return str(parsed.get("text") or "")


def _estimate_text_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(len(stripped.split()), len(stripped) // 4)


def _consume_sse_events(
    *,
    drained_events: list[tuple[str, str]],
    events: list[str],
    content_parts: list[str],
    chunk_count: int,
    first_content_at_ms: float | None,
    chunk_at_ms: float,
    content_event_times_ms: list[float] | None = None,
) -> tuple[int, float | None]:
    for event_name, payload in drained_events:
        events.append(event_name)
        if event_name == "error":
            parsed_error = _parse_json_dict(payload)
            message = str(
                parsed_error.get("message")
                or parsed_error.get("code")
                or payload
                or _ANALYSIS_STREAM_FAILED
            )
            raise RuntimeError(message)
        if event_name != "content":
            continue
        text = _extract_content_text(payload)
        if not text:
            continue
        content_parts.append(text)
        chunk_count += 1
        if content_event_times_ms is not None:
            content_event_times_ms.append(chunk_at_ms)
        if first_content_at_ms is None:
            first_content_at_ms = chunk_at_ms
    return chunk_count, first_content_at_ms


def _parse_request_id(raw_request_id: Any) -> UUID | None:
    if raw_request_id is None:
        return None
    try:
        return UUID(str(raw_request_id).strip())
    except ValueError:
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
    if not isinstance(details, str):
        return payload
    _enrich_trace_payload(action=action, details=details, payload=payload)
    return payload


def _enrich_trace_payload(
    *, action: str, details: str, payload: dict[str, Any]
) -> None:
    if action == "response":
        parsed = _parse_json_dict(details)
        payload.update(
            {
                "chunks": parsed.get("chunks"),
                "total_ms": parsed.get("total_ms"),
                "chars": parsed.get("chars"),
                "truncated": parsed.get("truncated"),
            }
        )
        return
    if action == "first_chunk":
        payload["elapsed_ms"] = _extract_elapsed_ms(details)
        return
    if action == "context_preview":
        parsed = _parse_json_dict(details)
        payload["prompt_context_truncated"] = parsed.get("prompt_context_truncated")
        payload["hidden_prompts_count"] = parsed.get("hidden_prompts_count")
        return
    if action == "prompt_trim":
        payload["prompt_trimmed"] = True


def _extract_elapsed_ms(details: str) -> float | None:
    for fragment in details.split():
        if not fragment.startswith("elapsed_ms="):
            continue
        try:
            return float(fragment.split("=", 1)[1])
        except ValueError:
            return None
    return None


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
        "hidden_prompts_count": context_preview_step.get("hidden_prompts_count"),
        "adapter_applied": trace.adapter_applied,
        "adapter_id": trace.adapter_id,
    }


def _extract_context_preview_text(process_trace: dict[str, Any] | None) -> str:
    if not isinstance(process_trace, dict):
        return ""
    steps = process_trace.get("steps")
    if not isinstance(steps, list):
        return ""
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("action") or "") != "context_preview":
            continue
        details = step.get("details")
        if not isinstance(details, str):
            continue
        parsed = _parse_json_dict(details)
        preview = parsed.get("prompt_context_preview")
        if isinstance(preview, str):
            return preview
    return ""


def _extract_system_prompt_text(context_preview: str) -> str:
    if not context_preview:
        return ""
    normalized = context_preview.strip()
    if not normalized:
        return ""
    upper_preview = normalized.upper()
    system_index = upper_preview.find("SYSTEM:")
    if system_index < 0:
        return ""
    after_system = normalized[system_index + len("SYSTEM:") :]
    user_index = after_system.upper().find("USER:")
    if user_index >= 0:
        return after_system[:user_index].strip()
    return after_system.strip()


def _split_answer_fragments(answer_text: str) -> list[str]:
    normalized = answer_text.strip()
    if not normalized:
        return []
    fragments = [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()
    ]
    return fragments


def _compute_percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    bounded = max(0.0, min(100.0, percentile))
    raw_index = (len(ordered) - 1) * (bounded / 100.0)
    lower = int(raw_index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = raw_index - lower
    value = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
    return round(value, 2)


def _classify_stream_quality(
    *,
    chunk_count: int,
    first_content_at_ms: float | None,
    elapsed_ms: float,
) -> str:
    if chunk_count <= 0:
        return "no_content"
    if chunk_count > 1:
        return "live_streaming"
    if (
        first_content_at_ms is not None
        and first_content_at_ms >= _STREAM_DELAYED_THRESHOLD_MS
    ):
        return "single_chunk_delayed"
    if (
        first_content_at_ms is not None
        and (elapsed_ms - first_content_at_ms) <= _STREAM_BUFFERED_WINDOW_MS
    ):
        return "buffered_delivery"
    return "single_chunk"


def _build_stream_profile(
    *,
    request_ready_at_ms: float,
    response_received_at_ms: float,
    elapsed_ms: float,
    chunk_count: int,
    events: list[str],
    first_content_at_ms: float | None,
    content_event_times_ms: list[float],
    response_text: str,
) -> dict[str, Any]:
    intervals_ms: list[float] = []
    for previous, current in zip(content_event_times_ms, content_event_times_ms[1:]):
        intervals_ms.append(round(current - previous, 2))
    chars = len(response_text)
    chars_per_second = (
        round((chars / elapsed_ms) * 1000.0, 2) if elapsed_ms > 0 else None
    )
    return {
        "time_to_stream_open_ms": round(
            response_received_at_ms - request_ready_at_ms, 2
        ),
        "time_to_first_byte_ms": round(
            response_received_at_ms - request_ready_at_ms, 2
        ),
        "time_to_first_byte_estimated": True,
        "time_to_first_byte_source": "estimated_stream_open",
        "time_to_first_content_ms": (
            round(first_content_at_ms, 2)
            if isinstance(first_content_at_ms, (int, float))
            else None
        ),
        "time_to_response_done_ms": round(elapsed_ms, 2),
        "chunk_count": chunk_count,
        "event_count": len(events),
        "chunk_intervals_ms": intervals_ms,
        "chunk_interval_p50_ms": _compute_percentile(intervals_ms, 50.0),
        "chunk_interval_p95_ms": _compute_percentile(intervals_ms, 95.0),
        "chars_per_second": chars_per_second,
        "stream_quality": _classify_stream_quality(
            chunk_count=chunk_count,
            first_content_at_ms=first_content_at_ms,
            elapsed_ms=elapsed_ms,
        ),
    }


def _build_input_profile(
    *,
    prompt: str,
    process_trace: dict[str, Any] | None,
) -> dict[str, Any]:
    context_preview = _extract_context_preview_text(process_trace)
    system_prompt = _extract_system_prompt_text(context_preview)
    return {
        "prompt_chars": len(prompt),
        "prompt_tokens_est": _estimate_text_tokens(prompt),
        "context_tokens_est": _estimate_text_tokens(context_preview),
        "system_tokens_est": _estimate_text_tokens(system_prompt),
        "context_preview_available": bool(context_preview),
        "prompt_trimmed": bool(process_trace.get("prompt_trimmed"))
        if isinstance(process_trace, dict)
        else False,
        "context_preview_truncated": (
            bool(process_trace.get("context_preview_truncated"))
            if isinstance(process_trace, dict)
            else False
        ),
        "hidden_prompts_count": (
            int(process_trace.get("hidden_prompts_count") or 0)
            if isinstance(process_trace, dict)
            else 0
        ),
    }


def _build_generation_profile(
    *,
    max_tokens: int | None,
    temperature: float | None,
    top_p: float | None,
    process_trace: dict[str, Any] | None,
) -> dict[str, Any]:
    adapter_applied = (
        process_trace.get("adapter_applied")
        if isinstance(process_trace, dict)
        else None
    )
    adapter_id = (
        process_trace.get("adapter_id") if isinstance(process_trace, dict) else None
    )
    if adapter_applied is True or adapter_id:
        fallback_signal = "used"
    elif adapter_applied is False:
        fallback_signal = "none"
    else:
        fallback_signal = "unknown"
    return {
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "top_p_requested": top_p,
        "top_p_applied": None,
        "top_p_source": "request",
        "top_p_status": "requested_only"
        if isinstance(top_p, (int, float))
        else "unavailable",
        "adapter_applied": adapter_applied,
        "adapter_id": adapter_id,
        "fallback_signal": fallback_signal,
    }


def _build_evidence_coverage_profile(
    *,
    response_text: str,
    rag_focus: dict[str, Any],
) -> dict[str, Any]:
    fragments = _split_answer_fragments(response_text)
    links = rag_focus.get("answer_evidence_links")
    links_list = links if isinstance(links, list) else []
    linked_fragments = len(links_list)
    fragments_total = len(fragments)
    coverage_percent = (
        round((linked_fragments / fragments_total) * 100.0, 2)
        if fragments_total > 0
        else 0.0
    )
    orphan_fragments = max(0, fragments_total - linked_fragments)
    return {
        "fragments_total": fragments_total,
        "fragments_linked": linked_fragments,
        "coverage_percent": coverage_percent,
        "orphan_fragments": orphan_fragments,
    }


def _build_rag_profile(
    *,
    rag_focus: dict[str, Any],
) -> dict[str, Any]:
    entities = rag_focus.get("entities")
    evidence_edges = rag_focus.get("evidence_edges")
    active_entity_ids = rag_focus.get("active_entity_ids")
    return {
        "source": str(rag_focus.get("source") or "graph_fallback"),
        "entities_count": len(entities) if isinstance(entities, list) else 0,
        "evidence_edges_count": (
            len(evidence_edges) if isinstance(evidence_edges, list) else 0
        ),
        "active_entities_count": (
            len(active_entity_ids) if isinstance(active_entity_ids, list) else 0
        ),
        "grounding_score": rag_focus.get("grounding_score"),
    }


def _build_logit_profile(
    *,
    logit_lens: dict[str, Any],
) -> dict[str, Any]:
    checkpoints = logit_lens.get("checkpoints")
    interpretability = logit_lens.get("interpretability")
    interpretability_dict = (
        interpretability if isinstance(interpretability, dict) else {}
    )
    return {
        "source": str(logit_lens.get("source") or "probe_unavailable"),
        "status": str(logit_lens.get("status") or "probe_unavailable"),
        "checkpoints_count": len(checkpoints) if isinstance(checkpoints, list) else 0,
        "interpretable": bool(interpretability_dict.get("interpretable")),
        "confidence_band": str(
            interpretability_dict.get("confidence_band") or "unknown"
        ),
        "token_noise_ratio": float(
            interpretability_dict.get("token_noise_ratio") or 0.0
        ),
    }


def _build_operator_reason_codes(
    *,
    rag_source: str,
    coverage_percent: float,
    logit_source: str,
    proxy_active: bool,
    stream_quality: str,
    token_noise_ratio: float,
) -> list[str]:
    coverage_code = "R2_COVERAGE_LOW"
    if coverage_percent >= 70.0:
        coverage_code = "R2_COVERAGE_HIGH"
    elif coverage_percent >= 40.0:
        coverage_code = "R2_COVERAGE_MEDIUM"

    stream_code = "R4_STREAM_DEGRADED"
    if stream_quality in {"live_streaming", "single_chunk"}:
        stream_code = "R4_STREAM_OK"
    elif stream_quality == "single_chunk_delayed":
        stream_code = "R4_STREAM_DELAYED"

    noise_code = "R5_LOGIT_NOISE_LOW"
    if token_noise_ratio >= 0.7:
        noise_code = "R5_LOGIT_NOISE_HIGH"
    elif token_noise_ratio >= 0.35:
        noise_code = "R5_LOGIT_NOISE_MEDIUM"

    probe_code = "R3_PROBE_FALLBACK"
    if logit_source == "probe_runtime":
        probe_code = "R3_PROBE_PROXY" if proxy_active else "R3_PROBE_RUNTIME"

    return [
        "R1_RUNTIME_TRACE" if rag_source == "runtime_trace" else "R1_GRAPH_FALLBACK",
        coverage_code,
        probe_code,
        stream_code,
        noise_code,
    ]


def _resolve_operator_verdict(
    *,
    rag_source: str,
    coverage_percent: float,
    grounding_score: Any,
    logit_source: str,
) -> tuple[str, str]:
    grounded = (
        rag_source == "runtime_trace"
        and coverage_percent >= 60.0
        and isinstance(grounding_score, (int, float))
        and float(grounding_score) >= 0.55
    )
    weakly_grounded = (
        rag_source == "runtime_trace"
        or coverage_percent >= 35.0
        or logit_source == "probe_runtime"
    )
    if grounded:
        return ("grounded", "high" if coverage_percent >= 75 else "medium")
    if weakly_grounded:
        return ("weakly_grounded", "medium")
    return ("ungrounded", "low")


def _build_operator_conclusion_payload(
    *,
    rag_focus: dict[str, Any],
    logit_lens: dict[str, Any],
    evidence_coverage: dict[str, Any],
    stream_profile: dict[str, Any],
    analysis_capabilities: dict[str, Any],
) -> dict[str, Any]:
    rag_source = str(rag_focus.get("source") or "graph_fallback")
    logit_source = str(logit_lens.get("source") or "probe_unavailable")
    grounding_score = rag_focus.get("grounding_score")
    coverage_percent = float(evidence_coverage.get("coverage_percent") or 0.0)
    stream_quality = str(stream_profile.get("stream_quality") or "no_content")
    interpretability = logit_lens.get("interpretability")
    interpretability_dict = (
        interpretability if isinstance(interpretability, dict) else {}
    )
    token_noise_ratio = float(interpretability_dict.get("token_noise_ratio") or 0.0)
    proxy_active = bool(analysis_capabilities.get("proxy_active"))
    reason_codes = _build_operator_reason_codes(
        rag_source=rag_source,
        coverage_percent=coverage_percent,
        logit_source=logit_source,
        proxy_active=proxy_active,
        stream_quality=stream_quality,
        token_noise_ratio=token_noise_ratio,
    )
    verdict, confidence = _resolve_operator_verdict(
        rag_source=rag_source,
        coverage_percent=coverage_percent,
        grounding_score=grounding_score,
        logit_source=logit_source,
    )

    partial = (
        rag_source != "runtime_trace" or logit_source != "probe_runtime" or proxy_active
    )
    if proxy_active and logit_source == "probe_runtime":
        internals_quality = "proxy_probe"
    elif logit_source == "probe_runtime":
        internals_quality = "runtime_probe"
    else:
        internals_quality = "fallback_probe"

    return {
        "verdict": verdict,
        "confidence_tier": confidence,
        "partial": partial,
        "reason_codes": reason_codes,
        "stream_quality": stream_quality,
        "internals_quality": internals_quality,
        "evidence_coverage_percent": coverage_percent,
        "token_noise_ratio": round(token_noise_ratio, 4),
    }


def _capability_from_probe_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = str((payload or {}).get("source") or "probe_unavailable")
    status = str((payload or {}).get("status") or "probe_unavailable")
    available = source == "probe_runtime" and status == "ok"
    raw_code = (payload or {}).get("code")
    code = str(raw_code).strip() if isinstance(raw_code, str) else ""
    proxy = bool(code and "_proxy_" in code)
    native = bool(available and not proxy)
    if available:
        reason = code or "ok"
    else:
        reason = code or "probe_unavailable"
    return {
        "available": available,
        "native": native,
        "proxy": proxy,
        "source": source,
        "status": status,
        "reason": reason,
    }


def _build_probe_limits_payload(limits: dict[str, Any]) -> dict[str, Any]:
    return {
        "timeout_seconds": float(limits.get("timeout_seconds") or 0.0),
        "max_attempts": int(limits.get("max_attempts") or 0),
        "max_top_k": int(limits.get("max_top_k") or 0),
        "max_layer_count": int(limits.get("max_layer_count") or 0),
        "max_head_count": int(limits.get("max_head_count") or 0),
        "max_prompt_tokens": int(limits.get("max_prompt_tokens") or 0),
    }


def _resolve_internals_verdict(
    *,
    available_count: int,
    native_available_count: int,
    total_count: int,
) -> str:
    if native_available_count == total_count:
        return "full"
    if available_count > 0:
        return "partial"
    return "fallback_only"


def _build_analysis_capabilities_payload(
    *,
    attention: dict[str, Any] | None,
    saliency: dict[str, Any] | None,
    logit_lens: dict[str, Any] | None,
    probe_health: dict[str, Any] | None,
) -> dict[str, Any]:
    attention_capability = _capability_from_probe_payload(attention)
    saliency_capability = _capability_from_probe_payload(saliency)
    logit_lens_capability = _capability_from_probe_payload(logit_lens)
    available_count = sum(
        1
        for capability in (
            attention_capability,
            saliency_capability,
            logit_lens_capability,
        )
        if capability["available"]
    )
    native_available_count = sum(
        1
        for capability in (
            attention_capability,
            saliency_capability,
            logit_lens_capability,
        )
        if capability.get("native")
    )
    proxy_active = any(
        bool(capability.get("proxy"))
        for capability in (
            attention_capability,
            saliency_capability,
            logit_lens_capability,
        )
    )
    total_count = 3
    probe_health_dict = probe_health if isinstance(probe_health, dict) else {}
    limits = probe_health_dict.get("limits")
    limits_dict = limits if isinstance(limits, dict) else {}
    internals_verdict = _resolve_internals_verdict(
        available_count=available_count,
        native_available_count=native_available_count,
        total_count=total_count,
    )
    return {
        "attention": attention_capability,
        "saliency": saliency_capability,
        "logit_lens": logit_lens_capability,
        "available_count": available_count,
        "native_available_count": native_available_count,
        "total_count": total_count,
        "proxy_active": proxy_active,
        "probe_profile": str(probe_health_dict.get("profile") or "unknown"),
        "probe_enabled": bool(probe_health_dict.get("enabled")),
        "probe_healthy": bool(probe_health_dict.get("healthy")),
        "runtime_supported": bool(probe_health_dict.get("runtime_supported")),
        "endpoint_configured": bool(probe_health_dict.get("endpoint_configured")),
        "model_whitelisted": bool(probe_health_dict.get("model_whitelisted")),
        "limits": _build_probe_limits_payload(limits_dict),
        "internals_verdict": internals_verdict,
    }


def _record_run_trends(
    *,
    process_trace: dict[str, Any] | None,
    rag_profile: dict[str, Any],
    logit_profile: dict[str, Any],
    stream_profile: dict[str, Any],
    evidence_coverage: dict[str, Any],
    settings: Any = None,
) -> dict[str, Any] | None:
    request_id = ""
    if isinstance(process_trace, dict):
        request_id = str(process_trace.get("request_id") or "").strip()
    if not request_id:
        request_id = f"run-{int(time.time() * 1000)}-{uuid4().hex[:8]}"
    coverage_raw = evidence_coverage.get("coverage_percent")
    first_content_raw = stream_profile.get("time_to_first_content_ms")
    token_noise_raw = logit_profile.get("token_noise_ratio")
    coverage_percent = (
        float(coverage_raw) if isinstance(coverage_raw, (int, float)) else None
    )
    first_content_ms = (
        float(first_content_raw)
        if isinstance(first_content_raw, (int, float))
        else None
    )
    token_noise_ratio = (
        float(token_noise_raw) if isinstance(token_noise_raw, (int, float)) else None
    )

    return record_operator_run(
        request_id=request_id,
        rag_source=str(rag_profile.get("source") or "graph_fallback"),
        probe_source=str(logit_profile.get("source") or "probe_unavailable"),
        stream_quality=str(stream_profile.get("stream_quality") or "unknown"),
        coverage_percent=coverage_percent,
        first_content_ms=first_content_ms,
        token_noise_ratio=token_noise_ratio,
        settings=settings,
    )


async def _record_run_trends_async(
    *,
    process_trace: dict[str, Any] | None,
    rag_profile: dict[str, Any],
    logit_profile: dict[str, Any],
    stream_profile: dict[str, Any],
    evidence_coverage: dict[str, Any],
    settings: Any = None,
) -> dict[str, Any] | None:
    return await asyncio.to_thread(
        _record_run_trends,
        process_trace=process_trace,
        rag_profile=rag_profile,
        logit_profile=logit_profile,
        stream_profile=stream_profile,
        evidence_coverage=evidence_coverage,
        settings=settings,
    )


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


def _build_degraded_mode_skipped_result(
    *,
    prompt: str,
    runtime: dict[str, Any],
    request_ready_at_ms: float,
    elapsed_ms: float,
    error_code: str = _DEGRADED_POLICY_BLOCK,
    detail: str = "Traffic control degraded mode active",
) -> dict[str, Any]:
    timeline: list[dict[str, Any]] = [
        {
            "id": "snapshot_before",
            "label": _TIMELINE_LABEL_SNAPSHOT_CAPTURED,
            "status": "done",
            "detail": runtime["label"],
            "at_ms": 0.0,
        },
        {
            "id": "request_ready",
            "label": _TIMELINE_LABEL_PROMPT_PREPARED,
            "status": "done",
            "detail": prompt,
            "at_ms": request_ready_at_ms,
        },
        {
            "id": "analysis_skipped",
            "label": "Analysis skipped",
            "status": "skipped",
            "detail": detail,
            "at_ms": elapsed_ms,
        },
    ]
    return {
        "analysis_enabled": True,
        "status": "skipped",
        "skipped_reason": "traffic_control_degraded_mode",
        "snapshot_after": None,
        "analysis": {
            "prompt": prompt,
            "response": "",
            "chunk_count": 0,
            "events": ["skipped"],
            "timeline_step_count": len(timeline),
            "timeline": timeline,
            "elapsed_ms": elapsed_ms,
            "provider": runtime["provider"],
            "model": runtime["model"],
            "runtime_label": runtime["label"],
            "request_ready_ms": request_ready_at_ms,
            "response_received_ms": request_ready_at_ms,
            "snapshot_after_ms": None,
            "process": None,
            "error": _TRAFFIC_CONTROL_DEGRADED_ERROR,
            "error_code": error_code,
        },
    }


def _extract_model_drift_issue(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    runtime_drift = snapshot.get("runtime_drift")
    if not isinstance(runtime_drift, dict):
        return None
    issues = runtime_drift.get("issues")
    if not isinstance(issues, list) or not issues:
        return None
    for issue in issues:
        if not isinstance(issue, str):
            continue
        normalized = issue.lower()
        if "target model" in normalized or "model drift" in normalized:
            return {
                "issue": issue,
                "runtime_active_model_id": runtime_drift.get("runtime_active_model_id"),
                "daemon_target_model": runtime_drift.get("daemon_target_model"),
            }
    return None


def _build_model_drift_skipped_result(
    *,
    prompt: str,
    runtime: dict[str, Any],
    request_ready_at_ms: float,
    drift_issue: dict[str, Any],
) -> dict[str, Any]:
    issue_text = str(drift_issue.get("issue") or "Model drift detected").strip()
    runtime_active_model_id = drift_issue.get("runtime_active_model_id")
    daemon_target_model = drift_issue.get("daemon_target_model")
    detail_suffix = ""
    if runtime_active_model_id or daemon_target_model:
        detail_suffix = (
            f" (runtime_active_model_id={runtime_active_model_id or 'n/a'}, "
            f"daemon_target_model={daemon_target_model or 'n/a'})"
        )
    emit_runtime_model_event(
        "runtime_model_mismatch_detected",
        source="introspection_preflight",
        runtime=str(runtime.get("provider") or ""),
        runtime_active_model_id=runtime_active_model_id or "n/a",
        daemon_target_model=daemon_target_model or "n/a",
    )
    detail = f"{issue_text}{detail_suffix}"
    timeline: list[dict[str, Any]] = [
        {
            "id": "snapshot_before",
            "label": _TIMELINE_LABEL_SNAPSHOT_CAPTURED,
            "status": "done",
            "detail": runtime["label"],
            "at_ms": 0.0,
        },
        {
            "id": "request_ready",
            "label": _TIMELINE_LABEL_PROMPT_PREPARED,
            "status": "done",
            "detail": prompt,
            "at_ms": request_ready_at_ms,
        },
        {
            "id": "analysis_skipped_model_drift",
            "label": "Analysis skipped",
            "status": "skipped",
            "detail": detail,
            "at_ms": request_ready_at_ms,
        },
    ]
    return {
        "analysis_enabled": True,
        "status": "skipped",
        "skipped_reason": "model_drift_detected",
        "snapshot_after": None,
        "analysis": {
            "prompt": prompt,
            "response": "",
            "chunk_count": 0,
            "events": ["skipped"],
            "timeline_step_count": len(timeline),
            "timeline": timeline,
            "elapsed_ms": request_ready_at_ms,
            "provider": runtime["provider"],
            "model": runtime["model"],
            "runtime_label": runtime["label"],
            "request_ready_ms": request_ready_at_ms,
            "response_received_ms": request_ready_at_ms,
            "snapshot_after_ms": None,
            "process": None,
            "error": _MODEL_DRIFT_DETECTED_ERROR,
            "error_code": _MODEL_DRIFT_DETECTED_ERROR,
            "runtime_active_model_id": runtime_active_model_id,
            "daemon_target_model": daemon_target_model,
        },
    }


def _resolve_degraded_error_details(error: Exception) -> tuple[str, str] | None:
    message = str(error or "").strip()
    normalized = message.lower()
    if not normalized:
        return None
    if "circuit breaker open" in normalized:
        return _DEGRADED_CIRCUIT_OPEN, message
    if (
        "traffic control is in degraded mode" in normalized
        or "degraded mode active" in normalized
        or "global outbound request cap exceeded" in normalized
        or "rate limit exceeded" in normalized
    ):
        return _DEGRADED_POLICY_BLOCK, message
    if (
        "connect error" in normalized
        or "connection refused" in normalized
        or "name or service not known" in normalized
        or "timed out" in normalized
    ):
        return _DEGRADED_ENDPOINT_UNREACHABLE, message
    return None


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
                    "label": _TIMELINE_LABEL_SNAPSHOT_CAPTURED,
                    "status": "done",
                    "detail": runtime["label"],
                    "at_ms": 0.0,
                },
                {
                    "id": "request_ready",
                    "label": _TIMELINE_LABEL_PROMPT_PREPARED,
                    "status": "done",
                    "detail": prompt,
                    "at_ms": request_ready_at_ms,
                },
                {
                    "id": "stream_opened",
                    "label": _TIMELINE_LABEL_STREAM_OPENED,
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


def _build_failed_analysis_result(
    *,
    prompt: str,
    runtime: dict[str, Any],
    events: list[str],
    chunk_count: int,
    response_text: str,
    request_ready_at_ms: float,
    response_received_at_ms: float,
    elapsed_ms: float,
    error_message: str,
) -> dict[str, Any]:
    timeline: list[dict[str, Any]] = [
        {
            "id": "snapshot_before",
            "label": _TIMELINE_LABEL_SNAPSHOT_CAPTURED,
            "status": "done",
            "detail": runtime["label"],
            "at_ms": 0.0,
        },
        {
            "id": "request_ready",
            "label": _TIMELINE_LABEL_PROMPT_PREPARED,
            "status": "done",
            "detail": prompt,
            "at_ms": request_ready_at_ms,
        },
        {
            "id": "stream_opened",
            "label": _TIMELINE_LABEL_STREAM_OPENED,
            "status": "done",
            "detail": f"{len(events)} event(s) observed",
            "at_ms": response_received_at_ms,
        },
        {
            "id": "analysis_failed",
            "label": "Analysis failed",
            "status": "failed",
            "detail": error_message,
            "at_ms": elapsed_ms,
        },
    ]
    return {
        "analysis_enabled": True,
        "status": "failed",
        "snapshot_after": None,
        "analysis": {
            "prompt": prompt,
            "response": response_text,
            "chunk_count": chunk_count,
            "events": events,
            "timeline_step_count": len(timeline),
            "timeline": timeline,
            "elapsed_ms": elapsed_ms,
            "provider": runtime["provider"],
            "model": runtime["model"],
            "runtime_label": runtime["label"],
            "request_ready_ms": request_ready_at_ms,
            "response_received_ms": response_received_at_ms,
            "snapshot_after_ms": None,
            "process": None,
            "error": error_message,
        },
    }


def _build_stream_bootstrap_exception_result(
    *,
    exc: Exception,
    prompt: str,
    runtime: dict[str, Any],
    request_ready_at_ms: float,
    elapsed_ms: float,
) -> tuple[str | None, dict[str, Any]]:
    degraded_details = _resolve_degraded_error_details(exc)
    if degraded_details is not None:
        error_code, detail = degraded_details
        return None, _build_degraded_mode_skipped_result(
            prompt=prompt,
            runtime=runtime,
            request_ready_at_ms=request_ready_at_ms,
            elapsed_ms=elapsed_ms,
            error_code=error_code,
            detail=detail,
        )

    logger.exception("Model introspection analysis stream bootstrap failed")
    error_message = str(exc) or _ANALYSIS_STREAM_FAILED
    return error_message, _build_failed_analysis_result(
        prompt=prompt,
        runtime=runtime,
        events=["error"],
        chunk_count=0,
        response_text="",
        request_ready_at_ms=request_ready_at_ms,
        response_received_at_ms=request_ready_at_ms,
        elapsed_ms=elapsed_ms,
        error_message=error_message,
    )


def _build_stream_consumption_exception_result(
    *,
    exc: Exception,
    prompt: str,
    runtime: dict[str, Any],
    request_ready_at_ms: float,
    response_received_at_ms: float,
    elapsed_ms: float,
    events: list[str],
    chunk_count: int,
    response_text: str,
) -> tuple[str | None, dict[str, Any]]:
    degraded_details = _resolve_degraded_error_details(exc)
    if degraded_details is not None:
        error_code, detail = degraded_details
        return None, _build_degraded_mode_skipped_result(
            prompt=prompt,
            runtime=runtime,
            request_ready_at_ms=request_ready_at_ms,
            elapsed_ms=elapsed_ms,
            error_code=error_code,
            detail=detail,
        )

    logger.exception("Model introspection analysis stream failed")
    error_message = str(exc) or _ANALYSIS_STREAM_FAILED
    return error_message, _build_failed_analysis_result(
        prompt=prompt,
        runtime=runtime,
        events=events + ["error"],
        chunk_count=chunk_count,
        response_text=response_text,
        request_ready_at_ms=request_ready_at_ms,
        response_received_at_ms=response_received_at_ms,
        elapsed_ms=elapsed_ms,
        error_message=error_message,
    )


async def _collect_streaming_response(response: Any) -> dict[str, Any]:
    content_parts: list[str] = []
    events: list[str] = []
    chunk_count = 0
    first_content_at_ms: float | None = None
    content_event_times_ms: list[float] = []
    stream_started_at = time.perf_counter()

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        status_code = getattr(response, "status_code", "unknown")
        raise RuntimeError(
            f"analysis stream response does not expose body iterator (status={status_code})"
        )

    raw_chunks: list[str] = []
    sse_tail = ""
    async for chunk in body_iterator:
        chunk_at_ms = (time.perf_counter() - stream_started_at) * 1000.0
        chunk_text = (
            chunk.decode("utf-8", errors="replace")
            if isinstance(chunk, bytes)
            else str(chunk)
        )
        raw_chunks.append(chunk_text)
        drained_events, sse_tail = _drain_sse_events(sse_tail + chunk_text)
        chunk_count, first_content_at_ms = _consume_sse_events(
            drained_events=drained_events,
            events=events,
            content_parts=content_parts,
            chunk_count=chunk_count,
            first_content_at_ms=first_content_at_ms,
            chunk_at_ms=chunk_at_ms,
            content_event_times_ms=content_event_times_ms,
        )

    if sse_tail.strip():
        drained_events, _ = _drain_sse_events(sse_tail + "\n\n")
        chunk_count, first_content_at_ms = _consume_sse_events(
            drained_events=drained_events,
            events=events,
            content_parts=content_parts,
            chunk_count=chunk_count,
            first_content_at_ms=first_content_at_ms,
            chunk_at_ms=(time.perf_counter() - stream_started_at) * 1000.0,
            content_event_times_ms=content_event_times_ms,
        )

    return {
        "response_text": "".join(content_parts),
        "chunk_count": chunk_count,
        "events": events,
        "raw_chunks": raw_chunks,
        "first_content_at_ms": first_content_at_ms,
        "content_event_times_ms": content_event_times_ms,
    }


def _build_logit_lens_timeline_step(
    *,
    logit_lens: dict[str, Any],
    at_ms: float,
) -> dict[str, Any]:
    diagnostics = logit_lens.get("diagnostics")
    diagnostics_dict = diagnostics if isinstance(diagnostics, dict) else {}
    elapsed_ms = diagnostics_dict.get("elapsed_ms")
    status = str(logit_lens.get("status") or "probe_unavailable")
    code = str(logit_lens.get("code") or "probe_unavailable")
    checkpoints = logit_lens.get("checkpoints")
    checkpoint_count = len(checkpoints) if isinstance(checkpoints, list) else 0
    if status == "ok":
        detail = (
            f"{checkpoint_count} checkpoint(s) · {elapsed_ms:.1f} ms"
            if isinstance(elapsed_ms, (int, float))
            else f"{checkpoint_count} checkpoint(s)"
        )
        step_status = "done"
    elif _is_probe_failure_status_or_code(status=status, code=code):
        detail = code
        step_status = "failed"
    else:
        detail = code
        step_status = "skipped"
    return {
        "id": "logit_lens_probe",
        "label": _TIMELINE_LABEL_LOGIT_LENS,
        "status": step_status,
        "detail": detail,
        "reason_code": None if step_status == "done" else code,
        "path": "internals_path",
        "at_ms": at_ms,
        "progress": 90,
    }


def _is_probe_failure_status_or_code(*, status: str, code: str) -> bool:
    normalized_status = str(status or "").strip().lower()
    normalized_code = str(code or "").strip().lower()
    if normalized_status == "failed":
        return True
    if normalized_code in {
        "probe_failed",
        "runtime_error",
        "probe_transport_error",
    }:
        return True
    return normalized_code.startswith("probe_timeout")


def _build_probe_timeline_step(
    *,
    step_id: str,
    step_label: str,
    payload: dict[str, Any],
    at_ms: float,
    progress: int = 95,
) -> dict[str, Any]:
    diagnostics = payload.get("diagnostics")
    diagnostics_dict = diagnostics if isinstance(diagnostics, dict) else {}
    elapsed_ms = diagnostics_dict.get("elapsed_ms")
    status = str(payload.get("status") or "probe_unavailable")
    code = str(payload.get("code") or "probe_unavailable")
    if status == "ok":
        detail = (
            f"ok · {elapsed_ms:.1f} ms"
            if isinstance(elapsed_ms, (int, float))
            else "ok"
        )
        step_status = "done"
    elif _is_probe_failure_status_or_code(status=status, code=code):
        detail = code
        step_status = "failed"
    else:
        detail = code
        step_status = "skipped"
    return {
        "id": step_id,
        "label": step_label,
        "status": step_status,
        "detail": detail,
        "reason_code": None if step_status == "done" else code,
        "path": "internals_path",
        "at_ms": at_ms,
        "progress": progress,
    }


async def _collect_logit_lens_payload_safe(
    *,
    prompt: str,
    response_text: str,
) -> dict[str, Any]:
    try:
        return await build_logit_lens_payload(
            prompt=prompt,
            response_text=response_text,
        )
    except (RuntimeError, ValueError, TypeError):
        logger.exception("Model introspection logit lens probe failed")
        return {
            "source": "probe_unavailable",
            "status": "probe_unavailable",
            "code": "probe_failed",
            "message": "Probe is unavailable for this run",
            "runtime_label": None,
            "input_tokens": [],
            "output_tokens": [],
            "checkpoints": [],
            "signals": {
                "early_unstable": False,
                "late_stabilized": False,
                "low_confidence_path": False,
            },
            "interpretability": {
                "interpretable": False,
                "confidence_band": "unknown",
                "token_noise_ratio": 1.0,
                "readable_top_tokens": 0,
                "total_top_tokens": 0,
            },
            "diagnostics": {},
        }


def _build_rag_focus_fallback(
    *,
    prompt: str,
) -> dict[str, Any]:
    return {
        "source": "graph_fallback",
        "query": prompt,
        "entities": [],
        "evidence_edges": [],
        "active_entity_ids": [],
        "grounding_score": None,
        "answer_evidence_links": [],
    }


def _collect_rag_focus_payload_safe(
    *,
    prompt: str,
    snapshot: dict[str, Any],
    process_trace: dict[str, Any] | None,
    response_text: str,
) -> dict[str, Any]:
    try:
        return build_rag_focus_payload(
            prompt=prompt,
            snapshot=snapshot,
            process_trace=process_trace,
            response_text=response_text,
        )
    except (RuntimeError, ValueError, TypeError):
        logger.exception("Model introspection rag focus extraction failed")
        return _build_rag_focus_fallback(
            prompt=prompt,
        )


async def _collect_attention_payload_safe(
    *,
    prompt: str,
) -> dict[str, Any]:
    try:
        return await build_attention_payload(prompt=prompt)
    except (RuntimeError, ValueError, TypeError):
        logger.exception("Model introspection attention probe failed")
        return {
            "source": "probe_unavailable",
            "status": "probe_unavailable",
            "code": "attention_unavailable",
            "message": "Attention probe unavailable",
            "runtime_label": None,
            "tokens": [],
            "layers": [],
            "diagnostics": {},
        }


async def _collect_saliency_payload_safe(
    *,
    prompt: str,
    response_text: str,
) -> dict[str, Any]:
    try:
        return await build_saliency_payload(
            prompt=prompt,
            response_text=response_text,
        )
    except (RuntimeError, ValueError, TypeError):
        logger.exception("Model introspection saliency probe failed")
        return {
            "source": "probe_unavailable",
            "status": "probe_unavailable",
            "code": "saliency_unavailable",
            "message": "Saliency probe unavailable",
            "runtime_label": None,
            "method": None,
            "target_output_token_index": None,
            "target_output_token": None,
            "token_weights": [],
            "diagnostics": {},
        }


def _build_analysis_timeline(
    *,
    prompt: str,
    runtime: dict[str, Any],
    stream_payload: dict[str, Any],
    elapsed_ms: float,
    request_ready_at_ms: float,
    response_received_at_ms: float,
    snapshot_after_at_ms: float | None,
    logit_lens_step: dict[str, Any] | None = None,
    attention_step: dict[str, Any] | None = None,
    saliency_step: dict[str, Any] | None = None,
    refreshed_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = [
        {
            "id": "snapshot_before",
            "label": _TIMELINE_LABEL_SNAPSHOT_CAPTURED,
            "status": "done",
            "detail": runtime["label"],
            "path": "answer_path",
            "at_ms": 0.0,
            "progress": 0,
        },
        {
            "id": "request_ready",
            "label": _TIMELINE_LABEL_PROMPT_PREPARED,
            "status": "done",
            "detail": prompt,
            "path": "answer_path",
            "at_ms": request_ready_at_ms,
            "progress": 10,
        },
        {
            "id": "stream_opened",
            "label": _TIMELINE_LABEL_STREAM_OPENED,
            "status": "done",
            "detail": f"{len(stream_payload.get('events', []))} event(s) observed",
            "path": "answer_path",
            "at_ms": response_received_at_ms,
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
                "path": "answer_path",
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
            "path": "answer_path",
            "at_ms": elapsed_ms,
            "progress": 85,
        }
    )

    if logit_lens_step is not None:
        timeline.append(logit_lens_step)
    if attention_step is not None:
        timeline.append(attention_step)
    if saliency_step is not None:
        timeline.append(saliency_step)

    if refreshed_snapshot is not None:
        timeline.append(
            {
                "id": "snapshot_after",
                "label": "Snapshot refreshed",
                "status": "done",
                "detail": f"{len(refreshed_snapshot.get('available_packages', []))} packages available",
                "path": "answer_path",
                "at_ms": float(snapshot_after_at_ms or elapsed_ms),
                "progress": 100,
            }
        )

    return timeline


@dataclass(slots=True)
class _CompletedAnalysisPayloadContext:
    prompt: str
    stream_payload: dict[str, Any]
    chunk_count: int
    events: list[str]
    analysis_timeline: list[dict[str, Any]]
    elapsed_ms: float
    runtime: dict[str, Any]
    request_ready_at_ms: float
    response_received_at_ms: float
    snapshot_after_at_ms: float
    process_trace: dict[str, Any] | None
    rag_focus: dict[str, Any]
    attention: dict[str, Any]
    saliency: dict[str, Any]
    rag_profile: dict[str, Any]
    logit_lens: dict[str, Any]
    logit_profile: dict[str, Any]
    input_profile: dict[str, Any]
    generation_profile: dict[str, Any]
    stream_profile: dict[str, Any]
    evidence_coverage: dict[str, Any]
    operator_conclusion: dict[str, Any]
    analysis_capabilities: dict[str, Any]
    run_trends: dict[str, Any] | None


@dataclass(slots=True)
class _FinalizeCompletedAnalysisArgs:
    prompt: str
    snapshot: dict[str, Any]
    runtime: dict[str, Any]
    stream_payload: dict[str, Any]
    request_id: UUID | None
    flow_started_at: float
    request_ready_at_ms: float
    response_received_at_ms: float
    max_tokens: int | None
    temperature: float | None
    top_p: float | None
    logit_lens: dict[str, Any]
    attention: dict[str, Any]
    saliency: dict[str, Any]
    model_manager: Any = None
    settings: Any = None


def _build_completed_analysis_payload(
    context: _CompletedAnalysisPayloadContext,
) -> dict[str, Any]:
    return {
        "prompt": context.prompt,
        "response": context.stream_payload["response_text"],
        "chunk_count": context.chunk_count,
        "events": context.events,
        "timeline_step_count": len(context.analysis_timeline),
        "timeline": context.analysis_timeline,
        "elapsed_ms": context.elapsed_ms,
        "provider": context.runtime["provider"],
        "model": context.runtime["model"],
        "runtime_label": context.runtime["label"],
        "request_ready_ms": context.request_ready_at_ms,
        "response_received_ms": context.response_received_at_ms,
        "snapshot_after_ms": context.snapshot_after_at_ms,
        "process": context.process_trace,
        "rag_focus": context.rag_focus,
        "attention": context.attention,
        "saliency": context.saliency,
        "rag_profile": context.rag_profile,
        "logit_lens": context.logit_lens,
        "logit_profile": context.logit_profile,
        "input_profile": context.input_profile,
        "generation_profile": context.generation_profile,
        "stream_profile": context.stream_profile,
        "evidence_coverage": context.evidence_coverage,
        "operator_conclusion": context.operator_conclusion,
        "analysis_capabilities": context.analysis_capabilities,
        "run_trends": context.run_trends,
    }


async def _finalize_completed_analysis(
    args: _FinalizeCompletedAnalysisArgs,
) -> tuple[dict[str, Any], dict[str, Any], float]:
    elapsed_ms = (time.perf_counter() - args.flow_started_at) * 1000.0
    probe_steps_at_ms = elapsed_ms
    logit_lens_step = _build_logit_lens_timeline_step(
        logit_lens=args.logit_lens,
        at_ms=probe_steps_at_ms,
    )
    attention_step = _build_probe_timeline_step(
        step_id="attention_probe",
        step_label=_TIMELINE_LABEL_ATTENTION,
        payload=args.attention,
        at_ms=probe_steps_at_ms,
        progress=93,
    )
    saliency_step = _build_probe_timeline_step(
        step_id="saliency_probe",
        step_label=_TIMELINE_LABEL_SALIENCY,
        payload=args.saliency,
        at_ms=probe_steps_at_ms,
        progress=96,
    )
    try:
        refreshed_snapshot = await build_model_introspection_snapshot(
            model_manager=args.model_manager, settings=args.settings
        )
        snapshot_after_at_ms = (time.perf_counter() - args.flow_started_at) * 1000.0
    except Exception:
        logger.exception("Model introspection snapshot refresh failed")
        refreshed_snapshot = args.snapshot
        snapshot_after_at_ms = None
    process_trace = _summarize_request_trace(args.request_id)
    response_text = str(args.stream_payload.get("response_text") or "")
    rag_focus = _collect_rag_focus_payload_safe(
        prompt=args.prompt,
        snapshot=args.snapshot,
        process_trace=process_trace,
        response_text=response_text,
    )
    input_profile = _build_input_profile(
        prompt=args.prompt, process_trace=process_trace
    )
    generation_profile = _build_generation_profile(
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        process_trace=process_trace,
    )
    stream_profile = _build_stream_profile(
        request_ready_at_ms=args.request_ready_at_ms,
        response_received_at_ms=args.response_received_at_ms,
        elapsed_ms=elapsed_ms,
        chunk_count=int(args.stream_payload.get("chunk_count") or 0),
        events=list(args.stream_payload.get("events") or []),
        first_content_at_ms=(
            float(args.stream_payload["first_content_at_ms"])
            if isinstance(args.stream_payload.get("first_content_at_ms"), (int, float))
            else None
        ),
        content_event_times_ms=list(
            args.stream_payload.get("content_event_times_ms") or []
        ),
        response_text=response_text,
    )
    evidence_coverage = _build_evidence_coverage_profile(
        response_text=response_text,
        rag_focus=rag_focus,
    )
    rag_profile = _build_rag_profile(rag_focus=rag_focus)
    logit_profile = _build_logit_profile(logit_lens=args.logit_lens)
    analysis_capabilities = _build_analysis_capabilities_payload(
        attention=args.attention,
        saliency=args.saliency,
        logit_lens=args.logit_lens,
        probe_health=refreshed_snapshot.get("probe"),
    )
    operator_conclusion = _build_operator_conclusion_payload(
        rag_focus=rag_focus,
        logit_lens=args.logit_lens,
        evidence_coverage=evidence_coverage,
        stream_profile=stream_profile,
        analysis_capabilities=analysis_capabilities,
    )
    try:
        run_trends = await _record_run_trends_async(
            process_trace=process_trace,
            rag_profile=rag_profile,
            logit_profile=logit_profile,
            stream_profile=stream_profile,
            evidence_coverage=evidence_coverage,
            settings=args.settings,
        )
    except Exception:
        logger.exception("Model introspection run trends persistence failed")
        run_trends = None
    analysis_timeline = _build_analysis_timeline(
        prompt=args.prompt,
        runtime=args.runtime,
        stream_payload=args.stream_payload,
        elapsed_ms=elapsed_ms,
        request_ready_at_ms=args.request_ready_at_ms,
        response_received_at_ms=args.response_received_at_ms,
        snapshot_after_at_ms=snapshot_after_at_ms,
        logit_lens_step=logit_lens_step,
        attention_step=attention_step,
        saliency_step=saliency_step,
        refreshed_snapshot=refreshed_snapshot,
    )
    payload = _build_completed_analysis_payload(
        _CompletedAnalysisPayloadContext(
            prompt=args.prompt,
            stream_payload=args.stream_payload,
            chunk_count=int(args.stream_payload.get("chunk_count") or 0),
            events=list(args.stream_payload.get("events") or []),
            analysis_timeline=analysis_timeline,
            elapsed_ms=elapsed_ms,
            runtime=args.runtime,
            request_ready_at_ms=args.request_ready_at_ms,
            response_received_at_ms=args.response_received_at_ms,
            snapshot_after_at_ms=(
                snapshot_after_at_ms
                if isinstance(snapshot_after_at_ms, (int, float))
                else elapsed_ms
            ),
            process_trace=process_trace,
            rag_focus=rag_focus,
            attention=args.attention,
            saliency=args.saliency,
            rag_profile=rag_profile,
            logit_lens=args.logit_lens,
            logit_profile=logit_profile,
            input_profile=input_profile,
            generation_profile=generation_profile,
            stream_profile=stream_profile,
            evidence_coverage=evidence_coverage,
            operator_conclusion=operator_conclusion,
            analysis_capabilities=analysis_capabilities,
            run_trends=run_trends,
        )
    )
    effective_snapshot_after_at_ms = (
        float(snapshot_after_at_ms)
        if isinstance(snapshot_after_at_ms, (int, float))
        else elapsed_ms
    )
    return payload, refreshed_snapshot, effective_snapshot_after_at_ms


async def stream_model_introspection_analysis(
    *,
    prompt: str,
    live_analysis_enabled: bool = False,
    max_tokens: int | None = 128,
    temperature: float | None = 0.2,
    top_p: float | None = None,
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

    drift_issue = _extract_model_drift_issue(snapshot)
    if drift_issue is not None:
        request_ready_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
        skipped_result = _build_model_drift_skipped_result(
            prompt=prompt,
            runtime=runtime,
            request_ready_at_ms=request_ready_at_ms,
            drift_issue=drift_issue,
        )
        yield _serialize_sse_event("analysis_start", skipped_result)
        yield _serialize_sse_event("analysis_done", skipped_result)
        return

    request = SimpleChatRequest(
        content=prompt,
        model=runtime["model"],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )
    request_ready_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
    running_result = _build_running_analysis_result(
        prompt=prompt,
        runtime=runtime,
        request_ready_at_ms=request_ready_at_ms,
    )
    try:
        response = await stream_simple_chat(request)
        request_id = _parse_request_id(_get_response_header(response, "X-Request-Id"))
        response_received_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - flow_started_at) * 1000.0
        error_message, done_payload = _build_stream_bootstrap_exception_result(
            exc=exc,
            prompt=prompt,
            runtime=runtime,
            request_ready_at_ms=request_ready_at_ms,
            elapsed_ms=elapsed_ms,
        )
        if error_message is not None:
            yield _serialize_sse_event(
                "error",
                {"code": "analysis_stream_failed", "message": error_message},
            )
        else:
            yield _serialize_sse_event(
                "analysis_start",
                running_result,
            )
        yield _serialize_sse_event("analysis_done", done_payload)
        return

    yield _serialize_sse_event("analysis_start", running_result)

    content_parts: list[str] = []
    events: list[str] = []
    chunk_count = 0
    first_content_at_ms: float | None = None
    content_event_times_ms: list[float] = []
    sse_tail = ""

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        elapsed_ms = (time.perf_counter() - flow_started_at) * 1000.0
        error_message = "analysis stream response does not expose a body iterator"
        yield _serialize_sse_event(
            "error",
            {"code": "analysis_stream_failed", "message": error_message},
        )
        yield _serialize_sse_event(
            "analysis_done",
            _build_failed_analysis_result(
                prompt=prompt,
                runtime=runtime,
                events=events + ["error"],
                chunk_count=chunk_count,
                response_text="".join(content_parts),
                request_ready_at_ms=request_ready_at_ms,
                response_received_at_ms=response_received_at_ms,
                elapsed_ms=elapsed_ms,
                error_message=error_message,
            ),
        )
        return

    try:
        async for chunk in body_iterator:
            chunk_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
            chunk_text = (
                chunk.decode("utf-8", errors="replace")
                if isinstance(chunk, bytes)
                else str(chunk)
            )
            drained_events, sse_tail = _drain_sse_events(sse_tail + chunk_text)
            chunk_count, first_content_at_ms = _consume_sse_events(
                drained_events=drained_events,
                events=events,
                content_parts=content_parts,
                chunk_count=chunk_count,
                first_content_at_ms=first_content_at_ms,
                chunk_at_ms=chunk_at_ms,
                content_event_times_ms=content_event_times_ms,
            )
            yield chunk_text

        if sse_tail.strip():
            drained_events, _ = _drain_sse_events(sse_tail + "\n\n")
            chunk_count, first_content_at_ms = _consume_sse_events(
                drained_events=drained_events,
                events=events,
                content_parts=content_parts,
                chunk_count=chunk_count,
                first_content_at_ms=first_content_at_ms,
                chunk_at_ms=(time.perf_counter() - flow_started_at) * 1000.0,
                content_event_times_ms=content_event_times_ms,
            )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - flow_started_at) * 1000.0
        error_message, done_payload = _build_stream_consumption_exception_result(
            exc=exc,
            prompt=prompt,
            runtime=runtime,
            request_ready_at_ms=request_ready_at_ms,
            response_received_at_ms=response_received_at_ms,
            elapsed_ms=elapsed_ms,
            events=events,
            chunk_count=chunk_count,
            response_text="".join(content_parts),
        )
        if error_message is not None:
            yield (
                _serialize_sse_event(
                    "error",
                    {"code": "analysis_stream_failed", "message": error_message},
                ),
            )
        yield _serialize_sse_event("analysis_done", done_payload)
        return

    response_text = "".join(content_parts)
    logit_lens, attention, saliency = await asyncio.gather(
        _collect_logit_lens_payload_safe(
            prompt=prompt,
            response_text=response_text,
        ),
        _collect_attention_payload_safe(prompt=prompt),
        _collect_saliency_payload_safe(
            prompt=prompt,
            response_text=response_text,
        ),
    )
    stream_payload = {
        "response_text": "".join(content_parts),
        "chunk_count": chunk_count,
        "events": events,
        "first_content_at_ms": first_content_at_ms,
        "content_event_times_ms": content_event_times_ms,
    }
    (
        analysis_payload,
        refreshed_snapshot,
        _snapshot_after_at_ms,
    ) = await _finalize_completed_analysis(
        _FinalizeCompletedAnalysisArgs(
            prompt=prompt,
            snapshot=snapshot,
            runtime=runtime,
            stream_payload=stream_payload,
            request_id=request_id,
            flow_started_at=flow_started_at,
            request_ready_at_ms=request_ready_at_ms,
            response_received_at_ms=response_received_at_ms,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            logit_lens=logit_lens,
            attention=attention,
            saliency=saliency,
            model_manager=model_manager,
            settings=settings,
        )
    )
    final_result = {
        "analysis_enabled": True,
        "status": "completed",
        "snapshot": snapshot,
        "snapshot_after": refreshed_snapshot,
        "analysis": analysis_payload,
    }
    yield _serialize_sse_event("analysis_done", final_result)


async def analyze_model_with_optional_live_run(
    *,
    prompt: str,
    live_analysis_enabled: bool = False,
    max_tokens: int | None = 128,
    temperature: float | None = 0.2,
    top_p: float | None = None,
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
        skipped_result = _build_skipped_analysis_result(prompt, runtime)
        skipped_result["snapshot"] = snapshot
        return skipped_result

    if not prompt.strip():
        raise ValueError("prompt cannot be empty")

    drift_issue = _extract_model_drift_issue(snapshot)
    if drift_issue is not None:
        request_ready_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
        skipped_result = _build_model_drift_skipped_result(
            prompt=prompt,
            runtime=runtime,
            request_ready_at_ms=request_ready_at_ms,
            drift_issue=drift_issue,
        )
        skipped_result["snapshot"] = snapshot
        return skipped_result

    request = SimpleChatRequest(
        content=prompt,
        model=runtime["model"],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )
    request_ready_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
    result: dict[str, Any] = {
        "analysis_enabled": True,
        "status": "running",
        "snapshot": snapshot,
        "analysis": None,
    }
    try:
        response = await stream_simple_chat(request)
    except Exception as exc:
        degraded_details = _resolve_degraded_error_details(exc)
        if degraded_details is not None:
            error_code, detail = degraded_details
            elapsed_ms = (time.perf_counter() - flow_started_at) * 1000.0
            skipped_result = _build_degraded_mode_skipped_result(
                prompt=prompt,
                runtime=runtime,
                request_ready_at_ms=request_ready_at_ms,
                elapsed_ms=elapsed_ms,
                error_code=error_code,
                detail=detail,
            )
            skipped_result["snapshot"] = snapshot
            return skipped_result
        raise
    request_id = _parse_request_id(_get_response_header(response, "X-Request-Id"))
    response_received_at_ms = (time.perf_counter() - flow_started_at) * 1000.0
    try:
        stream_payload = await _collect_streaming_response(response)
    except Exception as exc:
        degraded_details = _resolve_degraded_error_details(exc)
        if degraded_details is not None:
            error_code, detail = degraded_details
            elapsed_ms = (time.perf_counter() - flow_started_at) * 1000.0
            skipped_result = _build_degraded_mode_skipped_result(
                prompt=prompt,
                runtime=runtime,
                request_ready_at_ms=request_ready_at_ms,
                elapsed_ms=elapsed_ms,
                error_code=error_code,
                detail=detail,
            )
            skipped_result["snapshot"] = snapshot
            return skipped_result
        raise
    elapsed_ms = (time.perf_counter() - flow_started_at) * 1000.0
    response_text = str(stream_payload.get("response_text") or "")
    logit_lens, attention, saliency = await asyncio.gather(
        _collect_logit_lens_payload_safe(
            prompt=prompt,
            response_text=response_text,
        ),
        _collect_attention_payload_safe(prompt=prompt),
        _collect_saliency_payload_safe(
            prompt=prompt,
            response_text=response_text,
        ),
    )
    (
        analysis_payload,
        refreshed_snapshot,
        _snapshot_after_at_ms,
    ) = await _finalize_completed_analysis(
        _FinalizeCompletedAnalysisArgs(
            prompt=prompt,
            snapshot=snapshot,
            runtime=runtime,
            stream_payload=stream_payload,
            request_id=request_id,
            flow_started_at=flow_started_at,
            request_ready_at_ms=request_ready_at_ms,
            response_received_at_ms=response_received_at_ms,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            logit_lens=logit_lens,
            attention=attention,
            saliency=saliency,
            model_manager=model_manager,
            settings=settings,
        )
    )
    result.update(
        {
            "status": "completed",
            "snapshot_after": refreshed_snapshot,
            "analysis": analysis_payload,
        }
    )
    return result
