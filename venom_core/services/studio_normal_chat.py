"""Prepare the lightweight Studio Normal stream from persisted chat and notes."""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException

from venom_core.api.schemas.llm_simple import (
    MAX_CHAT_HISTORY_CHARS,
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
from venom_core.services.academy.qualified_chat import GENERATION_TRUNCATED
from venom_core.services.academy.qualified_chat_explanations import changes_example
from venom_core.services.academy.qualified_chat_revisions import (
    public_lookup_query,
    source_revision_hint,
    without_previous_links,
)
from venom_core.services.background_priority import run_drainable_thread
from venom_core.services.chat_grounding import (
    PUBLIC_SOURCE_BLOCK,
    PublicSourceUnavailable,
    current_chat_context,
    grounding_follow_up,
    is_current_news_request,
)
from venom_core.services.session_store import SessionStore

_NORMAL_HISTORY_POLICY = (
    "Use the conversation history to answer follow-up questions. "
    "Prefer the latest user correction."
)
_NORMAL_LANGUAGE_POLICY = (
    "Answer in the language of the current question unless another language "
    "was requested."
)


_RETRIEVED_SOURCE_POLICY = (
    "\n\nAplikacja pozyskała poniższy fragment po rozstrzygnięciu zgody na "
    "wyszukiwanie. Zacznij od konkretnej odpowiedzi z fragmentu i podaj właściwy "
    "odnośnik. Przy pytaniu o fakt pomiń komentarz o zgodzie i wyszukiwaniu. "
    "Jeżeli szukanej informacji nie ma we fragmencie, nazwij brakujące pole."
)
_SHORT_SOURCE_POLICY = (
    " Przy krótkiej odpowiedzi podaj tylko żądane fakty i pełny URL źródła. "
    "Użyj zdania źródła, które dotyczy dokładnie pytanego faktu. "
    "Pomiń wstęp, powtarzane przypisy i czas odczytu, jeśli o niego nie proszono."
)
_SOURCE_STATUS_POLICY = (
    "\n\nPoniższy status pochodzi z aplikacji. Przekaż go własnymi słowami "
    "w języku pytania, po polsku przy polskim pytaniu. Jeśli odczyt nie "
    "powiódł się w tej turze, powiedz, że nie udało się uzyskać źródła. "
    "Nie dopisuj danych, odnośników ani ograniczeń funkcji wyszukiwania."
)


def _recent_turns(
    store: SessionStore,
    session_id: str,
    budget: int,
    *,
    omit_truncated: bool = False,
    omit_assistant_links: bool = False,
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
    remaining = budget - len(system_context)
    omit_truncated = (
        SETTINGS.ACADEMY_QUALIFIED_CHAT_ENABLED
        and not request.use_notes
        and changes_example(request.content)
    )
    local_qualification = (
        SETTINGS.ACADEMY_QUALIFIED_CHAT_ENABLED and not request.use_notes
    )
    supplied_update = local_qualification and bool(
        source_revision_hint(request.content)
    )
    omit_assistant_links = (
        supplied_update and public_lookup_query(request.content) is None
    )
    history = _recent_turns(
        store,
        session_id,
        max(0, min(remaining, MAX_CHAT_HISTORY_CHARS)),
        omit_truncated=omit_truncated,
        omit_assistant_links=omit_assistant_links,
    )
    previous = next(
        (turn.content for turn in reversed(history) if turn.role == "user"), ""
    )
    query = grounding_follow_up(request.content, previous)
    if local_qualification:
        query = (
            None
            if source_revision_hint(request.content)
            else public_lookup_query(query)
        )
    source_context = (
        ""
        if query is None
        else await current_chat_context(query, use_notes=request.use_notes)
    )
    if local_qualification and source_context:
        if isinstance(source_context, PublicSourceUnavailable):
            source_context = "\nW tej turze nie udało się odczytać publicznego źródła."
        policy = _SOURCE_STATUS_POLICY
        if source_context.startswith(PUBLIC_SOURCE_BLOCK):
            policy = _RETRIEVED_SOURCE_POLICY
            if is_current_news_request(request.content):
                policy += (
                    " Przy odczycie nagłówka zacznij od «Nagłówek RSS». "
                    "Podaj nagłówek po polsku. Jeżeli wskazuje, kto powiedział, "
                    "poinformował lub ogłosił, podaj tę osobę lub instytucję "
                    "w osobnym polu «Atrybucja». Zachowaj tę informację także przy "
                    "tłumaczeniu końcówki «said» lub «says». "
                    "Dołącz pole «Data publikacji» z datą źródła i pole «Link» "
                    "z pełnym URL pozycji."
                )
            if output_tokens <= 128:
                policy += _SHORT_SOURCE_POLICY
        if len(policy) + 1 + len(source_context) <= remaining:
            source_context = f"{policy}\n{source_context}"
    if len(source_context) <= remaining:
        system_context += source_context
    elif source_context:
        fallback = "\nFresh source context did not fit; say it was not checked."
        if len(fallback) <= remaining:
            system_context += fallback
    budget -= len(system_context)
    if budget < 0:
        raise HTTPException(413, {"reason_code": "studio_normal_context_limit"})
    return request.model_copy(
        update={
            "history": _recent_turns(
                store,
                session_id,
                min(budget, MAX_CHAT_HISTORY_CHARS),
                omit_truncated=omit_truncated,
                omit_assistant_links=omit_assistant_links,
            ),
            "max_tokens": output_tokens,
            "think": False,
        }
    ), system_context
