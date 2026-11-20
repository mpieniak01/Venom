"""Publication controls for qualified direct Gemma chat."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from venom_core.api.schemas.llm_simple import HistoryMessage

QUALIFIED_MODEL = "gemma4:12b-it-q4_k_m"
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
_CALENDAR_CLAIM = re.compile(
    r"\b(?:kalendarz\w*|terminarz\w*)\b.{0,100}\b"
    r"(?:dodałem|dodałam|zapisałem|zapisałam|wpisałem|wpisałam|zanotowałem|zanotowałam)\b"
    r"|\b(?:dodałem|dodałam|dodano|zapisałem|zapisałam|zapisano|wpisałem|wpisałam|"
    r"wpisano|zanotowałem|zanotowałam|zanotowano|(?:został\w*) (?:wpisan|zapisan|dodan)\w*)\b"
    r".{0,100}\b(?:kalendarz\w*|terminarz\w*)\b",
    re.I,
)
_CLAUSE_SPLIT = re.compile(r"[.!?]|\b(?:ale|jednak|natomiast)\b", re.I)
_NEGATED_CLAIM = re.compile(
    r"\bnie (?:dodałem|dodałam|zapisałem|zapisałam|wpisałem|wpisałam|zanotowałem|zanotowałam|został\w*)\b",
    re.I,
)
_LOCATION = r"(?:przy|w|za|pod|obok) [\w-]+(?: [\w-]+){0,5}"
_RETURN_LOCATION = re.compile(
    rf"\b(?:zwraca|oddaje) się (?P<place>{_LOCATION})(?=[.!?]|$)", re.I
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


def _return_location(history: Sequence[HistoryMessage]) -> str | None:
    for turn in reversed(history):
        if turn.role != "user":
            continue
        clause = _normalize(turn.content)
        if correction := _RETURN_UPDATE.fullmatch(clause):
            return correction["place"] + "."
        if _LAYOUT_ONLY.fullmatch(clause):
            continue
        locations = tuple(_RETURN_LOCATION.finditer(clause))
        return locations[0]["place"] + "." if len(locations) == 1 else None
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


@dataclass(frozen=True)
class QualifiedReply:
    local_text: str | None = None

    @staticmethod
    def publish(draft: str) -> str:
        for clause in _CLAUSE_SPLIT.split(draft):
            if _CALENDAR_CLAIM.search(clause) and not _NEGATED_CLAIM.search(clause):
                return _CALENDAR_UNCONFIRMED
        return draft


def prepare_reply(text: str, history: Sequence[HistoryMessage]) -> QualifiedReply:
    normalized = _normalize(text)
    local_text = (
        _return_location(history)
        if _ONLY_LOCATION.fullmatch(normalized)
        else _calendar_reply(normalized)
    )
    return QualifiedReply(local_text)
