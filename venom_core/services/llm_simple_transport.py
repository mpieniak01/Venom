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
    """An HTTP200 stream explicitly failed; it cannot complete successfully."""


def httpx_module() -> Any:
    return httpx


@asynccontextmanager
async def open_stream_response(
    *,
    provider_name: str,
    completions_url: str,
    payload: dict[str, Any],
) -> AsyncIterator[Any]:
    async with TrafficControlledHttpClient(
        provider=provider_name, timeout=None
    ) as client:
        async with client.astream(
            "POST",
            completions_url,
            json=payload,
            disable_retry=True,
        ) as response:
            yield response


async def iter_stream_packets(resp: Any) -> AsyncIterator[dict[str, Any]]:
    async for line in resp.aiter_lines():
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        if not data:
            continue
        try:
            packet = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(packet, dict):
            if packet.get("error") is not None:
                # Error bodies can contain private provider/conversation details.
                # Fail the stream without echoing that untrusted payload.
                raise UpstreamStreamError("upstream_stream_error")
            yield packet


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
