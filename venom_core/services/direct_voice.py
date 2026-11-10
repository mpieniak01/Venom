"""Direct voice reuses the text chat service with connection-local history."""

from __future__ import annotations

import codecs
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from venom_core.api.schemas.llm_simple import (
    MAX_CHAT_HISTORY_CHARS,
    HistoryMessage,
    SimpleChatRequest,
)
from venom_core.services.chat_history import MAX_HISTORY_RESPONSE_CHARS, _parse_packet
from venom_core.services.llm_simple_service import stream_simple_chat


async def complete_direct_turn(
    content: str, history: list[HistoryMessage], *, session_id: str
) -> tuple[str, list[HistoryMessage]]:
    """Perform one normal Direct request; preserve prior messages verbatim."""
    response = await stream_simple_chat(
        SimpleChatRequest(
            content=content,
            history=history,
            stream=False,
            session_id=session_id,
        )
    )
    answer = await _collect_direct_answer(response.body_iterator)
    if len(content) + len(answer) > MAX_CHAT_HISTORY_CHARS:
        return answer, []
    updated = [
        *history,
        HistoryMessage(role="user", content=content),
        HistoryMessage(role="assistant", content=answer),
    ]
    # Bound complete turns only, as in text chat; no content-based filtering.
    while (
        len(updated) > 20
        or sum(len(turn.content) for turn in updated) > MAX_CHAT_HISTORY_CHARS
    ):
        updated = updated[2:]
    return answer, updated


async def _direct_events(
    chunks: AsyncIterable[str | bytes | memoryview],
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    pending = ""
    decoder = codecs.getincrementaldecoder("utf-8")()
    async for chunk in chunks:
        pending += chunk if isinstance(chunk, str) else decoder.decode(bytes(chunk))
        pending = pending.replace("\r\n", "\n")
        if len(pending) > MAX_HISTORY_RESPONSE_CHARS:
            raise RuntimeError("chat_history_response_limit")
        while "\n\n" in pending:
            packet, pending = pending.split("\n\n", 1)
            event = _parse_packet(packet)
            if event is not None:
                yield event


async def _collect_direct_answer(
    chunks: AsyncIterable[str | bytes | memoryview],
) -> str:
    parts: list[str] = []
    size = 0
    completed = False
    iterator = aiter(chunks)
    try:
        async for kind, value in _direct_events(iterator):
            if kind == "error":
                raise RuntimeError("direct_voice_generation_failed")
            if kind == "done":
                completed = True
            if kind != "content":
                continue
            text = value.get("text")
            if not isinstance(text, str):
                raise RuntimeError("direct_voice_invalid_response")
            size += len(text)
            if size > MAX_HISTORY_RESPONSE_CHARS:
                raise RuntimeError("chat_history_response_limit")
            parts.append(text)
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
    answer = "".join(parts)
    if not completed or not answer.strip():
        raise RuntimeError("direct_voice_incomplete_response")
    return answer
