"""Produce a short confirmation request from explicit user-authored facts."""

from __future__ import annotations

import re
from collections.abc import Sequence

from venom_core.services.chat_policy.direct_correction import (
    verified_reservation_return,
)

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
