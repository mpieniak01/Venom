"""Prepare the lightweight Studio Normal stream from persisted chat and notes."""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from venom_core.api.schemas.llm_simple import (
    MAX_CHAT_HISTORY_CHARS,
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
from venom_core.services.chat_grounding import (
    PUBLIC_SOURCE_BLOCK,
    PublicSourceUnavailable,
    current_chat_context,
    is_current_news_request,
)
from venom_core.services.chat_policy.history import recent_turns
from venom_core.services.chat_policy.qualified_chat_explanations import changes_example
from venom_core.services.chat_policy.qualified_chat_quote import without_quotes
from venom_core.services.chat_policy.qualified_chat_revisions import (
    explicit_lookup_allowed,
    public_lookup_query,
    source_revision_hint,
)
from venom_core.services.chat_policy.studio_sources import (
    StudioSourcePlan,
    plan_studio_source,
)
from venom_core.services.public_source_evidence import (
    PublicSourceContext,
    PublicSourceEvidence,
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
_WIKI_LOCAL_FACT = re.compile(
    r"(?P<fact>.+) \((?P<url>https://pl\.wikipedia\.org/wiki/\S+)\)\."
)
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")
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
    store: SessionStore
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


def _wiki_sentence_format(message: str) -> tuple[int, bool] | None:
    visible = without_quotes(message)
    matches = list(_SENTENCE_REQUEST.finditer(visible))
    if not matches:
        return None
    count = 1 if matches[-1].group("one") else 2
    return count, bool(_DECIMAL_DOT_REQUEST.search(visible))


def _wiki_sentence_policy(message: str) -> str:
    requested = _wiki_sentence_format(message)
    if requested is None:
        return ""
    count, decimal_dot = requested
    limit = (
        " Napisz dokładnie jedno zdanie. Połącz pytany fakt i odnośnik w tym samym "
        "zdaniu. Pomiń osobną definicję hasła, jeżeli pytanie dotyczy konkretnej cechy."
        if count == 1
        else " Napisz dokładnie dwa zdania. W obu pozostań przy zakresie pytania."
    )
    return limit + _WIKI_FACT_POLICY + (_DECIMAL_DOT_POLICY if decimal_dot else "")


def _wiki_local_reply(message: str, reply: str) -> str:
    requested = _wiki_sentence_format(message)
    fact_with_url = _WIKI_LOCAL_FACT.fullmatch(reply)
    if requested is None or fact_with_url is None:
        return reply
    count, decimal_dot = requested
    fact, url = fact_with_url["fact"], fact_with_url["url"]
    if decimal_dot:
        fact = _DECIMAL_COMMA.sub(".", fact)
    if count == 1:
        return f"{fact} ({url})."
    return f"{fact}. Potwierdza to polska Wikipedia ({url})."


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
    history = recent_turns(
        store,
        session_id,
        max(0, min(remaining, MAX_CHAT_HISTORY_CHARS)),
        omit_truncated=omit_truncated,
        omit_assistant_links=omit_assistant_links,
        history=history_records,
    )
    return _NormalChatSetup(
        session_id,
        store,
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
    plan: StudioSourcePlan,
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
    if not source_context:
        return source_context, headlines, scope_reply, None
    evidence = None
    if isinstance(source_context, PublicSourceContext):
        evidence = source_context.evidence
        if setup.local_qualification:
            local_reply = source_context.reply
            if evidence.scope == "wiki" and local_reply is not None:
                local_reply = _wiki_local_reply(request.content, local_reply)
            scope_reply = scope_reply or local_reply
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
    plan = plan_studio_source(
        request.content,
        setup.history,
        setup.history_records,
        local_qualification=setup.local_qualification,
        provided_information_only=setup.provided_information_only,
        use_notes=request.use_notes,
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
    if plan.prior_context and len(plan.prior_context) <= setup.remaining:
        evidence = evidence or plan.retained_evidence
    if scope_reply and not setup.local_qualification:
        system_context += (
            "\n\nPodaj zakres poprzedniego odczytu na podstawie tego zapisu aplikacji: "
            + scope_reply
        )
    budget = setup.budget - len(system_context)
    if budget < 0:
        raise HTTPException(413, {"reason_code": "studio_normal_context_limit"})
    prepared = request.model_copy(
        update={
            "history": recent_turns(
                setup.store,
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
