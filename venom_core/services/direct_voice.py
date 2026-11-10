"""Direct voice reuses the text chat service with connection-local history."""

from __future__ import annotations

import codecs

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
    parts: list[str] = []
    pending = ""
    size = 0
    completed = False
    decoder = codecs.getincrementaldecoder("utf-8")()
    iterator = response.body_iterator
    try:
        async for chunk in iterator:
            pending += chunk if isinstance(chunk, str) else decoder.decode(bytes(chunk))
            pending = pending.replace("\r\n", "\n")
            if len(pending) > MAX_HISTORY_RESPONSE_CHARS:
                raise RuntimeError("chat_history_response_limit")
            while "\n\n" in pending:
                packet, pending = pending.split("\n\n", 1)
                event = _parse_packet(packet)
                if event is None:
                    continue
                kind, value = event
                if kind == "error":
                    raise RuntimeError("direct_voice_generation_failed")
                if kind == "content":
                    text = value.get("text")
                    if not isinstance(text, str):
                        raise RuntimeError("direct_voice_invalid_response")
                    size += len(text)
                    if size > MAX_HISTORY_RESPONSE_CHARS:
                        raise RuntimeError("chat_history_response_limit")
                    parts.append(text)
                if kind == "done":
                    completed = True
        answer = "".join(parts)
        if not completed or not answer.strip():
            raise RuntimeError("direct_voice_incomplete_response")
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
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
