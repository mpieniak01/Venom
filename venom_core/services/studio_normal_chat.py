"""Prepare the lightweight Studio Normal stream from persisted chat and notes."""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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
from venom_core.services.academy.qualified_chat_quote import without_quotes
from venom_core.services.academy.qualified_chat_revisions import (
    explicit_lookup_allowed,
    lookup_forbidden,
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
    is_rss_read_request,
    rss_editorial_query,
)
from venom_core.services.public_source_evidence import (
    PublicSourceContext,
    PublicSourceEvidence,
    asks_about_previous_scope,
    previous_public_fact_context,
    previous_scope_reply,
    previous_verified_fact_reply,
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
_SHORT_SOURCE_REQUEST = re.compile(
    r"\b(?:krótko|zwięźle|(?:jedno|dwa) krótkie zdani\w*|"
    r"w (?:jednym|dwóch)(?: krótkim| krótkich)? zdani\w*)\b",
    re.I,
)
_SHORT_SOURCE_POLICY = (
    " Przy krótkiej odpowiedzi podaj tylko żądane fakty i pełny URL źródła. "
    "Skopiuj pełny adres ze źródła zamiast samego numeru przypisu. "
    "Użyj zdania źródła, które dotyczy dokładnie pytanego faktu. "
    "Pomiń wstęp, powtarzane przypisy i czas odczytu, jeśli o niego nie proszono."
)
_SENTENCE_REQUEST = re.compile(
    r"\b(?:(?P<one>w\s+jednym(?:\s+krótkim)?\s+zdaniu|"
    r"do\s+jednego(?:\s+krótkiego)?\s+zdania|(?:jedno|1)(?:\s+krótkie)?\s+zdanie)"
    r"|w\s+dwóch(?:\s+krótkich)?\s+zdaniach|"
    r"do\s+dwóch(?:\s+krótkich)?\s+zdań|(?:dwa|2)(?:\s+krótkie)?\s+zdania)\b",
    re.I,
)
_DECIMAL_DOT_REQUEST = re.compile(r"\bkropk\w*\s+dziesiętn\w*\b", re.I)
_DECIMAL_DOT_POLICY = (
    " W liczbach dziesiętnych użyj kropki między cyframi. Wartość z polskim "
    "przecinkiem dziesiętnym przepisz z kropką zamiast przecinka, zachowując "
    "cyfry, jednostkę oraz pełny adres."
)
_WIKI_FACT_POLICY = (
    " Odpowiedz wprost na szczegółowe pytanie, zachowując wartość, jednostkę, "
    "przybliżenie i warunek, gdy występują w źródle. Podaj pełny adres właściwego "
    "hasła tylko raz, w nawiasie na końcu ostatniego zdania przed kropką."
)
_PROVIDED_INFORMATION_ONLY = re.compile(
    r"\b(?:tylko|wyłącznie|jedynie)\s+na podstawie\s+"
    r"(?:tej\s+rozmowy|podanych informacji|informacji,?\s+które\s+(?:podałem|podałam))\b",
    re.I,
)
_RSS_NOT_READ = "W tej turze nie odczytano nagłówków z publicznego kanału RSS."
_SOURCE_STATUS_POLICY = (
    "\n\nPoniższy status pochodzi z aplikacji. Przekaż go własnymi słowami "
    "w języku pytania, po polsku przy polskim pytaniu. Jeśli odczyt nie "
    "powiódł się w tej turze, powiedz, że nie udało się uzyskać źródła. "
    "Nie dopisuj danych, odnośników ani ograniczeń funkcji wyszukiwania."
)


@dataclass
class _NormalChatSetup:
    session_id: str
    output_tokens: int
    budget: int
    system_context: str
    remaining: int
    provided_information_only: bool
    omit_truncated: bool
    local_qualification: bool
    omit_assistant_links: bool
    history_records: list[dict[str, object]]
    history: list[HistoryMessage]


@dataclass
class _SourcePlan:
    query: str | None
    explicit_rss: bool
    scope_reply: str | None
    prior_context: str


def _wiki_sentence_policy(message: str) -> str:
    visible = without_quotes(message)
    matches = list(_SENTENCE_REQUEST.finditer(visible))
    if not matches:
        return ""
    limit = (
        " Napisz dokładnie jedno zdanie. Połącz pytany fakt i odnośnik w tym samym "
        "zdaniu. Pomiń osobną definicję hasła, jeżeli pytanie dotyczy konkretnej cechy."
        if matches[-1].group("one")
        else " Napisz dokładnie dwa zdania. W obu pozostań przy zakresie pytania."
    )
    decimal_format = _DECIMAL_DOT_POLICY if _DECIMAL_DOT_REQUEST.search(visible) else ""
    return limit + _WIKI_FACT_POLICY + decimal_format


def _recent_turns(
    store: SessionStore,
    session_id: str,
    budget: int,
    *,
    omit_truncated: bool = False,
    omit_assistant_links: bool = False,
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


def _previous_evidence(history: list[dict[str, object]]) -> PublicSourceEvidence | None:
    if len(history) < 2:
        return None
    user, assistant = history[-2:]
    if (
        user.get("role") != "user"
        or assistant.get("role") != "assistant"
        or not assistant.get("request_id")
        or user.get("request_id") != assistant.get("request_id")
        or assistant.get("status") != "COMPLETED"
        or assistant.get("finish_reason") == "length"
    ):
        return None
    return PublicSourceEvidence.from_record(assistant.get("public_source_evidence"))


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


async def _normal_chat_setup(
    request: SimpleChatRequest,
    store: SessionStore | None,
    get_vector_store: Callable[[], Awaitable[Any]],
) -> _NormalChatSetup:
    session_id = request.session_id
    if not store or not session_id:
        raise HTTPException(400, "studio_normal_requires_session")
    if request.material_ids or request.tools or request.tool_choice:
        raise HTTPException(400, "studio_normal_text_only")
    output_tokens, budget, use_default_language = _normal_context_budget(request)
    system_context = _NORMAL_HISTORY_POLICY
    if use_default_language:
        system_context += f" {_NORMAL_LANGUAGE_POLICY}"
    system_context += await _note_context(request, session_id, get_vector_store)
    system_context, provided_information_only = _provided_information_policy(
        request, system_context
    )
    remaining = budget - len(system_context)
    omit_truncated, local_qualification, omit_assistant_links = _normal_history_options(
        request
    )
    history_records = store.get_history(session_id)
    history = _recent_turns(
        store,
        session_id,
        max(0, min(remaining, MAX_CHAT_HISTORY_CHARS)),
        omit_truncated=omit_truncated,
        omit_assistant_links=omit_assistant_links,
        history=history_records,
    )
    return _NormalChatSetup(
        session_id,
        output_tokens,
        budget,
        system_context,
        remaining,
        provided_information_only,
        omit_truncated,
        local_qualification,
        omit_assistant_links,
        history_records,
        history,
    )


def _normal_context_budget(request: SimpleChatRequest) -> tuple[int, int, bool]:
    num_ctx = SETTINGS.OLLAMA_CONTEXT_LENGTH or 4096
    output_tokens = min(max(1, request.max_tokens or 256), max(1, num_ctx // 4))
    budget = max(0, (num_ctx - output_tokens - 128) * 2)
    configured_prompt = (SETTINGS.SIMPLE_MODE_SYSTEM_PROMPT or "").strip()
    use_default_language = configured_prompt in {"", DEFAULT_SIMPLE_MODE_SYSTEM_PROMPT}
    if use_default_language:
        configured_prompt = ""
    budget -= len(request.content) + len(configured_prompt) + 64
    if budget < 0:
        raise HTTPException(413, {"reason_code": "studio_normal_context_limit"})
    return output_tokens, budget, use_default_language


def _provided_information_policy(
    request: SimpleChatRequest, system_context: str
) -> tuple[str, bool]:
    provided_only = bool(
        SETTINGS.ACADEMY_QUALIFIED_CHAT_ENABLED
        and not request.use_notes
        and not explicit_lookup_allowed(request.content)
        and _PROVIDED_INFORMATION_ONLY.search(without_quotes(request.content))
    )
    if not provided_only:
        return system_context, False
    system_context += (
        " Korzystaj tylko z danych z rozmowy. Jeśli aktualnej wartości nie podano, "
        "powiedz wprost «W rozmowie nie podano tej informacji». "
        "Nie przypisuj sobie wypowiedzi użytkownika. "
        "Jeśli pytanie na końcu dotyczy jednej wartości, odpowiedz na nie wprost "
        "i nie streszczaj wcześniejszych porad."
    )
    format_request = _SENTENCE_REQUEST.search(without_quotes(request.content))
    if format_request and format_request.group("one"):
        system_context += (
            " Napisz dokładnie jedno zdanie odpowiadające na ostatnie pytanie. "
            "Zakończ odpowiedź na tym jednym zdaniu."
        )
    return system_context, True


def _normal_history_options(request: SimpleChatRequest) -> tuple[bool, bool, bool]:
    local_qualification = (
        SETTINGS.ACADEMY_QUALIFIED_CHAT_ENABLED and not request.use_notes
    )
    omit_truncated = local_qualification and changes_example(request.content)
    supplied_update = local_qualification and bool(
        source_revision_hint(request.content)
    )
    omit_assistant_links = (
        supplied_update and public_lookup_query(request.content) is None
    )
    return omit_truncated, local_qualification, omit_assistant_links


def _source_plan(
    request: SimpleChatRequest,
    history: list[HistoryMessage],
    history_records: list[dict[str, object]],
    *,
    local_qualification: bool,
    provided_information_only: bool,
) -> _SourcePlan:
    previous_users = [turn.content for turn in history if turn.role == "user"]
    previous = previous_users[-1] if previous_users else ""
    query = grounding_follow_up(request.content, previous)
    prior_evidence = (
        _previous_evidence(history_records) if local_qualification else None
    )
    explicit_rss = local_qualification and is_rss_read_request(request.content)
    scope_reply = (
        previous_scope_reply(prior_evidence)
        if local_qualification
        and asks_about_previous_scope(request.content)
        and not explicit_rss
        else None
    )
    if local_qualification and not explicit_rss and scope_reply is None:
        scope_reply = previous_verified_fact_reply(request.content, prior_evidence)
    prior_context = (
        ""
        if explicit_rss
        else previous_public_fact_context(request.content, prior_evidence)
    )
    if (
        scope_reply
        or prior_context
        or provided_information_only
        or lookup_forbidden(request.content, previous_users)
    ):
        query = None
    elif local_qualification:
        query = (
            None
            if source_revision_hint(request.content)
            else public_lookup_query(query)
        )
    if explicit_rss and query is not None:
        query = rss_editorial_query(query)
    return _SourcePlan(query, explicit_rss, scope_reply, prior_context)


def _source_policy(
    request: SimpleChatRequest,
    source_context: str,
    evidence: PublicSourceEvidence | None,
    output_tokens: int,
) -> str:
    if not source_context.startswith(PUBLIC_SOURCE_BLOCK):
        return _SOURCE_STATUS_POLICY
    policy = _RETRIEVED_SOURCE_POLICY
    if is_current_news_request(request.content):
        policy += (
            " Przy odczycie nagłówka zacznij od «Nagłówek RSS». "
            "Podaj nagłówek po polsku. Jeżeli wskazuje, kto powiedział, "
            "poinformował lub ogłosił, podaj tę osobę lub instytucję "
            "w osobnym polu «Atrybucja». Zachowaj tę informację także przy "
            "tłumaczeniu końcówki «said» lub «says». Przetłumacz opis "
            "funkcji albo instytucji w atrybucji, zachowując nazwy własne. "
            "Dołącz pole «Data publikacji» z datą źródła i pole «Link» "
            "z pełnym URL pozycji."
        )
    if output_tokens <= 128 or _SHORT_SOURCE_REQUEST.search(request.content):
        policy += _SHORT_SOURCE_POLICY
    if evidence is not None and evidence.scope == "wiki":
        policy += _wiki_sentence_policy(request.content)
    return policy


def _source_context_state(
    request: SimpleChatRequest,
    source_context: Any,
    plan: _SourcePlan,
    setup: _NormalChatSetup,
) -> tuple[str, tuple[Any, ...], str | None, PublicSourceEvidence | None]:
    headlines = (
        source_context.headlines
        if plan.explicit_rss and isinstance(source_context, PublicSourceContext)
        else ()
    )
    scope_reply = plan.scope_reply
    if plan.explicit_rss and not headlines:
        scope_reply = _RSS_NOT_READ
    evidence = None
    if not setup.local_qualification or not source_context:
        return source_context, headlines, scope_reply, evidence
    if isinstance(source_context, PublicSourceContext):
        evidence = source_context.evidence
        scope_reply = scope_reply or source_context.reply
    elif isinstance(source_context, PublicSourceUnavailable):
        evidence = PublicSourceEvidence("unavailable")
        source_context = "\nW tej turze nie udało się odczytać publicznego źródła."
    policy = _source_policy(request, source_context, evidence, setup.output_tokens)
    if len(policy) + 1 + len(source_context) <= setup.remaining:
        source_context = f"{policy}\n{source_context}"
    return source_context, headlines, scope_reply, evidence


def _fit_source_context(
    system_context: str,
    prior_context: str,
    source_context: str,
    scope_reply: str | None,
    headlines: tuple[Any, ...],
    evidence: PublicSourceEvidence | None,
    remaining: int,
) -> tuple[str, str | None, tuple[Any, ...], PublicSourceEvidence | None]:
    if prior_context and len(prior_context) <= remaining:
        system_context += prior_context
    if len(source_context) <= remaining:
        return system_context + source_context, scope_reply, headlines, evidence
    if headlines:
        scope_reply = (
            "Odczytano tylko nagłówki RSS. Nie mieszczą się w kontekście odpowiedzi."
        )
        headlines = ()
    elif scope_reply is None:
        evidence = None
    fallback = "\nFresh source context did not fit; say it was not checked."
    if source_context and len(fallback) <= remaining:
        system_context += fallback
    return system_context, scope_reply, headlines, evidence


async def prepare_studio_normal(
    request: SimpleChatRequest,
    store: SessionStore | None,
    get_vector_store: Callable[[], Awaitable[Any]],
) -> tuple[SimpleChatRequest, str]:
    """Build a single prompt with history and retrieve notes only when requested."""
    setup = await _normal_chat_setup(request, store, get_vector_store)
    plan = _source_plan(
        request,
        setup.history,
        setup.history_records,
        local_qualification=setup.local_qualification,
        provided_information_only=setup.provided_information_only,
    )
    source_context = (
        ""
        if plan.query is None
        else await current_chat_context(plan.query, use_notes=request.use_notes)
    )
    source_context, headlines, scope_reply, evidence = _source_context_state(
        request, source_context, plan, setup
    )
    system_context, scope_reply, headlines, evidence = _fit_source_context(
        setup.system_context,
        plan.prior_context,
        source_context,
        scope_reply,
        headlines,
        evidence,
        setup.remaining,
    )
    budget = setup.budget - len(system_context)
    if budget < 0:
        raise HTTPException(413, {"reason_code": "studio_normal_context_limit"})
    prepared = request.model_copy(
        update={
            "history": _recent_turns(
                store,
                setup.session_id,
                min(budget, MAX_CHAT_HISTORY_CHARS),
                omit_truncated=setup.omit_truncated,
                omit_assistant_links=setup.omit_assistant_links,
                history=setup.history_records,
            ),
            "max_tokens": setup.output_tokens,
            "think": False,
        }
    )
    prepared._studio_public_source_evidence = evidence.to_record() if evidence else None
    prepared._studio_public_scope_reply = scope_reply
    prepared._studio_rss_headlines = headlines
    return prepared, system_context
