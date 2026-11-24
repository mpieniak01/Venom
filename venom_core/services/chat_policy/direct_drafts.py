"""Prepare bounded confirmation drafts and guide ordinary short messages."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.direct_correction import (
    verified_reservation_return,
)
from venom_core.services.chat_policy.qualified_chat_quote import without_quotes

_CONFIRMATION_DRAFT = re.compile(
    r"(?:przygotuj|napisz|ułóż)\s+(?:krótką\s+)?wiadomość"
    r"(?:\s+do\s+opiekuna)?\s+z\s+prośbą\s+o\s+potwierdzenie\s+rezerwacji"
    r"(?:\.\s+(?:podaj|zwróć)\s+(?:tylko|wyłącznie)\s+treść(?:\s+wiadomości)?"
    r"(?:\s+i\s+użyj\s+(?:właściwego|jej)\s+numeru)?)?[.!]?",
    re.I,
)


def reservation_confirmation_draft(
    content: str, preceding_users: Sequence[str]
) -> str | None:
    """Draft a request for the reservation last verified by the user."""
    if not preceding_users or not _CONFIRMATION_DRAFT.fullmatch(content.strip()):
        return None
    reservation = verified_reservation_return(preceding_users[-1], preceding_users[:-1])
    if reservation is None:
        return None
    number, _ = reservation
    return f"Dzień dobry, proszę o potwierdzenie rezerwacji nr {number}."


_SHORT_MESSAGE = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?:napisz|ułóż|przygotuj)\s+(?:"
    r"(?:gotową|krótką|zwięzłą|jedną)\s+(?:wiadomość|prośbę|odpowiedź)"
    r"|odpowiedź\s+w\s+(?:moim|naszym)\s+imieniu)\b",
    re.I,
)
_DRAFT_EDIT = re.compile(r"^(?:dodaj|dopisz|popraw|zmień|skróć|usuń)\b", re.I)
_OTHER_FORMAT = re.compile(
    r"\b(?:wariant\w*|szablon\w*|opcje|wersje|wyślij|prześlij|zacytuj|"
    r"porównaj|przetłumacz|oprócz tego|przy okazji|zmień temat|zmieniam temat)\b",
    re.I,
)
_CONSENT = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?:zgadzam się|udzielam zgody|wyrażam zgodę)\b", re.I
)
_END_WITH_QUESTION = re.compile(r"\bzakończ\s+pytaniem\b", re.I)
_MESSAGE_HINT = (
    "Zwróć wyłącznie jedną krótką, gotową do użycia treść wiadomości. "
    "Jeśli podano imię adresata, użyj go w zwrocie na początku. "
    "Pomiń wstęp, temat, podpis i pola do uzupełnienia, chyba że użytkownik ich wymaga. "
    "Zachowaj fakty z wiadomości użytkownika i zastosuj ostatnią korektę. "
    "Pisz w imieniu osoby wskazanej w ostatnim poleceniu. Prośbę i dodatkowe ustalenia "
    "ujmij w osobnych zdaniach. Użyj poprawnej odmiany imienia."
)
_CONSENT_HINT = (
    "Sformułuj samą zgodę w zdaniu oznajmującym. "
    "Wymień wprost jej przedmiot, termin, miejsce i pozostałe podane ograniczenia."
)
_QUESTION_HINT = "Zakończ wiadomość wymaganym pytaniem ze znakiem zapytania."


def short_message_hint(text: str, history: Sequence[HistoryMessage]) -> str:
    """Carry the requested draft form through a contiguous sequence of edits."""
    visible = without_quotes(text).strip()
    for candidate in [
        visible,
        *(
            without_quotes(t.content).strip()
            for t in reversed(history)
            if t.role == "user"
        ),
    ]:
        if _OTHER_FORMAT.search(candidate):
            break
        if _SHORT_MESSAGE.search(candidate):
            hints = [_MESSAGE_HINT]
            if _CONSENT.search(visible):
                hints.append(_CONSENT_HINT)
            if _END_WITH_QUESTION.search(visible):
                hints.append(_QUESTION_HINT)
            return " ".join(hints)
        if not _DRAFT_EDIT.match(candidate):
            break
    return ""
