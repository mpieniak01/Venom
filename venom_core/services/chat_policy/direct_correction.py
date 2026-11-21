"""Provide explicit, user-authored state updates to the native text adapter."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from venom_core.services.chat_policy.qualified_chat_quote import (
    single_quoted_operand,
    without_quotes,
)

_EDIT = re.compile(
    r"^\s*(?:przetłumacz|zacytuj|streść|porównaj|przepisz|przeformułuj|przeredaguj)\b",
    re.I,
)
_AMOUNT = re.compile(r"(?<![\w.,-])(\d{1,9}(?:[,.]\d{1,2})?)\s*(?:zł|PLN)\b", re.I)
_FEE = re.compile(r"\b(składk|kaucj|opłat|cen|kwot)\w*\b", re.I)
_INITIAL = re.compile(r"^\s*(?:szykuję|ustalam|rezerwację|obowiązuje)\b", re.I)
_PROPOSAL = re.compile(
    r"(?:^|[.!?]\s+)(?:proponuję|ktoś zaproponował|ktoś proponuje)\b", re.I
)
_REJECT = re.compile(r"(?:^|[.!?]\s+)odrzucam\s+(?:podwyżkę|propozycję|zmianę)\b", re.I)
_ACCEPT = re.compile(
    r"(?:^|[.!?]\s+)(?:zatwierdzam|akceptuję|przyjmuję)\s+"
    r"(?:składkę|kaucję|opłatę|cenę|kwotę|propozycję)\b",
    re.I,
)
_SOURCE = re.compile(r"\b(?:ulotk|kartk|kartc|karc|kartę)\w*\b", re.I)
_SOURCE_QUERY = re.compile(
    r"\b(?:sam[aej]\s+(?:ulotk|kartk|kartc|karc)\w*|z\s+(?:kartk|kartc|ulotk)\w*)\b",
    re.I,
)
_CLOSED_SOURCE = re.compile(r"\b(?:tylko|samym tekstem|wyłącznie)\b", re.I)
_NUMBER_ON_CARD = re.compile(r"\bnumer\s+(?:szafki|rezerwacji)\b", re.I)
_NAME = r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+"
_BOUNDED_NAME = rf"{_NAME}(?:[ \t]+{_NAME}){{0,3}}"
_SINGLE_LABELED_FIELD = re.compile(
    rf"\s*(?i:opiekunka|opiekun|osoba|sala)\s*:\s*{_BOUNDED_NAME}\s*"
)
_LOCATION_ONLY = re.compile(rf"\s*(?i:sala)\s+{_BOUNDED_NAME}\s*")
_STATE_QUERY = re.compile(r"\b(?:ustalen\w*|obowiązuj\w*|wiążąc\w*)\b", re.I)
_CANCEL_REGISTRATION = re.compile(
    r"^\s*(?:zapisy (?:jednak )?odwołane|odwołuję zapisy|rezygnuję z zapisów)"
    r"(?=\s*[.!?]|\s*$)",
    re.I,
)
_REQUIRES_REGISTRATION = re.compile(
    r"\b(?:trzeba się zapisać|zapisy (?:są )?obowiązkowe)\b", re.I
)
_FREE_ADMISSION = re.compile(r"\bwstęp (?:jest |nadal )?wolny\b", re.I)

_INVITATION_TASK = re.compile(
    r"\b(?:przeredaguj|popraw|uaktualnij|napisz|przygotuj)\s+(?:to\s+)?"
    r"(?:zaproszenie|ogłoszenie)\b",
    re.I,
)
_NO_REGISTRATION = re.compile(
    r"\b(?:bez zapisów|zapisy (?:są |zostały )?odwołane|"
    r"(?:zapisy|rejestracja) nie (?:są|jest) wymagan[ea]|"
    r"nie (?:trzeba|musisz) się (?:zapisać|zapisywać|rejestrować))\b",
    re.I,
)
_REGISTRATION = re.compile(r"\b(?:zapis\w*|zapisać|rejestr\w*)\b", re.I)
_INVITATION = re.compile(r"\bzaprasza(?:m|my)\b", re.I)
_UNSAFE_INVITATION_DETAIL = re.compile(
    r"\b(?:poczęstun\w*|darmow\w*|bezpłatn\w*|odpłatn\w*|bilet\w*|"
    r"wstęp|płatn\w*|opłat\w*|składk\w*|kaucj\w*|zł|PLN)\b",
    re.I,
)


@dataclass(frozen=True)
class CorrectionContext:
    scope: str
    text: str
    free_admission: bool = False


@dataclass
class _FeeState:
    field: str | None = None
    binding: str | None = None
    proposed: str | None = None
    decision: bool = False

    def read(self, text: str) -> None:
        fields = {match.lower() for match in _FEE.findall(text)} - {"kwot"}
        if len(fields) > 1:
            self.field = self.binding = self.proposed = None
            self.decision = False
            return
        field = next(iter(fields), self.field)
        if self.field is not None and field != self.field:
            self.binding = self.proposed = None
            self.decision = False
        self.field = field
        amounts = _AMOUNT.findall(text)
        amount = amounts[0] if len(amounts) == 1 else None
        if _REJECT.search(text) and self.proposed is not None:
            self.proposed = None
            self.decision = True
        elif _ACCEPT.search(text) and (accepted := amount or self.proposed):
            self.binding, self.proposed, self.decision = accepted, None, True
        elif _PROPOSAL.search(text) and amount:
            self.proposed, self.decision = amount, False
        elif self.field is not None and amount and _INITIAL.search(text):
            self.binding, self.proposed, self.decision = amount, None, False


def correction_context(
    content: str, preceding_users: Sequence[str]
) -> CorrectionContext | None:
    """Annotate an explicit update without rewriting prior messages or executing tools."""
    visible = without_quotes(content)
    if _EDIT.match(visible):
        return None
    previous = [
        without_quotes(text) for text in preceding_users[-6:] if not _EDIT.match(text)
    ]
    source = single_quoted_operand(content)
    if (
        source
        and _SOURCE.search(visible)
        and _SOURCE_QUERY.search(visible)
        and _CLOSED_SOURCE.search(visible)
    ):
        absent = ""
        if _LOCATION_ONLY.fullmatch(source) and _FEE.search(visible):
            absent = " Sama karta nie podaje kwoty."
        elif _SINGLE_LABELED_FIELD.fullmatch(source) and _NUMBER_ON_CARD.search(
            visible
        ):
            absent = " Sama karta nie podaje numeru."
        return CorrectionContext(
            "source_only",
            "Pytanie dotyczy wyłącznie zacytowanej karty. Odczytaj jej treść. "
            "Dla pola, którego tam nie ma, napisz «brak danych». Nie uzupełniaj pól z rozmowy."
            + absent,
        )
    if (
        _CANCEL_REGISTRATION.match(visible)
        and _INVITATION_TASK.search(visible)
        and any(_REQUIRES_REGISTRATION.search(text) for text in previous)
    ):
        free_admission = bool(_FREE_ADMISSION.search(visible))
        admission = " Wstęp jest wolny." if free_admission else ""
        return CorrectionContext(
            "registration_cancelled",
            "Aktualne ustalenie użytkownika: zapisy zostały odwołane. "
            "Zaproszenie ma jasno mówić, że nie trzeba się zapisywać." + admission,
            free_admission=free_admission,
        )
    if not (
        _STATE_QUERY.search(visible)
        or _ACCEPT.search(visible)
        or _REJECT.search(visible)
    ):
        return None
    if not (
        _FEE.search(visible) or _ACCEPT.search(visible) or _REJECT.search(visible)
    ) and not (
        previous
        and any(
            pattern.search(previous[-1]) for pattern in (_ACCEPT, _REJECT, _PROPOSAL)
        )
    ):
        return None
    state = _FeeState()
    for message in [*previous, visible]:
        state.read(message)
    if state.binding is None or not state.decision:
        return None
    return CorrectionContext(
        "binding_fee",
        f"Obowiązująca kwota przekazana przez użytkownika: {state.binding} zł. "
        "Podaj tę wiążącą kwotę. Zachowaj pozostałe ustalenia użytkownika, "
        "których nowsza wiadomość nie zmienia. Odróżnij kartę od ustaleń w rozmowie.",
    )


def corrected_registration_reply(context: CorrectionContext, reply: str) -> str | None:
    """Publish an explicit waiver if the draft fails to honor the latest decision."""
    if context.scope != "registration_cancelled":
        return None
    if (
        _NO_REGISTRATION.search(reply)
        and not _REGISTRATION.search(_NO_REGISTRATION.sub("", reply))
        and (not context.free_admission or _FREE_ADMISSION.search(reply))
    ):
        return None
    sentences = re.split(r"(?<=[.!?])\s+", reply.strip())
    invitation = next(
        (
            sentence
            for sentence in sentences
            if _INVITATION.search(sentence)
            and not _REGISTRATION.search(sentence)
            and not _UNSAFE_INVITATION_DETAIL.search(sentence)
            and sentence.endswith((".", "!"))
        ),
        "Zapraszamy do udziału.",
    )
    admission = (
        "Wstęp jest wolny i nie trzeba się zapisywać."
        if context.free_admission
        else "Zapisy nie są wymagane."
    )
    revised = f"{invitation} {admission}"
    return revised if revised != reply else None
