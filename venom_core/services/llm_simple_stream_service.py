"""Streaming control-flow helpers for llm_simple route."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol


@dataclass
class SimpleStreamState:
    chunks: list[str]
    chunk_count: int = 0
    first_chunk_seen: bool = False
    retry_requested: bool = False
    failed: bool = False
    completed: bool = False


class RuntimeLike(Protocol):
    provider: str


def reset_stream_attempt_state(state: SimpleStreamState) -> None:
    state.retry_requested = False
    state.failed = False
    state.completed = False


def apply_post_attempt_action(action: str) -> tuple[bool, bool]:
    if action == "retry":
        return True, False
    if action == "done":
        return False, True
    return False, False


def resolve_post_attempt_action(
    *,
    state: SimpleStreamState,
    finalize_success_fn: Callable[[], None],
) -> str:
    if state.retry_requested:
        return "retry"
    if state.failed:
        return "stop"
    if not state.completed:
        return "retry"
    finalize_success_fn()
    return "done"


def update_stream_state_from_packet(
    *,
    packet: dict[str, Any],
    runtime: RuntimeLike,
    state: SimpleStreamState,
    ollama_telemetry: dict[str, int],
    extract_ollama_telemetry_fn: Callable[[dict[str, Any]], dict[str, int]],
    extract_sse_tool_calls_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
    extract_sse_contents_fn: Callable[[dict[str, Any]], list[str]],
    on_first_chunk_fn: Callable[[str], None],
) -> list[str]:
    emitted_events: list[str] = []
    if runtime.provider == "ollama":
        telemetry = extract_ollama_telemetry_fn(packet)
        if telemetry:
            ollama_telemetry.update(telemetry)

    tool_calls = extract_sse_tool_calls_fn(packet)
    if tool_calls:
        emitted_events.append(
            "event: tool_calls\ndata: "
            + json.dumps({"tool_calls": tool_calls})
            + "\n\n"
        )

    for content in extract_sse_contents_fn(packet):
        state.chunk_count += 1
        state.chunks.append(content)
        if not state.first_chunk_seen:
            on_first_chunk_fn(content)
            state.first_chunk_seen = True
        emitted_events.append(
            "event: content\ndata: " + json.dumps({"text": content}) + "\n\n"
        )

    return emitted_events


async def stream_single_attempt(
    *,
    open_stream_response_fn: Callable[..., Any],
    iter_stream_packets_fn: Callable[[Any], Any],
    completions_url: str,
    payload: dict[str, Any],
    provider_name: str,
    state: SimpleStreamState,
    http_status_error_type: type[Exception],
    attempt: int,
    max_attempts: int,
    is_retryable_status_fn: Callable[[int | None], bool],
    runtime_provider: str,
    retry_backoff: float,
    sleep_fn: Callable[[float], Awaitable[None]],
    handle_packet_fn: Callable[[dict[str, Any]], list[str]],
    emit_http_error_fn: Callable[[Exception], Awaitable[str]],
) -> AsyncIterator[str]:
    try:
        async with open_stream_response_fn(
            provider_name=provider_name,
            completions_url=completions_url,
            payload=payload,
        ) as resp:
            async for packet in iter_stream_packets_fn(resp):
                for event in handle_packet_fn(packet):
                    yield event
    except http_status_error_type as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if (
            state.chunk_count == 0
            and attempt < max_attempts
            and is_retryable_status_fn(status_code)
            and runtime_provider == "ollama"
        ):
            state.retry_requested = True
            await sleep_fn(retry_backoff * attempt)
            return
        state.failed = True
        yield await emit_http_error_fn(exc)
        return

    state.completed = True
