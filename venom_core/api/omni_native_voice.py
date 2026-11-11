"""Shared transport state for the experimental native Omni voice turn."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException, Request

from venom_core.services import omni_native_dialogue
from venom_core.services.background_priority import run_drainable_thread
from venom_core.services.model_resources import model_operation
from venom_core.services.omni_native_dialogue import (
    NATIVE_MODES,
    NativeDialogueError,
    NativeDialogueResult,
    NativeMode,
)
from venom_core.services.runtime_switch_gate import runtime_request_guard
from venom_core.services.session_store import SessionRevision, SessionStore
from venom_core.utils.helpers import get_utc_now_iso
from venom_core.utils.llm_runtime import LLMRuntimeInfo, get_active_llm_runtime

MODES = NATIVE_MODES
PILOT_AUDIO_FORMATS = {
    "audio/webm": "matroska",
    "audio/ogg": "ogg",
    "audio/mp4": "mov",
}
PIPELINE = "omni_native_dialogue"
_CONTEXT_TTL_SECONDS = 300
_MAX_CACHED_SESSIONS = 16
_MAX_HISTORY_PCM_BYTES = 1024 * 1024
_MAX_TEXT_CHARS = 2000


def parse_mode(value: object) -> NativeMode | None:
    """Validate an explicit mode without treating unknown values as cascade."""
    if value is None:
        return None
    if value == "interleaved":
        return "interleaved"
    if value == "audio":
        return "audio"
    raise HTTPException(422, {"reason_code": "omni_native_invalid_input"})


@dataclass(slots=True)
class _Context:
    runtime: LLMRuntimeInfo
    image: bytes | None
    history: list[dict[str, object]]
    expiration: asyncio.TimerHandle
    request_id: str


class NativeTurnContexts:
    """Retain one completed turn and one active image per session in memory."""

    def __init__(self) -> None:
        self._sessions: OrderedDict[Hashable, _Context] = OrderedDict()
        self._active: set[Hashable] = set()

    @contextmanager
    def turn(self, key: Hashable) -> Iterator[None]:
        if key in self._active:
            raise HTTPException(409, {"reason_code": "omni_native_busy"})
        self._active.add(key)
        try:
            yield
        finally:
            self._active.discard(key)

    def discard(self, key: Hashable) -> None:
        entry = self._sessions.pop(key, None)
        if entry is not None:
            entry.expiration.cancel()

    def inputs(
        self,
        key: Hashable,
        runtime: LLMRuntimeInfo,
        mode: NativeMode,
        image: bytes | None,
        rows: list[dict[str, object]],
    ) -> tuple[bytes | None, list[dict[str, object]], str | None]:
        if mode == "audio":
            self.discard(key)
            return image, [], None
        entry = self._sessions.get(key)
        if entry is None:
            return image, [], None
        if entry.runtime != runtime or not any(
            row.get("request_id") == entry.request_id for row in rows
        ):
            self.discard(key)
            return image, [], None
        return (
            image if image is not None else entry.image,
            list(entry.history),
            entry.request_id,
        )

    def remember(
        self,
        key: Hashable,
        runtime: LLMRuntimeInfo,
        image: bytes | None,
        pcm: bytes,
        sample_rate: int,
        text: str,
        *,
        request_id: str,
    ) -> None:
        self.discard(key)
        if len(self._sessions) >= _MAX_CACHED_SESSIONS:
            self.discard(next(iter(self._sessions)))
        history: list[dict[str, object]] = []
        if len(pcm) <= _MAX_HISTORY_PCM_BYTES:
            history = [
                {"role": "user", "pcm": pcm, "sample_rate": sample_rate},
                {"role": "assistant", "content": text[:_MAX_TEXT_CHARS]},
            ]
        expiration = asyncio.get_running_loop().call_later(
            _CONTEXT_TTL_SECONDS, self.discard, key
        )
        self._sessions[key] = _Context(runtime, image, history, expiration, request_id)


def text_context(
    rows: list[dict[str, object]],
    retained: list[dict[str, object]],
    request_id: str | None,
) -> list[dict[str, object]]:
    """Restore the RAM-only native turn at its position in the session log."""
    history: list[dict[str, object]] = []
    for row in rows:
        role, content = row.get("role"), row.get("content")
        if row.get("mode") == PIPELINE:
            if (
                role == "assistant"
                and request_id
                and row.get("request_id") == request_id
            ):
                history.extend(retained)
            continue
        if (
            role in ("user", "assistant")
            and isinstance(content, str)
            and content.strip()
        ):
            history.append({"role": role, "content": content[:_MAX_TEXT_CHARS]})
    return history


async def persist_turn(
    store: SessionStore,
    session_id: str,
    mode: NativeMode,
    text: str | None,
    *,
    expected_revision: SessionRevision,
) -> str:
    request_id = str(uuid4())
    metadata = {
        "session_id": session_id,
        "request_id": request_id,
        "timestamp": get_utc_now_iso(),
        "status": "COMPLETED",
        "mode": PIPELINE,
        "generation_mode": mode,
    }
    saved = await run_drainable_thread(
        store.append_turn_once,
        session_id,
        request_id,
        [
            {**metadata, "role": "user", "content": "[Nagranie głosowe]"},
            {
                **metadata,
                "role": "assistant",
                "content": text or "[Odpowiedź głosowa]",
            },
        ],
        expected_revision=expected_revision,
    )
    if not saved:
        raise HTTPException(409, {"reason_code": "omni_native_session_cleared"})
    return request_id


def error_code(error: HTTPException) -> str:
    if isinstance(error.detail, dict):
        reason = error.detail.get("reason_code")
        if isinstance(reason, str):
            return reason
    return "omni_native_busy" if error.status_code == 409 else "omni_native_failed"


async def wait_for_disconnect(request: Request) -> None:
    """Wait for ASGI to report that a fully uploaded request lost its client."""
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            return


@model_operation
async def run_turn(
    runtime: LLMRuntimeInfo,
    pcm: bytes,
    sample_rate: int,
    image: bytes | None,
    history: list[dict[str, object]],
    mode: NativeMode,
) -> NativeDialogueResult:
    """Keep model switching and release blocked until the generator has stopped."""
    failure: BaseException
    async with runtime_request_guard(
        request_kind=PIPELINE, provider=runtime.provider, model=runtime.model_name
    ):
        if get_active_llm_runtime() != runtime:
            failure = HTTPException(409, {"reason_code": "omni_native_runtime_changed"})
        else:
            try:
                return await omni_native_dialogue.generate_native_turn(
                    runtime, pcm, sample_rate, image, history, mode=mode
                )
            except (NativeDialogueError, asyncio.CancelledError) as exc:
                # The native adapter drains or terminates its worker before raising.
                failure = exc
    raise failure
