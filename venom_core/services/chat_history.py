"""Observe the existing Direct stream and persist to the host SessionStore."""

from __future__ import annotations

import asyncio
import codecs
import json
from collections.abc import AsyncIterable
from typing import Any
from uuid import UUID, uuid4

from fastapi.responses import StreamingResponse

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.services.background_priority import run_drainable_thread
from venom_core.services.session_store import SessionStore
from venom_core.utils.helpers import get_utc_now_iso

MAX_HISTORY_RESPONSE_CHARS = 1000000
_COST_FIELDS = {
    "estimated_usd",
    "reserved_usd",
    "reported_usd",
    "state",
    "currency",
    "conversation_reported_usd",
    "conversation_reserved_usd",
    "conversation_state",
}


class DirectHistory:
    """Per-response observer; references and original text are never expanded here."""

    def __init__(
        self,
        request: SimpleChatRequest,
        request_id: str,
        store: SessionStore,
        *,
        public_source_evidence: dict[str, str] | None = None,
    ):
        self.session = request.session_id or ""
        self.request_id = request_id
        self.user_content = request.content
        self.material_ids = list(request.material_ids)
        self.mode = "studio_normal" if request.studio_normal else "direct"
        self.started_at = get_utc_now_iso()
        self.store = store
        self.parts: list[str] = []
        self.text_length = 0
        self.pending = ""
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.started = False
        self.recorded = False
        self.terminal = False
        self.length_limited = False
        self.cost: dict[str, Any] | None = None
        self.model_identity: dict[str, str] | None = None
        self.tool_result: dict[str, Any] | None = None
        self.public_source_evidence = public_source_evidence

    def feed(self, chunk: str | bytes | memoryview) -> str | None:
        text = chunk if isinstance(chunk, str) else self.decoder.decode(bytes(chunk))
        self.pending += text.replace("\r\n", "\n")
        if len(self.pending) > MAX_HISTORY_RESPONSE_CHARS:
            raise ValueError("chat_history_response_limit")
        terminal = None
        while "\n\n" in self.pending:
            packet, self.pending = self.pending.split("\n\n", 1)
            parsed = _parse_packet(packet)
            if parsed is not None:
                terminal = self._observe(*parsed) or terminal
        return terminal

    def _observe(self, kind: str, value: dict[str, Any]) -> str | None:
        identity = value.get("model_identity")
        if (
            isinstance(identity, dict)
            and identity.get("runtime") == "omni-native-peft-text"
        ):
            self.model_identity = {
                key: identity[key]
                for key in (
                    "runtime",
                    "runtime_id",
                    "adapter_id",
                    "model",
                    "revision",
                    "snapshot_sha256",
                    "config_sha256",
                    "weights_sha256",
                    "response_source",
                )
                if isinstance(identity.get(key), str) and len(identity[key]) <= 256
            }
            if kind == "done" and identity.get("response_source") == "calculator":
                self.tool_result = _calculator_snapshot(identity.get("tool_result"))
        charge = value if kind == "cost" else value.get("cost")
        if isinstance(charge, dict):
            self.cost = _cost_snapshot(charge)
        if kind == "start":
            self.started = True
        elif kind == "content":
            self._content(value.get("text"))
        elif kind in {"done", "error"}:
            self.terminal = True
            self.length_limited = (
                self.mode == "studio_normal"
                and kind == "done"
                and value.get("finish_reason") == "length"
            )
            return "COMPLETED" if kind == "done" else "FAILED"
        return None

    def _content(self, text: Any) -> None:
        if not isinstance(text, str):
            return
        self.started = True
        self.text_length += len(text)
        if self.text_length > MAX_HISTORY_RESPONSE_CHARS:
            raise ValueError("chat_history_response_limit")
        self.parts.append(text)

    async def persist(self, status: str) -> None:
        if self.recorded or (status != "COMPLETED" and not self.started):
            return
        now = get_utc_now_iso()
        common: dict[str, object] = {
            "session_id": self.session,
            "request_id": self.request_id,
            "status": status,
            "mode": self.mode,
        }
        user = {
            **common,
            "role": "user",
            "content": self.user_content,
            "material_ids": self.material_ids,
            "timestamp": self.started_at,
        }
        assistant = {
            **common,
            "role": "assistant",
            "content": "".join(self.parts),
            "timestamp": now,
        }
        if self.length_limited:
            assistant["finish_reason"] = "length"
        if self.model_identity is not None:
            assistant["model_identity"] = dict(self.model_identity)
        if self.cost is not None:
            assistant["cost"] = dict(self.cost)
        if status == "COMPLETED" and self.tool_result is not None:
            assistant["tool_result"] = dict(self.tool_result)
        if (
            self.mode == "studio_normal"
            and status == "COMPLETED"
            and not self.length_limited
            and self.text_length > 0
            and self.public_source_evidence is not None
        ):
            assistant["public_source_evidence"] = dict(self.public_source_evidence)
        # Pass frozen payloads to the existing drainable I/O helper. Repeated
        # caller cancellation cannot abandon a disk worker or mutate a new turn.
        await run_drainable_thread(
            self.store.append_turn_once,
            self.session,
            self.request_id,
            [user, assistant],
        )
        self.recorded = True


def _parse_packet(packet: str) -> tuple[str, dict[str, Any]] | None:
    lines = packet.split("\n")
    kind = next(
        (line[6:].strip() for line in lines if line.startswith("event:")), "message"
    )
    raw = "\n".join(line[5:].lstrip() for line in lines if line.startswith("data:"))
    try:
        value = json.loads(raw) if raw else {}
    except ValueError:
        return None
    return (kind, value) if isinstance(value, dict) else None


def _calculator_snapshot(receipt: Any) -> dict[str, Any] | None:
    if not isinstance(receipt, dict) or receipt.get("tool") != "calculator":
        return None
    status = receipt.get("status")
    value, unit = receipt.get("value"), receipt.get("unit")
    recomputed = receipt.get("recomputed")
    if (
        status not in ("succeeded", "missing_expression", "invalid_expression")
        or (value is not None and (not isinstance(value, str) or len(value) > 160))
        or (status == "succeeded") != (value is not None)
        or (unit is not None and (not isinstance(unit, str) or len(unit) > 16))
        or not isinstance(recomputed, bool)
    ):
        return None
    return {
        "tool": "calculator",
        "status": status,
        "value": value,
        "unit": unit,
        "recomputed": recomputed,
    }


def _cost_snapshot(charge: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in charge.items()
        if key in _COST_FIELDS and (item is None or isinstance(item, (str, int, float)))
    }


def _history_error(code: str, cost: dict[str, Any] | None) -> str:
    details: dict[str, Any] = {"code": code}
    if cost is not None:
        details["cost"] = cost
    return "event: error\ndata: " + json.dumps(details) + "\n\n"


async def _stream_history(source: AsyncIterable[Any], history: DirectHistory):
    iterator = aiter(source)
    try:
        async for chunk in iterator:
            status = history.feed(chunk)
            if status is not None:
                # Mark an authoritative terminal event before the save. If this
                # await is cancelled, an upstream completion never becomes a
                # fabricated CANCELLED turn or a second accounting decision.
                await history.persist(status)
            yield chunk
        if not history.terminal and history.started:
            history.terminal = True
            await history.persist("FAILED")
            yield _history_error("chat_stream_incomplete", history.cost)
    except (asyncio.CancelledError, GeneratorExit):
        if not history.terminal:
            # Drain the same bounded persistence worker before propagating Stop;
            # accounting metadata remains exactly what the provider reported.
            await history.persist("CANCELLED")
        raise
    except (OSError, ValueError, TypeError):
        history.terminal = True
        yield _history_error("chat_history_persistence_failed", history.cost)
    finally:
        close = getattr(iterator, "aclose", None)
        if callable(close):
            await close()


def persist_direct_response(
    response: StreamingResponse,
    request: SimpleChatRequest,
    store: SessionStore | None,
    *,
    public_source_evidence: dict[str, str] | None = None,
) -> StreamingResponse:
    """Keep the actual stream/budget lifecycle and inject no independent store."""
    if not request.session_id or store is None:
        return response
    request_id = response.headers.get("X-Request-Id", "")
    try:
        UUID(request_id)
    except ValueError:
        request_id = str(uuid4())
        response.headers["X-Request-Id"] = request_id
    history = DirectHistory(
        request, request_id, store, public_source_evidence=public_source_evidence
    )
    response.body_iterator = _stream_history(response.body_iterator, history)
    return response
