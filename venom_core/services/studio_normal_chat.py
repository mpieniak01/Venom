"""Prepare the lightweight Studio Normal stream from persisted chat and notes."""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException

from venom_core.api.schemas.llm_simple import (
    MAX_CHAT_MESSAGE_CHARS,
    HistoryMessage,
    SimpleChatRequest,
)
from venom_core.config import DEFAULT_SIMPLE_MODE_SYSTEM_PROMPT, SETTINGS
from venom_core.memory.chat_retrieval import (
    CHAT_NOTE_POLICY,
    CHAT_NOTES_DISABLED_POLICY,
    note_request_language,
    retrieve_chat_memory,
)
from venom_core.services.background_priority import run_drainable_thread
from venom_core.services.session_store import SessionStore

_NORMAL_HISTORY_POLICY = (
    "Use the conversation history to answer follow-up questions. "
    "Prefer the latest user correction."
)
_NORMAL_LANGUAGE_POLICY = (
    "Answer in the language of the current question unless another language "
    "was requested."
)


def _recent_turns(
    store: SessionStore, session_id: str, budget: int
) -> list[HistoryMessage]:
    history = store.get_history(session_id)
    result: list[HistoryMessage] = []
    end = len(history)
    while end > 1:
        user, assistant = history[end - 2 : end]
        if (
            user.get("role") != "user"
            or assistant.get("role") != "assistant"
            or user.get("request_id") != assistant.get("request_id")
            or assistant.get("status") not in {None, "COMPLETED"}
        ):
            end -= 1
            continue
        end -= 2
        prompt, reply = user.get("content"), assistant.get("content")
        if (
            not isinstance(prompt, str)
            or not isinstance(reply, str)
            or not prompt
            or not reply
            or max(len(prompt), len(reply)) > MAX_CHAT_MESSAGE_CHARS
        ):
            continue
        cost = len(prompt) + len(reply) + 64
        if cost > budget:
            break
        budget -= cost
        result.extend(
            (
                HistoryMessage(role="assistant", content=reply),
                HistoryMessage(role="user", content=prompt),
            )
        )
    result.reverse()
    return result


async def _note_context(
    request: SimpleChatRequest,
    session_id: str,
    get_vector_store: Callable[[], Awaitable[Any]],
) -> str:
    system_context = ""
    note_language = note_request_language(request.content)
    if request.use_notes and SETTINGS.CHAT_NOTES_ENABLED:
        vector_store = await get_vector_store()
        notes, _ = await run_drainable_thread(
            retrieve_chat_memory, vector_store, request.content, session_id
        )
        system_context += (
            f"\n\n{CHAT_NOTE_POLICY}\n\n[NOTES]\n{notes or '(no matching source)'}"
            "\n[/NOTES]"
        )
        if note_language:
            system_context += (
                f"\nWrite the answer in {note_language}, even if the notes "
                "use another language. Keep names and codes as written."
            )
    elif note_language:
        system_context += f"\n\n{CHAT_NOTES_DISABLED_POLICY}"
    return system_context


async def prepare_studio_normal(
    request: SimpleChatRequest,
    store: SessionStore | None,
    get_vector_store: Callable[[], Awaitable[Any]],
) -> tuple[SimpleChatRequest, str]:
    """Build a single prompt with history and retrieve notes only when requested."""
    session_id = request.session_id
    if not store or not session_id:
        raise HTTPException(400, "studio_normal_requires_session")
    if request.material_ids or request.tools or request.tool_choice:
        raise HTTPException(400, "studio_normal_text_only")

    num_ctx = SETTINGS.OLLAMA_CONTEXT_LENGTH or 4096
    output_tokens = min(max(1, request.max_tokens or 256), max(1, num_ctx // 4))
    # Reserve room for role framing and use a conservative multilingual char budget.
    budget = max(0, (num_ctx - output_tokens - 128) * 2)
    configured_prompt = (SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT or "").strip()
    use_default_language = configured_prompt in {"", DEFAULT_SIMPLE_MODE_SYSTEM_PROMPT}
    if use_default_language:
        configured_prompt = ""
    budget -= len(request.content) + len(configured_prompt) + 64
    if budget < 0:
        raise HTTPException(413, {"reason_code": "studio_normal_context_limit"})

    system_context = _NORMAL_HISTORY_POLICY
    if use_default_language:
        system_context += f" {_NORMAL_LANGUAGE_POLICY}"
    system_context += await _note_context(request, session_id, get_vector_store)
    budget -= len(system_context)
    if budget < 0:
        raise HTTPException(413, {"reason_code": "studio_normal_context_limit"})
    return request.model_copy(
        update={
            "history": _recent_turns(store, session_id, budget),
            "max_tokens": output_tokens,
            "think": False,
        }
    ), system_context
