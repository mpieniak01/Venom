"""Resolve explicit updates to a named event from the user's conversation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from venom_core.services.chat_policy.qualified_chat_quote import (
    single_quoted_operand,
    without_quotes,
)

_HEADER = re.compile(
    r"(?:przyjmij jako ustalone dla|ustalenia dla|zapisz sobie na tę rozmowę notatkę|"
    r"doszedł drugi komunikat do|jeszcze korekta redakcyjna do|korekta (?:redakcyjna )?do|"
    r"(?:decyzja|ustalenie) dla|(?:ostatnia kwestia )?przy|w sprawie|dla)\s*",
    re.I,
)
_HEADER_PROPOSAL = re.compile(r"(przy|w sprawie)\s+rozważamy zmianę", re.I)
_TITLE = re.compile(r"[\w -]{1,80}", re.UNICODE)
_INITIAL_HEADERS = {
    "przyjmij jako ustalone dla",
    "ustalenia dla",
    "zapisz sobie na tę rozmowę notatkę",
}
_ROOM = r"[A-ZĄĆĘŁŃÓŚŹŻ][\w-]{0,39}(?:[ \t]+[A-ZĄĆĘŁŃÓŚŹŻ][\w-]{0,39}){0,3}"
_TIME = r"(?:[01]?\d|2[0-3]):[0-5]\d"
_ROOM_FIELD = re.compile(rf"(?i:(?:sala|pracownia)(?:\s*:\s*|\s+))(?P<value>{_ROOM})")
_ROOM_MOVE = re.compile(
    rf"(?i:(?:zmienić salę na|(?:sala|pracownia)\s+na|"
    rf"(?:spotkanie|warsztat) przeniesiono do (?:sali|pracowni)))\s+(?P<value>{_ROOM})"
)
_TIME_FIELD = re.compile(rf"(?:(?:godzin[ęa]|start)\s*:?\s*)?(?P<value>{_TIME})", re.I)
_HOST_FIELD = re.compile(
    rf"(?i:(?:prowadzi|prowadząca|prowadzący)\s*:?\s*)(?P<value>{_ROOM})"
)
_NOTE_EVENT = re.compile(
    rf"(?i:(?:spotkanie|warsztat|zajęcia) (?:jest|są) o) (?P<time>{_TIME}) "
    rf"(?i:w (?:sali|pracowni)) (?P<room>{_ROOM})"
)
_FREE_ENTRY = re.compile(r"wstęp (?:jest )?wolny", re.I)
_BRING = re.compile(r"trzeba przynieść (?P<item>[a-ząćęłńóśźż -]{1,60})", re.I)
_PROPOSE = re.compile(
    r"(?:rozważamy zmianę|proponuję|propozycja)\s*:\s*(?P<fields>.+)", re.I
)
_ACCEPT = re.compile(
    r"(?:zatwierdzam|akceptuję|przyjmuję)\b(?:\s+(?P<fields>.+))?", re.I
)
_REJECT = re.compile(
    rf"(?:odrzucam (?:propozycję|zmianę)(?: (?P<field>godziny|sali))?|"
    rf"pomysł przesunięcia startu na (?P<time>{_TIME}) nie został zatwierdzony)",
    re.I,
)
_LOOKUP = re.compile(
    r"(?:to (?:tylko )?propozycja\.\s+)?"
    r"(?:co (?:nadal )?obowiązuje|podaj (?:teraz )?(?:obowiązującą wersję|aktualne ustalenia)|"
    r"(?:w jednym lub dwóch zdaniach )?daj ostateczne podsumowanie|"
    r"potwierdź zwięźle najważniejsze ustalenia)\s*[.!?]?",
    re.I,
)
_SUMMARY = re.compile(
    r"przygotuj (?:teraz )?(?:dwuzdaniową|krótką) informację na podstawie (?:obu )?notatek"
    r"(?:\s+po korekcie)?[.!]?(?:\s+użyj nowej wartości, nie korzystaj z internetu[.!]?)?",
    re.I,
)
_CHANGES = re.compile(r"rozróżnij zmianę od tego, co już było[.!]?", re.I)
_NEW_ONLY = re.compile(r"wypisz (?:w jednym zdaniu )?tylko nowe informacje[.!]?", re.I)
_PART_SEPARATOR = re.compile(r"[,;]\s*")
_SENTENCE_SEPARATOR = re.compile(r"(?<=[.!?])\s+")


@dataclass
class _Event:
    values: dict[str, str] = field(default_factory=dict)
    proposal: dict[str, str] = field(default_factory=dict)

    def update(self, entries: dict[str, str]) -> None:
        self.values.update(entries)
        for key in entries:
            self.proposal.pop(key, None)


def _named_message(message: str) -> tuple[str, str, str] | None:
    title = single_quoted_operand(message)
    if title is None or not _TITLE.fullmatch(title):
        return None
    visible = without_quotes(message)
    prefix, separator, body = visible.partition(":")
    prefix, body = prefix.strip(), body.strip()
    if not separator:
        return None
    if proposal := _HEADER_PROPOSAL.fullmatch(prefix):
        return title.casefold(), proposal[1].casefold(), f"propozycja: {body}"
    return (
        (title.casefold(), prefix.casefold(), body)
        if _HEADER.fullmatch(prefix)
        else None
    )


def _fields(clause: str) -> dict[str, str]:
    fields = {}
    for part in _PART_SEPARATOR.split(clause):
        part = part.strip()
        for name, pattern in (
            ("room", _ROOM_FIELD),
            ("room", _ROOM_MOVE),
            ("time", _TIME_FIELD),
            ("host", _HOST_FIELD),
        ):
            match = pattern.fullmatch(part)
            if match is not None:
                if name in fields:
                    return {}
                fields[name] = match["value"]
                break
        else:
            if _FREE_ENTRY.fullmatch(part):
                fields["admission"] = "wstęp jest wolny"
            elif (event := _NOTE_EVENT.fullmatch(part)) is not None:
                if "room" in fields or "time" in fields:
                    return {}
                fields.update(room=event["room"], time=event["time"])
            elif (bring := _BRING.fullmatch(part)) is not None:
                fields["bring"] = f"trzeba przynieść {bring['item']}"
            elif not (fields and part.casefold() == "godzina bez zmian"):
                return {}
    return fields


def _accepted_fields(state: _Event, clause: str | None) -> dict[str, str]:
    if clause is None or clause.casefold() in {"propozycję", "zmianę"}:
        return state.proposal.copy()
    explicit = _fields(clause)
    if explicit:
        return explicit
    # A bare room name is an acceptance only when it matches a pending room.
    room = state.proposal.get("room")
    if room and clause.partition(",")[0].strip().casefold() == room.casefold():
        suffix = clause.partition(",")[2].strip().casefold()
        if suffix in {"", "godzinę i prowadzącą zostawiam", "reszta bez zmian"}:
            return {"room": room}
    return {}


def _apply(state: _Event, header: str, clause: str) -> dict[str, str]:
    if clause.endswith("?"):
        return {}
    clause = clause.rstrip(".!")
    if header in _INITIAL_HEADERS:
        initial = _fields(clause)
        if "room" in initial and "time" in initial:
            state.values = initial
            state.proposal.clear()
        return {}
    if not state.values:
        return {}
    if proposal := _PROPOSE.fullmatch(clause):
        state.proposal = _fields(proposal["fields"])
        return {}
    if rejection := _REJECT.fullmatch(clause):
        _reject(state, rejection)
        return {}
    accepted = _ACCEPT.fullmatch(clause)
    changes = (
        _accepted_fields(state, accepted["fields"])
        if accepted
        else _note_update(header, clause)
    )
    state.update(changes)
    return changes


def _reject(state: _Event, rejection: re.Match[str]) -> None:
    if rejection["time"] is not None:
        if state.proposal.get("time") == rejection["time"]:
            state.proposal.pop("time")
    elif rejection["field"] is not None:
        key = "room" if rejection["field"].casefold() == "sali" else "time"
        state.proposal.pop(key, None)
    else:
        state.proposal.clear()


def _note_update(header: str, clause: str) -> dict[str, str]:
    if header == "doszedł drugi komunikat do" or "korekta" in header:
        return _fields(clause)
    return {}


def _read_message(state: _Event, header: str, body: str) -> tuple[dict[str, str], str]:
    clause, *instructions = _SENTENCE_SEPARATOR.split(body, maxsplit=1)
    return _apply(state, header, clause), instructions[0] if instructions else ""


def _render(state: _Event, changes: dict[str, str], instruction: str) -> str | None:
    room, time = state.values.get("room"), state.values.get("time")
    if not room or not time:
        return None
    if _NEW_ONLY.fullmatch(instruction) and "bring" in changes:
        return changes["bring"].capitalize() + "."
    if _CHANGES.fullmatch(instruction) and changes.keys() == {"room"}:
        return f"Nowe miejsce to {room}. Godzina {time} pozostaje bez zmian."
    if not _LOOKUP.fullmatch(instruction):
        return None
    return _summary(state)


def _summary(state: _Event) -> str:
    current = f"Miejsce to {state.values['room']}, godzina {state.values['time']}"
    if host := state.values.get("host"):
        current += f", prowadzi {host}"
    details = [
        state.values[key] for key in ("admission", "bring") if key in state.values
    ]
    if details:
        current += ". " + " i ".join(details).capitalize()
    pending = [
        f"{label} {state.proposal[key]}"
        for key, label in (
            ("room", "miejsce"),
            ("time", "godzina"),
            ("host", "prowadzący"),
        )
        if key in state.proposal
    ]
    if pending:
        current += ". Propozycja do zatwierdzenia to " + ", ".join(pending)
    return current + "."


def event_state_reply(content: str, preceding_users: Sequence[str]) -> str | None:
    """Apply only named, explicit updates and answer bounded read-only requests."""
    current = _named_message(content)
    title = single_quoted_operand(content)
    if title is None:
        return None
    summary_request = _SUMMARY.fullmatch(without_quotes(content).strip())
    if current is None and summary_request is None:
        return None
    state = _Event()
    for message in preceding_users:
        prior = _named_message(message)
        if prior is not None and prior[0] == title.casefold():
            _read_message(state, prior[1], prior[2])
    if current is not None:
        changes, instruction = _read_message(state, current[1], current[2])
        return _render(state, changes, instruction)
    return _summary(state) if {"room", "time"} <= state.values.keys() else None
