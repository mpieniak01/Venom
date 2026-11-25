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
    r"(?:(?:gotową|krótką|zwięzłą|jedną)\s+){1,2}(?:wiadomość|prośbę|odpowiedź)"
    r"|odpowiedź\s+w\s+(?:moim|naszym)\s+imieniu)\b",
    re.I,
)
_DRAFT_EDIT = re.compile(r"^(?:dodaj|dopisz|popraw|zmień|skróć|usuń)\b", re.I)
_OTHER_FORMAT = re.compile(
    r"\b(?:wariant\w*|szablon\w*|opcje|wersje|wyślij|prześlij|zacytuj|"
    r"porównaj|przetłumacz|oprócz tego|przy okazji|zmień temat|zmieniam temat)\b",
    re.I,
)
_CONSENT = re.compile(r"(?:zgadzam się|udzielam zgody|wyrażam zgodę)\b", re.I)
_SENTENCE_BREAK = re.compile(r"[.!?]\s+")
_ROLE_REPLY = re.compile(
    r"(?:Teraz\s+(?:jestem|piszę jako|odpowiadam jako|wypowiadam się jako)"
    r"\s+[^.!?\n:]{2,100})\.\s*"
    r"(?P<consent>(?:Zgadzam się|Udzielam zgody|Wyrażam zgodę)\s+"
    r"(?:tylko\s+|wyłącznie\s+)?na\s+[^.!?\n:]{3,500})\.\s*"
    r"(?:Napisz|Ułóż|Przygotuj)\s+(?:krótką\s+)?odpowiedź\s+w moim imieniu[.!]?",
    re.I,
)
_ADDRESSEE = re.compile(r"\bdo\s+pan[ai]\s+[^\W\d_]{2,41}\b", re.I)
_END_WITH_QUESTION = re.compile(r"\bzakończ\s+pytaniem\b", re.I)
_DRAFT_OPENING = "Zwróć wyłącznie jedną krótką, gotową do użycia treść wiadomości. "
_USE_OF_RECIPIENT_WORK = re.compile(
    r"\bz prośbą o (?:odtworzenie|pokazanie|wystawienie|odczytanie|publikację|"
    r"udostępnienie)\s+(?:jej|jego)\b",
    re.I,
)
_PENDING_CONSENT = re.compile(
    r"\b(?:zgoda nie została|nie (?:ma|mam|mamy) zgody)\b", re.I
)
_OFFER_TO_PRESENT = re.compile(
    r"\b(?:odtworz(?:ę|ymy)|pokaż(?:ę|emy)|wystawi(?:ę|my)|odczyta(?:m|my)|"
    r"opublikuj(?:ę|emy)|udostępni(?:ę|my))\b",
    re.I,
)
_MESSAGE_BODY = (
    "Pomiń wstęp, temat, podpis i pola do uzupełnienia, chyba że użytkownik ich wymaga. "
    "Zachowaj fakty z wiadomości użytkownika i zastosuj ostatnią korektę. "
    "Pisz w imieniu osoby wskazanej w ostatnim poleceniu. Prośbę i dodatkowe ustalenia "
    "ujmij w osobnych zdaniach."
)
_CONSENT_HINT = (
    "Sformułuj samą zgodę w zdaniu oznajmującym. "
    "Wymień wprost jej przedmiot, termin, miejsce i pozostałe podane ograniczenia."
)
_QUESTION_HINT = "Zakończ wiadomość wymaganym pytaniem ze znakiem zapytania."


def role_consent_reply(text: str) -> str | None:
    """Use the consent the new speaker explicitly supplied, with all its limits."""
    if without_quotes(text) != text:
        return None
    match = _ROLE_REPLY.fullmatch(text.strip())
    return f"{match['consent']}." if match else None


def _message_hints(candidate: str, visible: str) -> str:
    hints = [_DRAFT_OPENING + _MESSAGE_BODY]
    if any(_CONSENT.match(sentence) for sentence in _SENTENCE_BREAK.split(visible)):
        hints.extend(
            [
                _CONSENT_HINT,
                "Zacznij od samej zgody, chyba że użytkownik wymaga zwrotu do odbiorcy.",
            ]
        )
    elif _ADDRESSEE.search(candidate):
        hints.append(
            "Jeśli podano imię adresata, użyj go w zwrocie na początku. Użyj poprawnej odmiany imienia."
        )
        if _USE_OF_RECIPIENT_WORK.search(candidate) and (
            _PENDING_CONSENT.search(candidate) or _OFFER_TO_PRESENT.search(visible)
        ):
            hints.append(
                "Nadawca prosi odbiorcę o zgodę, aby sam mógł wykonać czynność "
                "opisaną w prośbie. Zapytaj, czy nadawca może to zrobić. "
                "Nie proś odbiorcy o wykonanie tej czynności."
            )
    else:
        hints.append(
            "Zacznij od treści wiadomości. Uwzględnij zwrot do odbiorcy, jeśli użytkownik go wymaga."
        )
    if _END_WITH_QUESTION.search(visible):
        hints.append(_QUESTION_HINT)
    return " ".join(hints)


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
            return _message_hints(candidate, visible)
        if not _DRAFT_EDIT.match(candidate):
            break
    return ""
