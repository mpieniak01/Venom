"""HTTP transport adapter for llm_simple streaming route."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx

from venom_core.infrastructure.traffic_control.http_client import (
    TrafficControlledHttpClient,
)


class UpstreamStreamError(RuntimeError):
    """An upstream stream failed or ended without explicit generation completion."""


def httpx_module() -> Any:
    return httpx


@asynccontextmanager
async def open_stream_response(
    *,
    provider_name: str,
    completions_url: str,
    payload: dict[str, Any],
) -> AsyncIterator[Any]:
    async with (
        TrafficControlledHttpClient(provider=provider_name, timeout=None) as client,
        client.astream(
            "POST",
            completions_url,
            json=payload,
            disable_retry=True,
        ) as response,
    ):
        yield response


def _packet_finishes_generation(packet: dict[str, Any]) -> bool:
    choices = packet.get("choices")
    if not isinstance(choices, list):
        return False
    completed = False
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        reason = choice.get("finish_reason")
        if not isinstance(reason, str):
            continue
        reason = reason.strip().lower()
        if reason in {"abort", "error"}:
            raise UpstreamStreamError("upstream_generation_failed")
        completed = completed or bool(reason)
    return completed


def _decode_stream_packet(data: str) -> dict[str, Any] | None:
    try:
        packet = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(packet, dict):
        return None
    if packet.get("error") is not None:
        # Never expose private provider/conversation details from an error body.
        raise UpstreamStreamError("upstream_stream_error")
    return packet


async def iter_stream_packets(resp: Any) -> AsyncIterator[dict[str, Any]]:
    completed = False
    async for line in resp.aiter_lines():
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        if not data:
            continue
        packet = _decode_stream_packet(data)
        if packet is not None:
            completed = _packet_finishes_generation(packet) or completed
            yield packet
    # Clean TCP EOF alone must never become a successful DONE.
    if not completed:
        raise UpstreamStreamError("upstream_stream_incomplete")


async def read_http_error_response_text(response: Any | None) -> str:
    if response is None:
        return ""
    try:
        body = await response.aread()
    except Exception:
        return ""
    if not body:
        return ""
    encoding = getattr(response, "encoding", None) or "utf-8"
    return body.decode(encoding, errors="replace")
