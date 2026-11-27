"""Publication controls for qualified direct Gemma chat."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat_constraints import (
    active_constraints,
    constraint_conflicts,
    constraint_labels,
    find_violations,
    uncertain_constraints,
)
from venom_core.services.chat_policy.qualified_chat_evidence import evidence_reply
from venom_core.services.chat_policy.qualified_chat_mechanisms import (
    checked_explanation,
    ice_melting_reply,
    pump_valve_reply,
    thermal_followup_reply,
)
from venom_core.services.chat_policy.qualified_chat_options import (
    CountRequirement,
    option_key,
    requested_count,
    split_options,
)
from venom_core.services.chat_policy.qualified_chat_quote import (
    QuoteRewrite,
    parse_quote_rewrite,
)
from venom_core.services.chat_policy.qualified_chat_revisions import lookup_forbidden
from venom_core.services.chat_policy.qualified_chat_rss import RSSSummary
from venom_core.services.chat_policy.qualified_chat_schedule import (
    draft_reminder_reply,
    draft_time_revision,
    route_shift,
)
from venom_core.services.chat_policy.qualified_chat_writing import (
    opening_matches,
    opening_sentence,
    opening_target,
    revises_opening_only,
    selects_one_proposal,
)
from venom_core.services.chat_policy.review_draft import ReviewDraft

_CALENDAR_UNCONFIRMED = "Wpis do kalendarza wymaga potwierdzenia wykonania."
_DAYS = {
    "poniedziałek": "w poniedziałek",
    "wtorek": "we wtorek",
    "środę": "w środę",
    "czwartek": "w czwartek",
    "piątek": "w piątek",
    "sobotę": "w sobotę",
    "niedzielę": "w niedzielę",
}
_EVENT = re.compile(
    r"(?:zanotuj|zapisz|ustal)(?P<calendar> w kalendarzu)? "
    r"(?P<event>próbę|odprawę|spotkanie|zajęcia): "
    r"(?:w|we) (?P<day>poniedziałek|wtorek|środę|czwartek|piątek|sobotę|niedzielę) "
    r"o (?P<hour>[01]?[0-9]|2[0-3]):(?P<minute>[0-5][0-9])",
    re.I,
)
_EVENT_NAMES = {"próbę": "Próba", "odprawę": "Odprawa"}
_CALENDAR_REQUEST = re.compile(
    r"^(?:zanotuj|zapisz|dodaj|ustal)\b.*\bkalendarz\w*\b", re.I
)
GENERATION_TRUNCATED = "Odpowiedź przekroczyła limit długości."
_CALENDAR_NAME = r"\b(?:kalendarz\w*|terminarz\w*)\b"
_WRITE_VERBS = (
    r"dodałem|dodałam|dodano|zapisałem|zapisałam|zapisano|wpisałem|wpisałam|"
    r"wpisano|zanotowałem|zanotowałam|zanotowano"
)
_CALENDAR_WRITE = (
    rf"(?<!\bnie )\b(?:{_WRITE_VERBS}|został\w* (?:wpisan|zapisan|dodan)\w*)\b"
)
_CALENDAR_CLAIM = re.compile(
    rf"{_CALENDAR_NAME}.{{0,100}}{_CALENDAR_WRITE}|"
    rf"{_CALENDAR_WRITE}.{{0,100}}{_CALENDAR_NAME}",
    re.I,
)
_CALENDAR_SUBJECT = (
    r"\b(?:wpisy?|spotkani[ea]|wydarzeni[ea]|odpraw[ay]|wizyt[ay]|"
    r"terminy?|rezerwacj[ae]|prób[ay]|zajęcia)\b"
)
_CALENDAR_PRESENCE = re.compile(
    rf"{_CALENDAR_SUBJECT}\s+(?:już\s+)?(?:jest|są|widnieje|znajduje się)"
    rf"\s+(?:już\s+)?w\s+{_CALENDAR_NAME}",
    re.I,
)
_CALENDAR_QUESTION = re.compile(r"^\s*czy\b", re.I)
_CLAUSE_SPLIT = re.compile(r"(?<=[.!?;])|\n|\b(?:ale|jednak|natomiast)\b", re.I)
_CALENDAR_CONTEXT = re.compile(_CALENDAR_NAME, re.I)
_CALENDAR_CUE = re.compile(
    rf"{_CALENDAR_NAME}|{_CALENDAR_SUBJECT}|\b(?:{_WRITE_VERBS}|został\w*)\b", re.I
)
_TRAILING_CONTEXT = re.compile(r"\b(?:czy|nie|w|we|do)\s*$", re.I)
_AMBIGUOUS_PLACE = re.compile(r"\b(?:i|lub|albo|oraz)\b", re.I)
_LOCATION = r"(?:przy|w|za|pod|obok) [\w-]+(?: [\w-]+){0,5}"
_RETURN_LOCATION = re.compile(
    rf"\b(?:zwraca|oddaje)(?: się)? (?P<place>{_LOCATION})(?=[.!?]|$)", re.I
)
_RETURN_UPDATE = re.compile(
    rf"(?:zmień|popraw)(?: tylko)? miejsce zwrotu na (?P<place>{_LOCATION})", re.I
)
_ONLY_LOCATION = re.compile(
    r"(?:podaj|zwróć) (?:tylko|wyłącznie) miejsce zwrotu(?:[.!?] pomiń etykietę i dodatkowe słowa)?",
    re.I,
)
_LAYOUT_ONLY = re.compile(
    r"(?:zapisz|przepisz|podaj|wypisz) (?:tę|teraz tę) treść w dwóch krótkich punktach"
    r"(?:[.!?] zacznij je odpowiednio od słów odbiór i zwrot)?",
    re.I,
)


def _normalize(text: str) -> str:
    return " ".join(text.split()).rstrip(".!?")


def _safe_location(place: str) -> str | None:
    return None if _AMBIGUOUS_PLACE.search(place) else place + "."


def _return_location(history: Sequence[HistoryMessage]) -> str | None:
    for turn in reversed(history):
        if turn.role != "user":
            continue
        clause = _normalize(turn.content)
        if correction := _RETURN_UPDATE.fullmatch(clause):
            return _safe_location(correction["place"])
        if _LAYOUT_ONLY.fullmatch(clause):
            continue
        locations = tuple(_RETURN_LOCATION.finditer(clause))
        return _safe_location(locations[0]["place"]) if len(locations) == 1 else None
    return None


def _calendar_reply(text: str) -> str | None:
    if match := _EVENT.fullmatch(text):
        event = match["event"].casefold()
        title = _EVENT_NAMES.get(event, event.capitalize())
        facts = f"{title} {_DAYS[match['day'].casefold()]} o {int(match['hour']):02d}:{match['minute']}."
        return (
            f"{_CALENDAR_UNCONFIRMED} {facts}"
            if match["calendar"]
            else f"Notatka: {facts}"
        )
    if _CALENDAR_REQUEST.match(text):
        return _CALENDAR_UNCONFIRMED
    return None


if TYPE_CHECKING:
    from venom_core.services.chat_policy.studio_claims import StudioClaimCheck


_DEFAULT_INSTRUCTION = (
    "Prowadź naturalną rozmowę po polsku. Uwzględniaj kontekst, poprawki i żądany format. "
    "Zwykła odpowiedź ma najwyżej cztery zdania."
)
_CLARIFICATION = (
    "Potrzebuję doprecyzowania, żeby odpowiedzieć zgodnie z Twoimi warunkami."
)
_EXACT_SENTENCE = re.compile(
    r"\b(?:jedno(?: krótkie)? zdanie|jednym(?: krótkim)? zdani[eu])\b", re.I
)
_TWO_BULLETS = re.compile(r"\b(?:dwóch krótkich punktach|dwa krótkie punkty)\b", re.I)
_MESSAGE_ONLY = re.compile(
    r"\b(?:sam tekst|samą treść|tylko treść|wyłącznie treść)\b", re.I
)
_EXPLICIT_UNKNOWN = re.compile(
    r"\b(?:nie znam\w*|nie wiem\w*|nie podano|brak danych|bez danych)\b", re.I
)
_SHORT_DRAFT = re.compile(
    r"\b(?:krótko|wiadomoś\w*|przypomni\w*|przeredaguj|zmień ton)\b", re.I
)
_SINGLE_ADVICE = re.compile(
    r"\b(?:jeden|jedną)\b[^.!?]{0,40}\b(?:sposób|metodę)\b", re.I
)
_CAUSE_QUESTION = re.compile(
    r"\b(?:czemu|dlaczego|co powoduje|skąd się bierze|jaka jest przyczyna)\b", re.I
)
_STRICT_COUNT = re.compile(r"\b(?:dokładnie|wyłącznie|tylko|jedynie)\b", re.I)
_STRICT_TIME = re.compile(
    r"\b(?:mniej|krócej|krótsz[aeąy]) niż (?:jedną |1 )?minut[ęy]\b", re.I
)
_KEEP = re.compile(r"\b(?:zachowaj|zostań przy|nadal)\b", re.I)
_SECONDS = re.compile(r"(?<![\d,.-])([1-9]\d?) sekund[ęy]?\b", re.I)
_STATED_TIME = re.compile(
    r"\b(?:\d+(?:[.,]\d+)?\s*(?:sekund\w*|minut\w*|godzin\w*|s\b|min\b|h\b)|"
    r"(?:jedn[aeoąę]|dwa|dwie|trzy|cztery|pięć|sześć|siedem|osiem|dziewięć|"
    r"dziesięć|kilka|kilkanaście|kilkadziesiąt|pół|półtorej|\w+naście|\w+dzieści|\w+dziesiąt)"
    r"\s+(?:sekund\w*|minut\w*|godzin\w*)|pół(?:minut\w*|godzin\w*))\b",
    re.I,
)
_SIGN = re.compile(
    r"\b(?:co to znaczy|wyjaśnij[^.!?]{0,40}(?:napis|co to znaczy))", re.I
)
_FREE = re.compile(r"wstęp wolny|bezpłatny wstęp|wstęp bezpłatny", re.I)
_ENTRY = re.compile(
    r"obowiązują wejściówki|wymagana wejściówka|wymagane wejściówki", re.I
)
_REMOVAL = re.compile(r"\b(?:czy samo|czy sama)\s+(?:wyjęcie|usunięcie)\b", re.I)
_TOPIC_RESET = re.compile(
    r"^\s*(?:zmieniam temat|zmieńmy temat|nowy temat|inny temat)\s*(?:[.!?:,]|$)",
    re.I,
)
_WEIGHT = re.compile(r"\b(?:ciężar\w*|ciężk\w*|wag[aię]|mas[ayę]|waż\w*)\b", re.I)
_SIZE = re.compile(
    r"\b(?:gabaryt\w*|miejsce|przejście|rozmiar\w*|wymiar\w*|(?:z)?mieśc\w*|półk\w*)\b",
    re.I,
)


def _presence_claim(clause: str) -> bool:
    return (
        not clause.rstrip().endswith("?")
        and not _CALENDAR_QUESTION.match(clause)
        and bool(_CALENDAR_PRESENCE.search(clause))
    )


def _claim(clauses: str) -> bool:
    return any(
        _CALENDAR_CLAIM.search(clause) or _presence_claim(clause)
        for clause in _CLAUSE_SPLIT.split(clauses)
    )


def _stable_prefix_end(text: str) -> int:
    end = len(text) - int(text.endswith("\n"))
    start = end
    while start > 0:
        char = text[start - 1]
        if not (char == "_" or char.isalnum()):
            break
        start -= 1
    return start if start < end else len(text)


@dataclass
class CalendarClaimStream:
    """Stream stable words until a possible calendar claim needs inspection."""

    pending: str = ""

    def push(self, chunk: str) -> str:
        self.pending += chunk
        boundary = _stable_prefix_end(self.pending)
        cue = _CALENDAR_CUE.search(self.pending[:boundary])
        if cue is not None:
            boundary = cue.start()
        context = _TRAILING_CONTEXT.search(self.pending[:boundary])
        if context is not None:
            boundary = context.start()
        sent = self.pending[:boundary]
        self.pending = self.pending[boundary:]
        return sent

    def finish(self, *, truncated: bool) -> str:
        if _claim(self.pending):
            return _CALENDAR_UNCONFIRMED
        if truncated:
            return "\n\n" + GENERATION_TRUNCATED
        return self.pending


def _current_topic(users: Sequence[str]) -> str:
    for index in range(len(users) - 1, -1, -1):
        if reset := _TOPIC_RESET.match(users[index]):
            return " ".join((users[index][reset.end() :], *users[index + 1 :]))
    return " ".join(users)


def _source_reply(text: str, users: Sequence[str]) -> str | None:
    quotes = re.findall(r"„([^”]+)”", text)
    if _SIGN.search(text) and len(quotes) == 1:
        parts = [part.strip().rstrip(".") for part in re.split(r"[,;]", quotes[0])]
        if len(parts) == 2 and any(
            _FREE.fullmatch(free) and _ENTRY.fullmatch(entry)
            for free, entry in (parts, parts[::-1])
        ):
            return "Wstęp jest bezpłatny. Do wejścia potrzebujesz wejściówki."
    context = _current_topic(users)
    if _REMOVAL.search(text) and _WEIGHT.search(context) and _SIZE.search(context):
        return (
            "Wyjęcie części zawartości może zmniejszyć ciężar, ale nie gwarantuje mniejszych gabarytów. "
            "Sprawdź zewnętrzne wymiary i miejsce, w którym przedmiot ma się zmieścić."
        )
    return None


def _options_schema(minimum: int, maximum: int) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["options"],
        "additionalProperties": False,
        "properties": {
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": minimum,
                "maxItems": maximum,
            }
        },
    }


def _read_json(draft: str) -> dict[str, Any]:
    try:
        value = json.loads(draft)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _format_hint(text: str, restrictions: frozenset[str]) -> str:
    hints = []
    if _EXACT_SENTENCE.search(text):
        hints.append(
            "Zwróć jedno zdanie i pomiń wstęp, pytanie dodatkowe oraz pożegnanie."
        )
    elif _TWO_BULLETS.search(text):
        hints.append("Zwróć wyłącznie dwa krótkie i samodzielne punkty.")
    elif _MESSAGE_ONLY.search(text) or "krótkie ogłoszenie" in text.casefold():
        hints.append(
            "Podaj wyłącznie gotowy, krótki tekst do wysłania. "
            "Zachowaj podany termin i miejsce. Pomiń wstęp, dopiski i pytania."
        )
    elif _SHORT_DRAFT.search(text):
        hints.append(
            "Podaj jedną krótką, gotową odpowiedź bez wstępu i dodatkowych wariantów. "
            "Zachowaj podane szczegóły i najnowszą poprawkę."
        )
    if restrictions:
        hints.append(
            f"Aktywne wykluczenia: {', '.join(constraint_labels(restrictions))}. "
            "Każda opcja ma spełniać je osobno, także przy linkach i załącznikach."
        )
    return " ".join(hints)


def _duration(
    text: str, history: Sequence[HistoryMessage], users: Sequence[str]
) -> tuple[bool, int | None]:
    if _STRICT_TIME.search(text):
        return True, None
    if not (users and _KEEP.search(text) and _STRICT_TIME.search(users[-1])):
        return False, None
    previous = history[-1] if history else None
    if previous and previous.role == "assistant":
        values = _SECONDS.findall(previous.content)
        if len(values) == 1 and int(values[0]) < 60:
            return True, int(values[0])
    return True, None


@dataclass(frozen=True)
class QualifiedReply:
    local_text: str | None = None
    restrictions: frozenset[str] = frozenset()
    hint: str = ""
    count: CountRequirement | None = None
    timed: bool = False
    retained_seconds: int | None = None
    calendar_context: bool = False
    rewrite: QuoteRewrite | None = None
    rss: RSSSummary | None = None
    opening_only: bool = False
    requested_opening: str | None = None
    review_draft: ReviewDraft | None = None
    claim_check: StudioClaimCheck | None = None
    retry_truncated: bool = False

    @property
    def requires_complete_draft(self) -> bool:
        return (
            self.local_text is not None
            or self.rewrite is not None
            or self.rss is not None
            or self.opening_only
            or self.review_draft is not None
            or self.claim_check is not None
            or bool(self.restrictions)
            or self.timed
            or self.count is not None
            or self.calendar_context
        )

    @property
    def schema(self) -> dict[str, Any] | None:
        if self.rss is not None:
            return self.rss.schema()
        if self.timed:
            return {
                "type": "object",
                "required": ["action", "seconds"],
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string"},
                    "seconds": {
                        "type": "integer",
                        "minimum": self.retained_seconds or 1,
                        "maximum": self.retained_seconds or 59,
                    },
                },
            }
        if self.count:
            return _options_schema(
                self.count.count if self.count.mode == "exact" else 1, self.count.count
            )
        return None

    def prompt(self, custom: str) -> str:
        return "\n\n".join(filter(None, (custom or _DEFAULT_INSTRUCTION, self.hint)))

    def _allowed(self, text: str) -> bool:
        return not (
            _claim(text)
            or find_violations(text, self.restrictions)
            or uncertain_constraints(text, self.restrictions)
        )

    def options(self, draft: str) -> list[str]:
        value = _read_json(draft).get("options")
        if not isinstance(value, list):
            return []
        accepted: dict[str, str] = {}
        for item in value:
            if (
                isinstance(item, str)
                and item.strip()
                and len(
                    split_options(json.dumps({"options": [item]}, ensure_ascii=False))
                )
                == 1
                and self._allowed(item)
            ):
                accepted.setdefault(option_key(item), item.strip())
        return list(accepted.values())

    def repair(self, draft: str) -> tuple[list[str], dict[str, Any]] | None:
        if self.timed or not self.count:
            return None
        kept = self.options(draft)
        if kept and self.count.accepts(len(kept)):
            return None
        missing = self.count.count - len(kept) if self.count.mode == "exact" else 1
        return (kept, _options_schema(missing, missing)) if missing > 0 else None

    def _publish_timed(self, draft: str) -> str:
        value = _read_json(draft)
        action, seconds = value.get("action"), value.get("seconds")
        if (
            not isinstance(action, str)
            or not any(char.isalnum() for char in action)
            or len(action.split()) > 18
            or _STATED_TIME.search(action)
            or type(seconds) is not int
            or not 1 <= seconds <= 59
            or (self.retained_seconds is not None and seconds != self.retained_seconds)
            or not self._allowed(action)
        ):
            return _CLARIFICATION
        if seconds == 1:
            label = "sekundę"
        elif seconds % 10 in (2, 3, 4) and seconds % 100 not in (12, 13, 14):
            label = "sekundy"
        else:
            label = "sekund"
        action = action.strip().rstrip(".!?")
        return f"Przez {seconds} {label} {action[0].lower() + action[1:]}."

    def _publish_counted(self, draft: str, repair: str | None, truncated: bool) -> str:
        values: dict[str, str] = {}
        for option in [*self.options(draft), *self.options(repair or "")]:
            values.setdefault(option_key(option), option)
        count = self.count
        if count is None:
            return GENERATION_TRUNCATED if truncated else _CLARIFICATION
        options = list(values.values())[: count.count]
        if not options or not count.accepts(len(options)):
            return GENERATION_TRUNCATED if truncated else _CLARIFICATION
        if len(options) == 1:
            return options[0]
        return "\n".join(f"{i}. {option}" for i, option in enumerate(options, 1))

    def _publish_default(self, draft: str) -> str:
        if self.opening_only:
            draft = opening_sentence(draft)
            if not opening_matches(draft, self.requested_opening):
                return _CLARIFICATION
        if _claim(draft):
            return _CALENDAR_UNCONFIRMED
        if not draft.strip() or not self._allowed(draft):
            return _CLARIFICATION
        return self.claim_check.publish(draft) if self.claim_check else draft

    def publish(
        self, draft: str, repair: str | None = None, *, truncated: bool = False
    ) -> str:
        if self.rewrite is not None:
            return self.rewrite.publish(draft)
        if self.rss is not None:
            return self.rss.publish(draft)
        if self.timed:
            return self._publish_timed(draft)
        if self.count:
            return self._publish_counted(draft, repair, truncated)
        return self._publish_default(draft)


def prepare_studio_reply(
    text: str, history: Sequence[HistoryMessage], *, token_budget: int | None = None
) -> QualifiedReply | None:
    if revises_opening_only(text):
        return QualifiedReply(
            hint=(
                "Napisz wyłącznie zmienione zdanie otwarcia. Zachowaj sens i negację "
                "najnowszej prośby. Pomiń temat, powitanie, podpis i komentarz."
            ),
            opening_only=True,
            requested_opening=opening_target(text),
        )
    quote = parse_quote_rewrite(text)
    if isinstance(quote, QuoteRewrite):
        if literal := quote.literal_reply:
            return QualifiedReply(local_text=literal)
        return QualifiedReply(rewrite=quote)
    if answer := quote or evidence_reply(text, history):
        return QualifiedReply(local_text=answer)
    if answer := (
        draft_reminder_reply(text)
        or draft_time_revision(text, history)
        or pump_valve_reply(text, history, token_budget=token_budget)
        or ice_melting_reply(text, history, token_budget=token_budget)
        or thermal_followup_reply(text, history, token_budget=token_budget)
    ):
        return QualifiedReply(local_text=answer)
    if explanation := checked_explanation(text, history, token_budget=token_budget):
        return QualifiedReply(local_text=explanation.text())
    if history and selects_one_proposal(text):
        messages = [{"role": turn.role, "content": turn.content} for turn in history]
        messages.append({"role": "user", "content": text})
        restrictions = active_constraints(messages)
        return QualifiedReply(
            count=CountRequirement("exact", 1),
            restrictions=restrictions,
            hint=(
                f"{_format_hint(text, restrictions)} "
                "Zapisz w tablicy options jedną krótką odpowiedź. "
                "Podaj konkretną wskazówkę wykonania zgodną z najnowszym warunkiem. "
                "Pomiń pozostałe wcześniejsze propozycje i samą nazwę czynności."
            ).strip(),
        )
    return None


def _prepare_local_reply(
    text: str,
    history: Sequence[HistoryMessage],
    messages: list[dict[str, str]],
    users: list[str],
) -> QualifiedReply | None:
    normalized = _normalize(text)
    if _ONLY_LOCATION.fullmatch(normalized):
        return QualifiedReply(
            _return_location(history) or "Gdzie dokładnie znajduje się miejsce zwrotu?"
        )
    local = (
        _calendar_reply(normalized)
        or route_shift(text, messages)
        or _source_reply(text, [*users, text])
    )
    if local is not None:
        return QualifiedReply(local)
    return None


def _proposal_constraints(
    text: str,
    users: Sequence[str],
    restrictions: frozenset[str],
    time_bound: bool,
    hint: str,
) -> tuple[CountRequirement | None, str]:
    count = requested_count(text)
    if (
        count is not None
        and count.count == 1
        and count.mode == "exact"
        and not restrictions
        and _SINGLE_ADVICE.search(text)
        and not _STRICT_COUNT.search(text)
    ):
        count = None
        if users and _CAUSE_QUESTION.search(users[-1]):
            hint += (
                " Podaj jedną krótką czynność na wskazany moment. Wybierz czynnik "
                "z poprzedniego wyjaśnienia i powiedz, co ta czynność w nim zmienia "
                "przed wystąpieniem zjawiska. Korzystaj z przyczyn już podanych w rozmowie."
            )
    if time_bound:
        hint += (
            " Zwróć jedno krótkie polecenie bez czasu w polu action, a czas krótszy niż minuta w seconds. "
            "Wybierz zgodną wcześniejszą opcję, jeśli o to proszono, i zachowaj ustalony czas."
        )
    elif count:
        if _EXPLICIT_UNKNOWN.search(text) and lookup_forbidden(text, users):
            hint += (
                " Jeśli bez nieznanej informacji można podać użyteczne ogólne propozycje, "
                "podaj samodzielne propozycje wraz z krótkim uzasadnieniem. "
                "Jeżeli użytkownik prosi o rzeczy lub elementy ubioru, podaj po jednym "
                "konkretnym przedmiocie w opcji, nie ogólną strategię. "
                "Nie zgaduj aktualnych danych. Unikaj alternatyw w obrębie jednej propozycji."
            )
        hint += (
            " W polu options podaj pojedynczą pełną propozycję w każdym elemencie tablicy. "
            "Każdy element ma zawierać jedną samodzielną opcję."
        )
        if {"water", "glue"} <= restrictions:
            hint += " Wybieraj przedmioty gotowe do użycia na sucho, bez podlewania i mocowania klejem."
    return count, hint


def prepare_reply(text: str, history: Sequence[HistoryMessage]) -> QualifiedReply:
    users = [turn.content for turn in history if turn.role == "user"]
    messages = [{"role": turn.role, "content": turn.content} for turn in history]
    if local := _prepare_local_reply(text, history, messages, users):
        return local
    messages.append({"role": "user", "content": text})
    if constraint_conflicts(messages):
        return QualifiedReply(_CLARIFICATION)
    restrictions = active_constraints(messages)
    time_bound, preserved = _duration(text, history, users)
    hint = _format_hint(text, restrictions)
    count, hint = _proposal_constraints(text, users, restrictions, time_bound, hint)
    return QualifiedReply(
        restrictions=restrictions,
        hint=hint.strip(),
        count=count,
        timed=time_bound,
        retained_seconds=preserved,
        calendar_context=any(_CALENDAR_CONTEXT.search(turn) for turn in (*users, text)),
    )
