"""Keep complete persisted chat turns within the prompt budget."""

from venom_core.api.schemas.llm_simple import MAX_CHAT_MESSAGE_CHARS, HistoryMessage
from venom_core.services.chat_policy.qualified_chat import GENERATION_TRUNCATED
from venom_core.services.chat_policy.qualified_chat_revisions import (
    without_previous_links,
)
from venom_core.services.session_store import SessionStore


def recent_turns(
    store: SessionStore,
    session_id: str,
    budget: int,
    *,
    omit_truncated: bool = False,
    omit_assistant_links: bool = False,
    user_facts_only: bool = False,
    history: list[dict[str, object]] | None = None,
) -> list[HistoryMessage]:
    if history is None:
        history = store.get_history(session_id)
    result: list[HistoryMessage] = []
    end = len(history)
    while end > 1:
        user, assistant = history[end - 2 : end]
        if not _completed_pair(user, assistant):
            end -= 1
            continue
        end -= 2
        contents = _history_pair_contents(user, assistant)
        if contents is None:
            continue
        prompt, reply = contents
        if user_facts_only:
            cost = len(prompt) + 32
            if cost > budget:
                break
            budget -= cost
            result.append(HistoryMessage(role="user", content=prompt))
            continue
        reply = _prepare_history_reply(
            reply,
            assistant,
            omit_truncated=omit_truncated,
            omit_assistant_links=omit_assistant_links,
        )
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


def _completed_pair(user: dict[str, object], assistant: dict[str, object]) -> bool:
    return (
        user.get("role") == "user"
        and assistant.get("role") == "assistant"
        and user.get("request_id") == assistant.get("request_id")
        and assistant.get("status") in {None, "COMPLETED"}
    )


def _history_pair_contents(
    user: dict[str, object], assistant: dict[str, object]
) -> tuple[str, str] | None:
    prompt, reply = user.get("content"), assistant.get("content")
    if (
        not isinstance(prompt, str)
        or not isinstance(reply, str)
        or not prompt
        or not reply
        or max(len(prompt), len(reply)) > MAX_CHAT_MESSAGE_CHARS
    ):
        return None
    return prompt, reply


def _prepare_history_reply(
    reply: str,
    assistant: dict[str, object],
    *,
    omit_truncated: bool,
    omit_assistant_links: bool,
) -> str:
    if omit_truncated and (
        assistant.get("finish_reason") == "length"
        or reply.endswith(f"\n\n{GENERATION_TRUNCATED}")
        or reply == GENERATION_TRUNCATED
    ):
        reply = "Poprzednia odpowiedź została przerwana przed zakończeniem."
    if omit_assistant_links:
        reply = (
            without_previous_links(reply)
            or "Poprzednia odpowiedź zawierała tylko odnośnik."
        )
    return reply
