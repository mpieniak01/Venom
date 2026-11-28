"""Preserve two distinct source facts during a one-slot editorial correction."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat_quote import (
    single_quoted_operand,
    without_quotes,
)

_WORD = r"[^\W\d_]+"
_LOCATION = rf"(?:w|we|na|przy|obok|pod|za) {_WORD}(?: {_WORD}){{0,2}}"
_UNCERTAIN = re.compile(r"\b(?:nie|chyba|może|prawdopodobnie|jeśli|albo|lub)\b", re.I)
_SOUND_COMMAND = re.compile(
    r"(?:uprość w jednym zdaniu|skróć do jednego zdania)\s*:?\s*[.!]?", re.I
)
_SOUND_SOURCE = re.compile(
    rf"(?P<cause>po (?:zdjęciu|poluzowaniu|przesunięciu|wyjęciu|odkręceniu) {_WORD}) "
    rf"(?P<quiet>{_WORD}) (?P<halt>przestał[ao]? (?:stukać|buczeć|drżeć|brzęczeć|szumieć)) "
    rf"(?P<quiet_place>{_LOCATION}), (?P<link>a|ale|lecz) (?P<continuing>{_WORD}) "
    rf"(?P<continuing_place>{_LOCATION}) "
    r"(?P<persists>(?:nadal|wciąż) (?:tykał|szumiał|brzęczał|stukał|buczał)[ao]?)[.]?",
    re.I,
)
_SOUND_EDIT = re.compile(
    rf"(?P<subject>{_WORD}) (?:stał|był|leżał)[ao]? (?:jednak )?(?P<place>{_LOCATION})[.] "
    rf"zmień tylko (?:miejsce|położenie) (?P<target>{_WORD}), (?:nadal|zachowaj) jedno zdanie[.]?",
    re.I,
)

_LABEL = r"[A-Z][A-Z0-9]{0,2}"
_STORE = r"(?:do protokołu|w rejestrze|w dzienniku|na karcie)"
_MESSAGE_COMMAND = re.compile(
    r"(?:przepisz dwa komunikaty po jednym zdaniu|zapisz dwa komunikaty, każdy w osobnym zdaniu)[.!]?",
    re.I,
)
_PENDING = re.compile(
    rf"karty (?P<label>{_LABEL}) (?:mają być sprawdzone|są do sprawdzenia|trzeba sprawdzić) "
    rf"(?:przed|po|do) {_WORD}",
    re.I,
)
_RECORDED = re.compile(
    rf"odczyt karty (?P<label>{_LABEL}) (?:wpisano|zanotowano|zapisano) {_STORE}",
    re.I,
)
_EVIDENCE = re.compile(
    rf"sprawdzenie kart (?P<label>{_LABEL}) (?:wpisano|odnotowano|zapisano) "
    r"o (?:[01]?[0-9]|2[0-3])(?::[0-5][0-9])?",
    re.I,
)
_MESSAGE_EDIT = re.compile(
    rf"(?:tylko o (?P<only>{_LABEL}) jest teraz dowód wykonania|"
    rf"dla (?P<confirmed>{_LABEL}) potwierdzono wykonanie)\s*[.:]?\s*"
    r"(?P<keep>pierwszy|drugi) komunikat (?:zachowaj|zostaw)(?: bez zmian)?[.!]?",
    re.I,
)


def _source(text: str, command: re.Pattern[str]) -> str | None:
    body = single_quoted_operand(text)
    if body is None or len(body) > 400:
        return None
    visible = " ".join(without_quotes(text).split()).rstrip(" .!")
    return " ".join(body.split()) if command.fullmatch(visible) else None


def _sound_source(text: str) -> re.Match[str] | None:
    if body := _source(text, _SOUND_COMMAND):
        match = _SOUND_SOURCE.fullmatch(body)
        if not match or match["quiet"].casefold() == match["continuing"].casefold():
            return None
        if not any(
            _UNCERTAIN.search(match[key]) for key in ("quiet_place", "continuing_place")
        ):
            return match
    return None


def _sound_edit(text: str) -> re.Match[str] | None:
    edit = _SOUND_EDIT.fullmatch(text)
    return edit if edit and not _UNCERTAIN.search(edit["place"]) else None


def _target_forms(subject: str) -> set[str]:
    name = subject.casefold()
    forms = {name}
    if name.endswith("a"):
        forms.update({f"{name[:-1]}y", f"{name[:-1]}i"})
    else:
        forms.update({f"{name}a", f"{name}u"})
        if name.endswith("ek"):
            forms.add(f"{name[:-2]}ka")
    return forms


def _render_sounds(source: re.Match[str], edits: Sequence[re.Match[str]]) -> str | None:
    places = {key: source[f"{key}_place"] for key in ("quiet", "continuing")}
    subjects = {source[key].casefold(): key for key in places}
    for edit in edits:
        target = subjects.get(edit["subject"].casefold())
        if target is None or edit["target"].casefold() not in _target_forms(
            source[target]
        ):
            return None
        places[target] = edit["place"]
    return (
        f"{source['cause']} {source['quiet']} {places['quiet']} {source['halt']}, "
        f"{source['link']} {source['continuing']} {places['continuing']} {source['persists']}."
    )


def _sound_reply(text: str, users: Sequence[str]) -> str | None:
    if source := _sound_source(text):
        return _render_sounds(source, ())
    if not (edit := _sound_edit(text)):
        return None
    edits = [edit]
    for current in reversed(users):
        if source := _sound_source(current):
            return _render_sounds(source, list(reversed(edits)))
        if not (previous := _sound_edit(current)):
            return None
        edits.append(previous)
    return None


_CESSATION_COMMAND = re.compile(
    r"(?:oddaj|napisz|podaj) (?:prostsze jedno zdanie|jedno prostsze zdanie)[.!:]?",
    re.I,
)
_CESSATION = re.compile(
    rf"(?P<when>po [^.,!?]{{2,90}}) (?P<verb>ustał[ao]?) (?P<sound>{_WORD}(?: {_WORD}){{0,2}}), "
    rf"(?P<link>a|ale|lecz) (?P<subject>{_WORD}) (?P<place>{_LOCATION}) "
    rf"(?P<ongoing>(?:nadal|wciąż) {_WORD})[.]?",
    re.I,
)
_RELOCATE = re.compile(
    rf"(?P<subject>{_WORD}) (?:był[ao]?|stał[ao]?) (?P<place>{_LOCATION}) zamiast "
    rf"(?P<old>{_LOCATION})[.] (?:zmień|popraw) to w jednym zdaniu i zachowaj resztę[.!]?",
    re.I,
)


def _cessation_reply(text: str, users: Sequence[str]) -> str | None:
    edit = _RELOCATE.fullmatch(text)
    request = users[-1] if edit and users else text
    source = _source(request, _CESSATION_COMMAND)
    match = _CESSATION.fullmatch(source) if source else None
    if match is None:
        return None
    location = match["place"]
    if edit:
        if (edit["subject"].casefold(), edit["old"].casefold()) != (
            match["subject"].casefold(),
            location.casefold(),
        ) or _UNCERTAIN.search(edit["place"]):
            return None
        location = edit["place"]
    quiet = "ucichł" + match["verb"].casefold().removeprefix("ustał")
    return (
        f"{match['when']} {quiet} {match['sound']}, {match['link']} "
        f"{match['subject']} {location} {match['ongoing']}."
    )


def _messages(
    text: str,
) -> tuple[list[str], int, re.Match[str]] | None:
    body = _source(text, _MESSAGE_COMMAND)
    if body is None:
        return None
    clauses = re.split(r"\.\s+", body.removesuffix("."))
    if len(clauses) != 2:
        return None
    for i, clause in enumerate(clauses):
        planned = _PENDING.fullmatch(clause)
        recorded = _RECORDED.fullmatch(clauses[1 - i])
        if (
            planned
            and recorded
            and planned["label"].casefold() != recorded["label"].casefold()
        ):
            return clauses, i, planned
    return None


def _render_messages(clauses: Sequence[str]) -> str:
    return "\n".join(f"{clause}." for clause in clauses)


def _message_reply(text: str, previous: str) -> str | None:
    if initial := _messages(text):
        return _render_messages(initial[0])
    edit = _MESSAGE_EDIT.fullmatch(" ".join(without_quotes(text).split()))
    if not edit or not (initial := _messages(previous)):
        return None
    clauses, slot, plan = initial
    material = single_quoted_operand(text)
    if material is None or not (
        proof := _EVIDENCE.fullmatch(material.strip().removesuffix("."))
    ):
        return None
    label = (edit["only"] or edit["confirmed"]).casefold()
    preserved = 0 if edit["keep"].casefold() == "pierwszy" else 1
    if (
        slot == preserved
        or label != plan["label"].casefold()
        or label != proof["label"].casefold()
    ):
        return None
    clauses[slot] = proof[0]
    return _render_messages(clauses)


def studio_revision_facts(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Render supported edits from user-authored clauses and bound evidence."""
    current = " ".join(text.split())
    users = [" ".join(turn.content.split()) for turn in history if turn.role == "user"][
        -4:
    ]
    return (
        _sound_reply(current, users)
        or _cessation_reply(current, users)
        or _message_reply(current, users[-1] if users else "")
    )
