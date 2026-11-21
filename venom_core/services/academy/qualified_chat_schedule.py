"""Shift only an unambiguous, user-declared conversational schedule."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.academy.qualified_chat_quote import (
    single_quoted_operand,
    without_quotes,
)

_MONDAY = "poniedziałek"
_WEDNESDAY = "środa"
_FRIDAY = "piątek"
_REHEARSAL = "próba"
_DAYS = {
    _MONDAY: _MONDAY,
    "wtorek": "wtorek",
    "środę": _WEDNESDAY,
    _WEDNESDAY: _WEDNESDAY,
    "czwartek": "czwartek",
    _FRIDAY: _FRIDAY,
    "sobotę": "sobota",
    "sobota": "sobota",
    "niedzielę": "niedziela",
    "niedziela": "niedziela",
}

_EVENTS = {
    _REHEARSAL: _REHEARSAL,
    "próbę": _REHEARSAL,
    "odprawa": "odprawa",
    "odprawę": "odprawa",
    "spotkanie": "spotkanie",
    "zajęcia": "zajęcia",
}
_EVENT = "(?:" + "|".join(_EVENTS) + ")"
_DAY_FORMS = "(?:" + "|".join(_DAYS) + ")"
_DAYS_ORDER = (
    "poniedziałek",
    "wtorek",
    _WEDNESDAY,
    "czwartek",
    _FRIDAY,
    "sobota",
    "niedziela",
)
_DAY_TEXT = {
    "poniedziałek": "w poniedziałek",
    "wtorek": "we wtorek",
    "środa": "w środę",
    "czwartek": "w czwartek",
    "piątek": "w piątek",
    "sobota": "w sobotę",
    "niedziela": "w niedzielę",
}
_CLOCK = r"(?:[01]?[0-9]|2[0-3]):[0-5][0-9]"
_DRAFT = (
    r"(?:napisz (?:krótkie )?ogłoszenie|ułóż (?:krótkie ogłoszenie|jedno zdanie)):\s*"
)
_NOTATE = r"(?:zapisz|zanotuj|dopisz|ustal)\s+"
_START = re.compile(
    rf"(?:(?:{_DRAFT})?(?P<draft>{_EVENT})(?:\s+(?:jest|będzie|odbędzie się))?\s*"
    rf"|{_NOTATE}(?P<noted>{_EVENT}):\s*)"
    rf"(?:(?:w|we)\s+(?P<weekday>{_DAY_FORMS})\s+)?(?:o\s+)?(?P<start>{_CLOCK})"
    r"(?:\s*,\s*(?P<entry>wejście\s+(?:od|przez)\s+[\w -]+))?"
    r"(?:\s+(?P<room>w\s+sali\s+[\w -]+))?",
    re.I,
)
_ENTRY_UPDATE = re.compile(
    r"wejście\s+(?:jednak\s+)?(?P<entry>(?:od|przez)\s+[\w -]+)"
    r"(?:\.\s*godzina i dzień pozostają)?",
    re.I,
)
_ARRIVAL = re.compile(
    r"(?:poproś o przyjście|proszę przyjść)\s+(?P<minutes>[0-9]{1,4})\s+"
    r"minut[ęy]?\s+wcześniej",
    re.I,
)
_SHIFT_HEAD = re.compile(r"(?:proszę\s+)?(?:przesuń|cofnij)\b", re.I)
_START_TARGET = r"(?:godzinę(?: rozpoczęcia)?|" + _EVENT + r")"
_TIME_HINT = re.compile(
    rf"\b{_START_TARGET}\b|\bo\s+(?:[0-9]+\s+minut\w*|godzinę)", re.I
)
_SHIFT = re.compile(
    rf"(?:proszę\s+)?(?P<verb>przesuń|cofnij)\s+(?P<target>{_START_TARGET})\s+"
    r"o\s+(?P<minutes>[0-9]{1,4})\s+minut[ęy]?"
    r"(?:\s+(?P<direction>później|wcześniej|dalej|wstecz|do przodu))?"
    r"(?:,\s*zachowaj\s+(?P<keep>wejście i dzień|dzień i wejście|wejście|dzień))?",
    re.I,
)
_DRAFT_TIME_TARGET = r"godzinę (?:w (?:tym )?szkicu|w treści (?:sms-a|wiadomości))"
_DRAFT_TIME_SCOPE = re.compile(
    rf"^(?:proszę\s+)?(?:zmień|popraw|przesuń|cofnij)\s+{_DRAFT_TIME_TARGET}\b",
    re.I,
)
_DRAFT_TIME_EDIT = re.compile(
    rf"{_DRAFT_TIME_SCOPE.pattern}\s+na\s+(?P<new>{_CLOCK})"
    r"(?:,?\s+i zachowaj krótką formę prośby)?",
    re.I,
)
_DRAFT_REQUEST = re.compile(
    r"\b(?:szkic\w* (?:sms-a|wiadomości)|(?:zredaguj|przeredaguj) polecenie)\b",
    re.I,
)
_DRAFT_FORMAT = re.compile(
    r"^(?:przygotuj|napisz|ułóż|potrzebuję)\b[^.!?]{0,100}"
    r"\bszkic\w* (?:sms-a|wiadomości)\b",
    re.I,
)
_DRAFT_REMINDER = re.compile(
    rf"(?:proszę,?\s+)?(?P<body>(?:ustaw przypomnienie|przypomnij mi)"
    rf" (?:o|żeby) [^.!?]{{1,180}} (?:na|o))\s+(?P<old>{_CLOCK})",
    re.I,
)
_CLOCK_IN_TEXT = re.compile(rf"(?<!\d){_CLOCK}(?!\d)")
_LATER = {"później", "dalej", "do przodu"}
_EARLIER = {"wcześniej", "wstecz"}


@dataclass(frozen=True)
class Schedule:
    event: str
    start: str
    weekday: str | None
    entry: str | None = None
    room: str | None = None
    arrival_before: int | None = None


def _text(text: str) -> str:
    return " ".join(text.strip().rstrip(".!?").split())


def _declaration(text: str) -> Schedule | None:
    match = _START.fullmatch(text)
    if not match:
        return None
    weekday = match["weekday"]
    return Schedule(
        event=_EVENTS[(match["draft"] or match["noted"]).casefold()],
        start=match["start"].zfill(5),
        weekday=_DAYS[weekday.casefold()] if weekday else None,
        entry=match["entry"],
        room=match["room"],
    )


def _shift(text: str, state: Sequence[Schedule]) -> tuple[Schedule | None, str]:
    match = _SHIFT.fullmatch(text)
    if not match:
        return None, "Które zdarzenie przesunąć, o ile minut i w którą stronę?"
    target = _EVENTS.get(match["target"].casefold())
    candidates = [value for value in state if target is None or value.event == target]
    if len(candidates) > 1:
        return None, "Którego zdarzenia dotyczy przesunięcie?"
    if not candidates:
        return None, "Jaka jest potwierdzona godzina rozpoczęcia tego zdarzenia?"
    direction = (match["direction"] or "").casefold()
    if match["verb"].casefold() == "cofnij" and not direction:
        direction = "wcześniej"
    elif match["verb"].casefold() == "cofnij" and direction in _LATER:
        direction = ""
    if direction not in (_EARLIER | _LATER):
        return None, "Czy termin ma być wcześniejszy, czy późniejszy?"
    sign = -1 if direction in _EARLIER else 1

    before = candidates[0]
    hours, minutes = map(int, before.start.split(":"))
    signed_minutes = sign * int(match["minutes"])
    day_delta, minute_of_day = divmod(hours * 60 + minutes + signed_minutes, 24 * 60)
    if day_delta != 0 and "dzień" in (match["keep"] or "").casefold():
        return None, (
            "Przesunięcie zmienia dzień. Czy zmienić dzień zgodnie z obliczeniem, czy zachować pierwotny?"
        )
    weekday = (
        _DAYS_ORDER[(_DAYS_ORDER.index(before.weekday) + day_delta) % len(_DAYS_ORDER)]
        if before.weekday
        else None
    )
    result = replace(
        before,
        start=f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}",
        weekday=weekday,
    )
    if weekday and abs(day_delta) <= 1:
        day_text = _DAY_TEXT[weekday] + " "
    elif day_delta == 1:
        day_text = "następnego dnia "
    elif day_delta == -1:
        day_text = "poprzedniego dnia "
    elif day_delta:
        day_text = (
            f"{abs(day_delta)} dni {'później' if day_delta > 0 else 'wcześniej'}, "
        )
    else:
        day_text = ""
    parts = [f"{result.event.capitalize()}: {day_text}o {result.start}"]
    if result.entry:
        parts.append(result.entry)
    if result.room:
        parts.append(result.room)
    answer = ", ".join(parts) + "."
    if result.arrival_before is not None:
        minutes = result.arrival_before
        answer += f" Prośba: przyjdź {minutes} min wcześniej."
    return result, answer


def _confirmed_history(history: Sequence[dict[str, str]]) -> list[Schedule]:
    state: list[Schedule] = []
    for turn in history:
        if turn.get("role") != "user":
            continue
        text = _text(turn["content"])
        if declaration := _declaration(text):
            state.append(declaration)
        elif len(state) == 1 and (entry := _ENTRY_UPDATE.fullmatch(text)):
            state[0] = replace(state[0], entry="wejście " + entry["entry"])
        elif len(state) == 1 and (arrival := _ARRIVAL.fullmatch(text)):
            state[0] = replace(state[0], arrival_before=int(arrival["minutes"]))
        elif state and _SHIFT_HEAD.match(text):
            changed, _ = _shift(text, state)
            if not changed:
                state.clear()
                continue
            index = next(
                i for i, current in enumerate(state) if current.event == changed.event
            )
            state[index] = changed
        elif state:
            # An uninterpreted intervening user turn may amend or replace the current plan.
            state.clear()
    return state


def _quoted_reminder(text: str) -> re.Match[str] | None:
    if not _DRAFT_FORMAT.match(without_quotes(text)):
        return None
    source = single_quoted_operand(text)
    return _DRAFT_REMINDER.fullmatch(_text(source)) if source else None


def _reminder_text(body: str, time: str) -> str:
    return f"Proszę, {body[0].lower()}{body[1:]} {time.zfill(5)}."


def draft_reminder_reply(text: str) -> str | None:
    reminder = _quoted_reminder(text)
    if not reminder or _CLOCK_IN_TEXT.search(reminder["body"]):
        return None
    return _reminder_text(reminder["body"], reminder["old"])


def draft_time_revision(text: str, history: Sequence[HistoryMessage]) -> str | None:
    edit = _DRAFT_TIME_EDIT.fullmatch(_text(text))
    if not edit or len(history) < 2:
        return None
    user, draft = history[-2:]
    if user.role != "user" or draft.role != "assistant":
        return None
    visible = _text(user.content)
    if not (_DRAFT_REQUEST.search(visible) or _DRAFT_TIME_SCOPE.match(visible)):
        return None
    reminder = _quoted_reminder(user.content) or _DRAFT_REMINDER.fullmatch(
        _text(draft.content)
    )
    if not reminder or _CLOCK_IN_TEXT.findall(visible) != [reminder["old"]]:
        return None
    body = reminder["body"]
    if _CLOCK_IN_TEXT.search(body):
        return None
    return _reminder_text(body, edit["new"])


def route_shift(message: str, history: Sequence[dict[str, str]]) -> str | None:
    """Handle an explicit time shift. History excludes the current message."""
    text = _text(message)
    if _DRAFT_TIME_SCOPE.match(text) or not (
        _SHIFT_HEAD.match(text) and _TIME_HINT.search(text)
    ):
        return None
    _, answer = _shift(text, _confirmed_history(history))
    return answer
