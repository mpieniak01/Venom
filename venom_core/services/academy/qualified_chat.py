"""Publication controls for qualified direct Gemma chat."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.academy.qualified_chat_constraints import (
    active_constraints,
    constraint_conflicts,
    constraint_labels,
    find_violations,
    uncertain_constraints,
)
from venom_core.services.academy.qualified_chat_evidence import evidence_reply
from venom_core.services.academy.qualified_chat_mechanisms import (
    checked_explanation,
    ice_melting_reply,
)
from venom_core.services.academy.qualified_chat_options import (
    CountRequirement,
    option_key,
    requested_count,
    split_options,
)
from venom_core.services.academy.qualified_chat_quote import (
    QuoteRewrite,
    parse_quote_rewrite,
)
from venom_core.services.academy.qualified_chat_schedule import (
    draft_time_revision,
    route_shift,
)
from venom_core.services.academy.qualified_chat_writing import selects_one_proposal

QUALIFIED_MODEL = "gemma4:12b-it-q4_k_m"
QUALIFIED_BOLT_MODEL = "hf.co/nvidia/nvidia-nemotron-3.5-bolt-e4b-4gb:q4_k_m"
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
    rf"{_CALENDAR_WRITE}.{{0,100}}{_CALENDAR_NAME}|"
    rf"\bwpis\w* (?:już )?(?:jest|widnieje|znajduje się) (?:już )?w {_CALENDAR_NAME}",
    re.I,
)
_CLAUSE_SPLIT = re.compile(r"[.!?;\n]|\b(?:ale|jednak|natomiast)\b", re.I)
_CALENDAR_CONTEXT = re.compile(_CALENDAR_NAME, re.I)
_CALENDAR_CUE = re.compile(
    rf"{_CALENDAR_NAME}|\b(?:{_WRITE_VERBS}|wpis\w*|został\w*)\b", re.I
)
_UNFINISHED_WORD = re.compile(r"\w+$")
_TRAILING_CONTEXT = re.compile(r"\b(?:nie|w|we|do)\s*$", re.I)
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
_SECONDS = re.compile(r"(?<![\d,.-])([1-9][0-9]?) sekund(?:ę|y)?\b", re.I)
_STATED_TIME = re.compile(r"\b[0-9]+(?:[.,][0-9]+)?\s*(?:sekund\w*|minut\w*|s\b)", re.I)
_SIGN = re.compile(
    r"\b(?:co to znaczy|wyjaśnij[^.!?]{0,40}(?:napis|co to znaczy))", re.I
)
_FREE = re.compile(r"wstęp wolny|bezpłatny wstęp|wstęp bezpłatny", re.I)
_ENTRY = re.compile(
    r"obowiązują wejściówki|wymagana wejściówka|wymagane wejściówki", re.I
)
_REMOVAL = re.compile(r"\b(?:czy samo|czy sama)\s+(?:wyjęcie|usunięcie)\b", re.I)
_WEIGHT = re.compile(r"\b(?:ciężar\w*|ciężk\w*|wag[aię]|mas[ayę]|waż\w*)\b", re.I)
_SIZE = re.compile(
    r"\b(?:gabaryt\w*|miejsce|przejście|rozmiar\w*|wymiar\w*|(?:z)?mieśc\w*|półk\w*)\b",
    re.I,
)


def _claim(clauses: str) -> bool:
    return any(
        _CALENDAR_CLAIM.search(clause) for clause in _CLAUSE_SPLIT.split(clauses)
    )


@dataclass
class CalendarClaimStream:
    """Stream stable words until a possible calendar claim needs inspection."""

    pending: str = ""

    def push(self, chunk: str) -> str:
        self.pending += chunk
        tail = _UNFINISHED_WORD.search(self.pending)
        boundary = tail.start() if tail else len(self.pending)
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


def _source_reply(text: str, users: Sequence[str]) -> str | None:
    quotes = re.findall(r"„([^”]+)”", text)
    if _SIGN.search(text) and len(quotes) == 1:
        parts = [part.strip().rstrip(".") for part in re.split(r"[,;]", quotes[0])]
        if len(parts) == 2 and any(
            _FREE.fullmatch(free) and _ENTRY.fullmatch(entry)
            for free, entry in (parts, parts[::-1])
        ):
            return "Wstęp jest bezpłatny. Do wejścia potrzebujesz wejściówki."
    context = " ".join(users)
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

    @property
    def requires_complete_draft(self) -> bool:
        return (
            self.local_text is not None
            or self.rewrite is not None
            or bool(self.restrictions)
            or self.timed
            or self.count is not None
            or self.calendar_context
        )

    @property
    def schema(self) -> dict[str, Any] | None:
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
        label = (
            "sekundę"
            if seconds == 1
            else "sekundy"
            if seconds % 10 in (2, 3, 4) and seconds % 100 not in (12, 13, 14)
            else "sekund"
        )
        action = action.strip().rstrip(".!?")
        return f"Przez {seconds} {label} {action[0].lower() + action[1:]}."

    def publish(
        self, draft: str, repair: str | None = None, *, truncated: bool = False
    ) -> str:
        if self.rewrite is not None:
            return self.rewrite.publish(draft)
        if self.timed:
            return self._publish_timed(draft)
        if self.count:
            values: dict[str, str] = {}
            for option in [*self.options(draft), *self.options(repair or "")]:
                values.setdefault(option_key(option), option)
            options = list(values.values())[: self.count.count]
            if not options or not self.count.accepts(len(options)):
                return GENERATION_TRUNCATED if truncated else _CLARIFICATION
            if len(options) == 1:
                return options[0]
            return "\n".join(f"{i}. {option}" for i, option in enumerate(options, 1))
        if _claim(draft):
            return _CALENDAR_UNCONFIRMED
        return draft if draft.strip() and self._allowed(draft) else _CLARIFICATION


def prepare_studio_reply(
    text: str, history: Sequence[HistoryMessage], *, token_budget: int | None = None
) -> QualifiedReply | None:
    quote = parse_quote_rewrite(text)
    if isinstance(quote, QuoteRewrite):
        if literal := quote.literal_reply:
            return QualifiedReply(local_text=literal)
        return QualifiedReply(rewrite=quote)
    if answer := quote or evidence_reply(text, history):
        return QualifiedReply(local_text=answer)
    if answer := draft_time_revision(text, history) or ice_melting_reply(
        text, history, token_budget=token_budget
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


def prepare_reply(text: str, history: Sequence[HistoryMessage]) -> QualifiedReply:
    normalized = _normalize(text)
    users = [turn.content for turn in history if turn.role == "user"]
    messages = [{"role": turn.role, "content": turn.content} for turn in history]
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
    messages.append({"role": "user", "content": text})
    if constraint_conflicts(messages):
        return QualifiedReply(_CLARIFICATION)
    restrictions = active_constraints(messages)
    time_bound, preserved = _duration(text, history, users)
    count = requested_count(text)
    hint = _format_hint(text, restrictions)
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
        hint += (
            " W polu options podaj pojedynczą pełną propozycję w każdym elemencie tablicy. "
            "Każdy element ma zawierać jedną samodzielną opcję."
        )
        if {"water", "glue"} <= restrictions:
            hint += " Wybieraj przedmioty gotowe do użycia na sucho, bez podlewania i mocowania klejem."
    return QualifiedReply(
        restrictions=restrictions,
        hint=hint.strip(),
        count=count,
        timed=time_bound,
        retained_seconds=preserved,
        calendar_context=any(_CALENDAR_CONTEXT.search(turn) for turn in (*users, text)),
    )
