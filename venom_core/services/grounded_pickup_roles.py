"""Bind the point, historic signature and scheduled pickup to separate cards."""

from __future__ import annotations

import re
from dataclasses import dataclass

from venom_core.services.grounded_dialogue import (
    EvidenceError,
    PublishedAnswer,
    SourceDocument,
    SourceQuote,
    requested_card_ids,
    text_hash,
)

_PICKUP_DAY = {
    "poniedziałkowy": "w poniedziałek",
    "wtorkowy": "we wtorek",
    "środowy": "w środę",
    "czwartkowy": "w czwartek",
    "piątkowy": "w piątek",
    "sobotni": "w sobotę",
    "niedzielny": "w niedzielę",
}
_DAY = "|".join(_PICKUP_DAY.values())
_CARD = r"kartę (?:\[[\w.-]{1,64}\]|[\w.-]{1,64})"
_TWO_CARDS = rf"(?:przeczytaj|sprawdź) {_CARD} (?:i|oraz) {_CARD}"
_POINT_REQUEST = re.compile(
    rf"{_TWO_CARDS}\. podaj nazwę punktu i kto odbiera tam (?:nowy )?komplet (?P<day>{_DAY})",
    re.IGNORECASE,
)
_SIGNER_REQUEST = re.compile(
    rf"nie o odbierając(?:ą|ego) chodzi, tylko kto podpisał zamknięcie przeglądu\. {_TWO_CARDS}",
    re.IGNORECASE,
)
_FINAL_REQUEST = re.compile(
    rf"podaj dwie linie: punkt i osoba odbierająca (?P<day>{_DAY})",
    re.IGNORECASE,
)

_NAME_WORD = r"[^\W\d_]+(?:[-\u2019\x27][^\W\d_]+)*"
_POINT = rf"(?P<point>{_NAME_WORD}(?: {_NAME_WORD}){{0,4}})"
_LABEL_REQUEST = re.compile(
    r"(?:chcę odnaleźć osobę odbierającą komplet|szukam odbierającego nowy komplet)\. "
    rf"na etykiecie widnieje nazwa punktu {_POINT}",
    re.IGNORECASE,
)
_MONTH = (
    r"stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|"
    r"września|października|listopada|grudnia"
)
_HISTORY_CARD = re.compile(
    rf"punkt (?:wydawania|odbioru) nosi (?:oficjalną )?nazwę {_POINT}\. "
    rf"(?P<signature>{_NAME_WORD} {_NAME_WORD} (?:[1-9]|[12][0-9]|3[01]) (?:{_MONTH}) "
    r"podpisał(?:a)? zamknięcie przeglądu (?:starego|poprzedniego) kompletu\.) "
    r"(?:wzmianka nie dotyczy przyszłych wydawań|podpis dotyczy wyłącznie tego przeglądu)\.",
    re.IGNORECASE,
)
_PICKUP_CARD = re.compile(
    rf"(?P<day>{'|'.join(_PICKUP_DAY)}) odbiór nowego kompletu przewidziano "
    rf"w punkcie {_POINT}; osoba odbierająca wymaga potwierdzenia\."
    r"(?: komplet pozostaje zabezpieczony do chwili potwierdzenia\.)?",
    re.IGNORECASE,
)


def _request_text(message: str) -> str:
    return " ".join(message.split()).rstrip(".?!")


def pickup_label_guidance(message: str) -> str:
    if _LABEL_REQUEST.fullmatch(_request_text(message)):
        return (
            "Przytocz dosłownie nazwę punktu z etykiety i wyjaśnij, że tożsamość "
            "osoby odbierającej pozostaje nieustalona."
        )
    return ""


@dataclass(frozen=True)
class PickupRoles:
    point: str
    weekday: str
    signature: str
    historical: SourceQuote
    scheduled: SourceQuote

    def reply(self, *, signer_requested: bool) -> str:
        point = f"Punkt: {self.point} [{self.historical.source_id}]."
        signature = f"{self.signature} [{self.historical.source_id}]"
        status = (
            f"Osoba odbierająca nowy komplet {self.weekday} "
            f"wymaga potwierdzenia [{self.scheduled.source_id}]."
        )
        return (
            f"{signature} {status}"
            if signer_requested
            else f"{point} {status} {signature}"
        )


def _literal_quote(document: SourceDocument) -> SourceQuote:
    return SourceQuote(
        document.ref.source_id, document.ref.version, document.text.strip()
    )


def _valid_pickup_document(document: SourceDocument) -> bool:
    return (
        document.complete
        and document.available
        and not document.superseded
        and len(document.text) <= 640
        and text_hash(document.text) == document.ref.sha256
    )


def bind_pickup_roles(
    message: str, documents: tuple[SourceDocument, ...]
) -> tuple[PickupRoles, bool] | None:
    """Project facts only when the two named, complete cards match the family."""
    normalized = _request_text(message)
    point_request = _POINT_REQUEST.fullmatch(normalized)
    signer_requested = _SIGNER_REQUEST.fullmatch(normalized) is not None
    if not (point_request or signer_requested) or len(documents) != 2:
        return None
    if {d.ref.source_id for d in documents} != set(requested_card_ids(message)):
        return None
    historical: tuple[SourceDocument, re.Match[str]] | None = None
    scheduled: tuple[SourceDocument, re.Match[str]] | None = None
    for document in documents:
        if not _valid_pickup_document(document):
            return None
        content = " ".join(document.text.split())
        if history_match := _HISTORY_CARD.fullmatch(content):
            historical = (document, history_match)
        elif pickup_match := _PICKUP_CARD.fullmatch(content):
            scheduled = (document, pickup_match)
    if historical is None or scheduled is None:
        return None
    history_doc, history_match = historical
    pickup_doc, pickup_match = scheduled
    weekday = _PICKUP_DAY[pickup_match["day"].casefold()]
    if history_match["point"].casefold() != pickup_match["point"].casefold() or (
        point_request is not None and point_request["day"].casefold() != weekday
    ):
        raise EvidenceError("pilot_pickup_roles_inconsistent")
    return (
        PickupRoles(
            history_match["point"],
            weekday,
            history_match["signature"],
            _literal_quote(history_doc),
            _literal_quote(pickup_doc),
        ),
        signer_requested,
    )


@dataclass(frozen=True)
class PickupRolesReceipt:
    """Session snapshot of card claims certified in an explicit source turn.

    Plain output does not fetch cards. A later explicit source turn is needed
    to rebind updated cards to a new snapshot.
    """

    users: tuple[str, ...]
    roles: PickupRoles

    def recap(self, message: str, users: tuple[str, ...]) -> str | None:
        request = _FINAL_REQUEST.fullmatch(_request_text(message))
        if request is None:
            return None
        weekday = request["day"].casefold()
        if users != self.users or weekday != self.roles.weekday:
            return (
                f"Punkt: brak potwierdzenia.\n"
                f"Osoba odbierająca {weekday}: brak potwierdzenia."
            )
        return (
            f"Punkt: {self.roles.point}.\nOsoba odbierająca {weekday}: niepotwierdzona."
        )


@dataclass(frozen=True)
class PilotPickupRolesAnswer(PublishedAnswer):
    pickup_roles_receipt: PickupRolesReceipt
