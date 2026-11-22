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
_AMOUNT = re.compile(
    r"(?<![\w.,-])(?<!\d[ \u00a0\u202f])"
    r"(\d{1,3}(?:[ \u00a0\u202f]+\d{3}){1,2}(?:[,.]\d{1,2})?"
    r"|\d{1,9}(?:[,.]\d{1,2})?)\s*(?:zł|PLN)\b",
    re.I,
)
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
_FEE_NOMINATIVE = r"(?:składka|kaucja|opłata|cena)"
_FEE_ACCUSATIVE = r"(?:składkę|kaucję|opłatę|cenę)"
_PENDING_PROPOSAL = re.compile(
    rf"(?:proponuję|ktoś zaproponował|ktoś proponuje)\s+{_FEE_ACCUSATIVE}\s+"
    rf"{_AMOUNT.pattern}(?:[.!]\s*|$)",
    re.I,
)
_PENDING_MARKER = re.compile(
    r"to (?:na razie sugestia|na razie propozycja|tylko propozycja)\.\s*", re.I
)
_CURRENT_FEE_QUERY = re.compile(
    rf"(?:jaką {_FEE_ACCUSATIVE} mam wpisać do aktualnych ustaleń"
    rf"|jaka {_FEE_NOMINATIVE} (?:obowiązuje|jest aktualna)"
    rf"|ile (?:obecnie wynosi|wynosi obecnie) {_FEE_NOMINATIVE}"
    rf"|ile wynosi teraz {_FEE_NOMINATIVE} za wstęp dla jednej osoby)\s*\?",
    re.I,
)
_FEE_ENTRY = r"(?:wejście|wstęp|bilet)"
_PER_PERSON = r"(?:za (?:jedną )?osobę|na (?:jedną )?osobę|od osoby)"
_ACCEPTED_FEE_QUESTION = re.compile(
    rf"(?:zatwierdzam|akceptuję|przyjmuję)\s+(?P<field>{_FEE_ACCUSATIVE})"
    rf"(?:\s+za (?P<subject>{_FEE_ENTRY}))?\s+(?:w wysokości\s+)?"
    rf"(?P<amount>{_AMOUNT.pattern})(?:\s+(?P<unit>{_PER_PERSON}))?"
    r"\s*[.!]\s+(?P<question>[^.!?]+\?)",
    re.I,
)
_ENTRY_FEE_QUESTION = re.compile(
    rf"ile (?:teraz |obecnie )?kosztuje (?P<subject>{_FEE_ENTRY})"
    rf"\s+(?:dla (?:jednej )?osoby|{_PER_PERSON})\s*\?",
    re.I,
)
_ENTRY_SUBJECT = re.compile(rf"\b{_FEE_ENTRY}\b", re.I)
_PER_PERSON_UNIT = re.compile(rf"\s+{_PER_PERSON}\b", re.I)
_FEE_UNCERTAINTY = re.compile(r"\b(?:nie|może|prawdopodobnie)\b", re.I)
_SOURCE = re.compile(r"\b(?:ulotk|kartk|kartc|karc|kartę)\w*\b", re.I)
_SOURCE_QUERY = re.compile(
    r"\b(?:sam[aej]\s+(?:ulotk|kartk|kartc|karc)\w*|z\s+(?:kartk|kartc|ulotk)\w*)\b",
    re.I,
)
_CLOSED_SOURCE = re.compile(r"\b(?:tylko|samym tekstem|wyłącznie)\b", re.I)
_CARD_NUMBER = r"numer\s+(?:szafki|rezerwacji)"
_NUMBER_ON_CARD = re.compile(rf"\b{_CARD_NUMBER}\b", re.I)
_NAME = r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+"
_BOUNDED_NAME = rf"{_NAME}(?:[ \t]+{_NAME}){{0,3}}"
_SINGLE_LABELED_FIELD = re.compile(
    rf"\s*(?P<label>(?i:opiekunka|opiekun|osoba|sala))\s*:\s*"
    rf"(?P<value>{_BOUNDED_NAME})\s*"
)
_LOCATION_ONLY = re.compile(rf"\s*(?i:sala)\s+{_BOUNDED_NAME}\s*")
_COMPLETE_NUMBER_CARD = re.compile(
    r"(?:^|[.!?]\s+)(?:na (?:aktualnej )?kartce (?:jest|widnieje) "
    r"(?:tylko|wyłącznie)(?: napis)?|mam (?:też )?kartkę z samym tekstem)"
    r'\s*:?\s*(?:„[^”]+”|«[^»]+»|"[^"\n]+")\s*\.\s*'
    r"(?P<question>[^.!?]+[.!?]?)\s*\Z",
    re.I,
)
_CARD_NUMBER_QUERY = re.compile(
    r"(?:odczytaj|podaj)\s+(?:z kartki\s+)?"
    r"(?:(?P<label>opiekuna|opiekunkę|osobę|salę)\s+i\s+)?"
    rf"(?P<number>{_CARD_NUMBER})(?:\s+z kartki)?"
    r"(?:,\s*wskazując brakujące dane)?[.!?]?",
    re.I,
)
_CARD_LABELS = {
    "opiekuna": "opiekun",
    "opiekunkę": "opiekunka",
    "osobę": "osoba",
    "salę": "sala",
}
_RETURN_TO_RESERVATION = re.compile(
    r"(?:teraz korzystaj z ustaleń (?:naszej )?rozmowy|"
    r"wróć do ustaleń (?:naszej )?rozmowy)\.\s+"
    r"(?:jaki jest (?:rzeczywisty )?numer rezerwacji i kto jest opiekunem\?"
    r"|podaj numer rezerwacji i opiekuna\.?|podaj opiekuna i numer rezerwacji\.?)",
    re.I,
)
_RESERVATION_RECORD = re.compile(
    r"(?i:(?:na zajęcia (?:w|we) [a-ząćęłńóśźż-]+ )?"
    r"(?:na warsztaty [a-ząćęłńóśźż-]+ )?mam rezerwację )(?P<number>[0-9]{1,12})\.\s+"
    rf"(?i:(?:opiekunem|opiekunką) jest )(?P<name>{_BOUNDED_NAME})\."
    r"(?:\s+(?i:zrób krótką notatkę z tymi dwiema danymi|podaj obie dane w krótkiej notatce)\.)?"
)
_OTHER_RESERVATION = re.compile(r"\b(?:rezerwacj|opiekun)\w*\b", re.I)
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
    verified_reply: str | None = None


def _question_in_clause(text: str, start: int) -> bool:
    """Return whether the clause starting at ``start`` is phrased as a question."""
    terminator = _clause_terminator(text, start)
    return terminator is not None and terminator.group() == "?"


def _clause_terminator(text: str, start: int) -> re.Match[str] | None:
    """Find sentence punctuation while allowing decimal points in amounts."""
    return re.search(r"(?<!\d)\.(?!\d)|[!?]", text[start:])


@dataclass
class _FeeState:
    field: str | None = None
    binding: str | None = None
    proposed: str | None = None
    decision: bool = False

    def read(self, text: str) -> None:
        if not self._read_field(text):
            return
        if self._read_rejection(text):
            return
        if self._read_acceptance(text):
            return
        if self._read_proposal(text):
            return
        self._read_initial_binding(text)

    def _read_field(self, text: str) -> bool:
        fields = {match.lower() for match in _FEE.findall(text)} - {"kwot"}
        if len(fields) > 1:
            self.field = self.binding = self.proposed = None
            self.decision = False
            return False
        field = next(iter(fields), self.field)
        if self.field is not None and field != self.field:
            self.binding = self.proposed = None
            self.decision = False
        self.field = field
        return True

    def _read_rejection(self, text: str) -> bool:
        if _REJECT.search(text) and self.proposed is not None:
            self.proposed = None
            self.decision = True
            return True
        return False

    def _read_acceptance(self, text: str) -> bool:
        acceptance = _ACCEPT.search(text)
        if acceptance is None or _question_in_clause(text, acceptance.start()):
            return False
        clause = text[acceptance.start() :]
        terminator = _clause_terminator(text, acceptance.start())
        if terminator is not None:
            clause = text[acceptance.start() : acceptance.start() + terminator.end()]
        amounts = _AMOUNT.findall(clause)
        if len(amounts) == 1:
            accepted = amounts[0]
        elif not amounts:
            accepted = self.proposed
        else:
            accepted = None
        if accepted is not None:
            self.binding, self.proposed, self.decision = accepted, None, True
        return True

    def _read_proposal(self, text: str) -> bool:
        amounts = _AMOUNT.findall(text)
        if _PROPOSAL.search(text) and len(amounts) == 1:
            self.proposed, self.decision = amounts[0], False
            return True
        return False

    def _read_initial_binding(self, text: str) -> None:
        initial = _INITIAL.search(text)
        amounts = _AMOUNT.findall(text)
        if (
            self.field is not None
            and len(amounts) == 1
            and initial is not None
            and not _question_in_clause(text, initial.start())
        ):
            self.binding, self.proposed, self.decision = amounts[0], None, False


def _verified_number_card_reply(source: str, content: str) -> str | None:
    """Read a closed one-field card without using any conversation values."""
    field = _SINGLE_LABELED_FIELD.fullmatch(source)
    declaration = _COMPLETE_NUMBER_CARD.search(content)
    if not field or not declaration:
        return None
    question = declaration["question"].strip()
    query = _CARD_NUMBER_QUERY.fullmatch(question)
    if not query or not _SOURCE_QUERY.search(question):
        return None
    number = " ".join(query["number"].lower().split()).capitalize()
    if query["label"] is None:
        return f"{number}: brak danych."
    label = field["label"].casefold()
    if _CARD_LABELS[query["label"].casefold()] != label:
        return None
    return f"{label.capitalize()}: {field['value']}. {number}: brak danych."


def verified_reservation_return(
    content: str, preceding_users: Sequence[str]
) -> tuple[str, str] | None:
    """Read the number and caregiver for an explicit return to verified history."""
    if (
        not _RETURN_TO_RESERVATION.fullmatch(content.strip())
        or len(preceding_users) < 2
    ):
        return None
    record, card = preceding_users[-2:]
    reservation = _RESERVATION_RECORD.fullmatch(record.strip())
    source = single_quoted_operand(card)
    if (
        reservation is None
        or source is None
        or _EDIT.match(without_quotes(card))
        or any(
            _OTHER_RESERVATION.search(without_quotes(user))
            for user in preceding_users[-6:-2]
        )
    ):
        return None
    name, number = reservation["name"], reservation["number"]
    if (
        _verified_number_card_reply(source, card)
        != f"Opiekun: {name}. Numer rezerwacji: brak danych."
    ):
        return None
    return number, name


def _reservation_from_conversation(
    content: str, preceding_users: Sequence[str]
) -> CorrectionContext | None:
    reservation = verified_reservation_return(content, preceding_users)
    if reservation is None:
        return None
    number, name = reservation
    return CorrectionContext(
        "binding_reservation",
        "Pytanie dotyczy ustaleń rozmowy o rezerwacji.",
        verified_reply=f"Numer rezerwacji: {number}. Opiekun: {name}.",
    )


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
    context = _source_card_context(visible, content, source)
    if context is not None:
        return context
    context = _cancelled_registration_context(visible, previous)
    if context is not None:
        return context
    if visible == content:
        context = _conversation_fact_context(visible, preceding_users)
        if context is not None:
            return context
    if not _is_fee_state_request(visible):
        return None
    state = _fee_state_from_history(visible, previous)
    if state is None or state.binding is None or not state.decision:
        return None
    return CorrectionContext(
        "binding_fee",
        f"Obowiązująca kwota przekazana przez użytkownika: {state.binding} zł. "
        "Podaj tę wiążącą kwotę. Zachowaj pozostałe ustalenia użytkownika, "
        "których nowsza wiadomość nie zmienia. Odróżnij kartę od ustaleń w rozmowie.",
    )


def _source_card_context(
    visible: str, content: str, source: str | None
) -> CorrectionContext | None:
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
            verified_reply=_verified_number_card_reply(source, content),
        )
    return None


def _cancelled_registration_context(
    visible: str, previous: Sequence[str]
) -> CorrectionContext | None:
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
    return None


def _conversation_fact_context(
    visible: str, preceding_users: Sequence[str]
) -> CorrectionContext | None:
    for resolver in (
        _reservation_from_conversation,
        _accepted_fee_context,
        _pending_fee_context,
    ):
        context = resolver(visible, preceding_users)
        if context is not None:
            return context
    return None


def _is_fee_state_request(visible: str) -> bool:
    return bool(
        _STATE_QUERY.search(visible)
        or _ACCEPT.search(visible)
        or _REJECT.search(visible)
    )


def _fee_state_from_history(visible: str, previous: Sequence[str]) -> _FeeState | None:
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
    return state


def _proposal_question(text: str) -> tuple[str, str]:
    proposal = _PENDING_PROPOSAL.match(text)
    if proposal is None:
        return "", text
    suffix = text[proposal.end() :]
    marker = _PENDING_MARKER.match(suffix)
    return proposal[0], suffix[marker.end() :] if marker else suffix


def _accepted_fee_reference(field: str, preceding_users: Sequence[str]) -> str:
    if not preceding_users:
        return ""
    prior = without_quotes(preceding_users[-1]).strip()
    proposal, question = _proposal_question(prior)
    if proposal:
        proposed_field = _FEE.search(proposal)
        if (
            len(preceding_users) < 2
            or not proposed_field
            or proposed_field[1].casefold() != field
            or (question and not _CURRENT_FEE_QUERY.fullmatch(question))
        ):
            return ""
        prior = without_quotes(preceding_users[-2]).strip()
    if _FEE_UNCERTAINTY.search(prior):
        return ""
    state = _FeeState()
    state.read(prior)
    return prior if state.field == field and state.binding is not None else ""


def _accepted_fee_context(
    content: str, preceding_users: Sequence[str]
) -> CorrectionContext | None:
    """Answer a single explicit fee question from the user's current decision."""
    decision = _ACCEPTED_FEE_QUESTION.fullmatch(content.strip())
    if decision is None:
        return None
    field = _FEE.search(decision["field"])
    amount = _AMOUNT.fullmatch(decision["amount"])
    if field is None or amount is None:
        return None
    category = field[1].casefold()
    prior = _accepted_fee_reference(category, preceding_users)
    prior_amount = _AMOUNT.search(prior)
    known_subjects = {item.casefold() for item in _ENTRY_SUBJECT.findall(prior)}
    subject = (decision["subject"] or "").casefold() or None
    per_person = _accepted_fee_is_per_person(
        decision["unit"], prior_amount, prior, subject, known_subjects
    )
    question = decision["question"]
    if not _accepted_fee_question_matches(
        question, category, per_person, subject, known_subjects
    ):
        return None
    unit = " za osobę" if per_person else ""
    reply = f"Obowiązuje {amount[1]} zł{unit}."
    return CorrectionContext("binding_fee", reply, verified_reply=reply)


def _accepted_fee_is_per_person(
    unit: str | None,
    prior_amount: re.Match[str] | None,
    prior: str,
    subject: str | None,
    known_subjects: set[str],
) -> bool:
    return bool(
        unit
        or (
            prior_amount
            and (subject is None or known_subjects == {subject})
            and _PER_PERSON_UNIT.match(prior, prior_amount.end())
        )
    )


def _accepted_fee_question_matches(
    question: str,
    category: str,
    per_person: bool,
    subject: str | None,
    known_subjects: set[str],
) -> bool:
    entry = _ENTRY_FEE_QUESTION.fullmatch(question)
    if entry is not None:
        subjects = {subject} if subject else known_subjects
        return per_person and subjects == {entry["subject"].casefold()}
    requested = _FEE.search(question)
    if not _CURRENT_FEE_QUERY.fullmatch(question) or requested is None:
        return False
    if requested[1].casefold() != category:
        return False
    return "dla jednej osoby" not in question.casefold() or per_person


def _pending_fee_context(
    content: str, preceding_users: Sequence[str]
) -> CorrectionContext | None:
    proposal, question = _proposal_question(content.strip())
    if not preceding_users or _CURRENT_FEE_QUERY.fullmatch(question) is None:
        return None
    confirmation = preceding_users[-1]
    if not proposal and len(preceding_users) >= 2:
        proposal, previous_question = _proposal_question(confirmation.strip())
        if (
            previous_question
            and _CURRENT_FEE_QUERY.fullmatch(previous_question) is None
        ):
            return None
        confirmation = preceding_users[-2]
    if not proposal:
        return None

    confirmation = without_quotes(confirmation)
    if _FEE_UNCERTAINTY.search(confirmation):
        return None
    requested = _FEE.search(question)
    proposed = _FEE.search(proposal)
    if not requested or not proposed or requested[1].lower() != proposed[1].lower():
        return None
    state = _FeeState()
    state.read(confirmation)
    if state.binding is None or state.field != requested[1].lower():
        return None
    state.read(proposal)
    if state.proposed is None:
        return None

    reply = (
        f"Obowiązuje {state.binding} zł. "
        f"Kwota {state.proposed} zł jest propozycją do zatwierdzenia."
    )
    return CorrectionContext("pending_fee", reply, verified_reply=reply)


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
