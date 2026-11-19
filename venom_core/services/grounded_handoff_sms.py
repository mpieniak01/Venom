"""Render an explicitly agreed handoff as an SMS addressed to the recipient."""

from __future__ import annotations

import re

_CLOCK = r"(?:[01]\d|2[0-3]):[0-5]\d"
_PERSON = r"[^\W\d_][^\W\d_ -]{0,39}"
_DRAFT_REQUEST = re.compile(
    r"(?:zwróć|podaj|daj) (?:tylko|sam|wyłącznie) gotowy sms(?:,? bez tytułu)?[.!]?",
    re.IGNORECASE,
)
_FIRST = re.compile(
    rf"ułóż krótką wiadomość o (?P<kind>przekazaniu|odebraniu) (?P<item>[^.!?\n]+)\. "
    rf"mogę przyjść (?:po|o) {_CLOCK} i mam (?P<action>zostawić|odebrać) (?:go|ją|je|ich) "
    rf"(?P<relation>u|od) (?P<recipient>{_PERSON})[.]",
    re.IGNORECASE,
)
_CONFIRMATION = re.compile(
    rf"poproś (?P<recipient>{_PERSON}) o potwierdzenie, czy będzie (?:o|po) {_CLOCK}\. "
    r"nadal chodzi o (?P<item>[^\W\d_][^\W\d_ -]{0,59})\.",
    re.IGNORECASE,
)
_CORRECTION = re.compile(
    rf"(?:jednak )?nie obiecuj, że będę punktualnie\. "
    rf"zapytaj, czy (?P<preposition>po|o) (?P<time>{_CLOCK}) (?:mu|jej) pasuje[.]",
    re.IGNORECASE,
)
_ACT = {
    ("przekazaniu", "zostawić", "u"): "zostawię u Ciebie",
    ("odebraniu", "odebrać", "od"): "odbiorę od Ciebie",
}

# These explicit declensions are safe to bind; other names must match literally.
_ITEM_FORMS = (
    frozenset({"statyw", "statywu"}),
    frozenset({"pompa", "pompy", "pompę"}),
)


def _same_item(original: str, current: str) -> bool:
    first, second = original.casefold(), current.casefold()
    return first == second or any(
        first in forms and second in forms for forms in _ITEM_FORMS
    )


def handoff_sms_recap(message: str, users: tuple[str, ...]) -> str | None:
    """Keep the stated action and latest time for a recognized draft request."""
    if len(users) != 3 or not _DRAFT_REQUEST.fullmatch(" ".join(message.split())):
        return None
    original = _FIRST.fullmatch(" ".join(users[0].split()))
    confirmation = _CONFIRMATION.fullmatch(" ".join(users[1].split()))
    latest = _CORRECTION.fullmatch(" ".join(users[2].split()))
    if not original or not confirmation or not latest:
        return None
    if original["recipient"].casefold() != confirmation["recipient"].casefold():
        return None
    if not _same_item(original["item"], confirmation["item"]):
        return None
    action = _ACT.get(
        (
            original["kind"].casefold(),
            original["action"].casefold(),
            original["relation"].casefold(),
        )
    )
    if action is None:
        return None
    return (
        f"Cześć, czy pasuje Ci, jeśli {action} {confirmation['item']} "
        f"{latest['preposition'].lower()} {latest['time']}?"
    )
