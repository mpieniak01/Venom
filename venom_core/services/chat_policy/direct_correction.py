"""Provide explicit, user-authored state updates to the native text adapter."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from venom_core.services.chat_policy.direct_event_state import event_state_reply
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
_ONE_PERSON_TEXT = "dla jednej osoby"
_PER_PERSON_SUFFIX = " za osobę"
_PER_PERSON = r"(?:za (?:jedną )?osobę|na (?:jedną )?osobę|od osoby)"
_GROUP = r"(?:za (?:całą grupę|grupę|wszystkich)|dla (?:całej grupy|grupy|wszystkich))"
_PENDING_PROPOSAL = re.compile(
    rf"(?:proponuję|ktoś zaproponował|ktoś proponuje)\s+{_FEE_ACCUSATIVE}\s+"
    rf"{_AMOUNT.pattern}(?:\s+(?:{_PER_PERSON}|{_GROUP}))?(?:[.!]\s*|$)",
    re.I,
)
_PENDING_MARKER = re.compile(
    r"to (?:na razie sugestia|na razie propozycja|tylko propozycja)\.\s*", re.I
)
_CURRENT_FEE_QUERY = re.compile(
    rf"(?:jaką {_FEE_ACCUSATIVE} mam wpisać do aktualnych ustaleń"
    rf"|jaka {_FEE_NOMINATIVE} (?:obowiązuje|jest aktualna)"
    rf"|ile (?:obecnie wynosi|wynosi obecnie) {_FEE_NOMINATIVE}"
    rf"|ile wynosi teraz {_FEE_NOMINATIVE} za wstęp {_ONE_PERSON_TEXT})\s*\?",
    re.I,
)
_FEE_ENTRY = r"(?:wejście|wstęp|bilet)"
_REJECTED_FEE_QUESTION = re.compile(
    r"odrzucam (?:propozycję (?:zmiany )?|zmianę )(?:składki|kaucji|opłaty|ceny)"
    r"[.!]\s+(?P<question>[^.!?]+\?)",
    re.I,
)
_FEE_ESTABLISHMENT = re.compile(
    rf"(?:ustalam {_FEE_ACCUSATIVE}|obowiązuje {_FEE_NOMINATIVE})"
    rf"\s+{_AMOUNT.pattern}(?:\s+(?P<unit>{_PER_PERSON}))?\s*[.!]?",
    re.I,
)
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
_GROUP_UNIT = re.compile(rf"\s+{_GROUP}\b", re.I)
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
    return re.search(r"(?<!\d)\.|\.(?!\d)|[!?]", text[start:])


def _statement_body(text: str, start: int) -> str | None:
    terminator = _clause_terminator(text, start)
    if terminator is None:
        return text[start:]
    if terminator.group() == "?":
        return None
    return text[start : start + terminator.start()]


def _fee_value(amount: str) -> Decimal:
    return Decimal("".join(amount.split()).replace(",", "."))


def _fee_scope(clause: str, amount_end: int) -> str:
    if _PER_PERSON_UNIT.match(clause, amount_end):
        return _PER_PERSON_SUFFIX
    if _GROUP_UNIT.match(clause, amount_end):
        return " za całą grupę"
    return ""


@dataclass
class _FeeState:
    field: str | None = None
    binding: str | None = None
    proposed: str | None = None
    decision: bool = False
    binding_scope: str = ""
    proposed_scope: str = ""

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
            self.binding_scope = self.proposed_scope = ""
            self.decision = False
            return False
        field = next(iter(fields), self.field)
        if self.field is not None and field != self.field:
            self.binding = self.proposed = None
            self.binding_scope = self.proposed_scope = ""
            self.decision = False
        self.field = field
        return True

    def _read_rejection(self, text: str) -> bool:
        rejection = _REJECT.search(text)
        if (
            rejection is not None
            and self.proposed is not None
            and not _question_in_clause(text, rejection.end())
        ):
            self.proposed = None
            self.decision = True
            return True
        return False

    def _read_acceptance(self, text: str) -> bool:
        acceptance = _ACCEPT.search(text)
        if acceptance is None:
            return False
        clause = _statement_body(text, acceptance.end())
        if clause is None:
            return False
        amounts = list(_AMOUNT.finditer(clause))
        if len(amounts) == 1:
            amount = amounts[0]
            self.binding = amount[1]
            proposal_scope = ""
            if self.proposed is not None and _fee_value(self.proposed) == _fee_value(
                self.binding
            ):
                proposal_scope = self.proposed_scope
            self.binding_scope = (
                _fee_scope(clause, amount.end()) or proposal_scope or self.binding_scope
            )
        elif not amounts and self.proposed is not None:
            self.binding = self.proposed
            self.binding_scope = self.proposed_scope or self.binding_scope
        else:
            return True
        self.proposed, self.decision = None, True
        return True

    def _read_proposal(self, text: str) -> bool:
        proposal = _PROPOSAL.search(text)
        if proposal is None:
            return False
        clause = _statement_body(text, proposal.end())
        if clause is None:
            return False
        amounts = list(_AMOUNT.finditer(clause))
        if len(amounts) != 1:
            return False
        amount = amounts[0]
        self.proposed_scope = _fee_scope(clause, amount.end())
        self.proposed, self.decision = amount[1], False
        return True

    def _read_initial_binding(self, text: str) -> None:
        initial = _INITIAL.search(text)
        if self.field is None or initial is None:
            return
        clause = _statement_body(text, initial.end())
        if clause is None:
            return
        amounts = list(_AMOUNT.finditer(clause))
        if len(amounts) == 1:
            amount = amounts[0]
            self.binding_scope = _fee_scope(clause, amount.end())
            self.binding, self.proposed, self.decision = amount[1], None, False


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
    event = event_state_reply(content, preceding_users[-6:])
    if event is not None:
        return CorrectionContext("event_state", event, verified_reply=event)
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
    established = _FEE_ESTABLISHMENT.fullmatch(visible.strip())
    if established:
        unit = _PER_PERSON_SUFFIX if established["unit"] else ""
        reply = f"Obowiązuje {established[1]} zł{unit}."
        return CorrectionContext("binding_fee", reply, verified_reply=reply)
    for resolver in (
        _reservation_from_conversation,
        _accepted_fee_context,
        _rejected_fee_context,
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
    unit = _PER_PERSON_SUFFIX if per_person else ""
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
    return _ONE_PERSON_TEXT not in question.casefold() or per_person


def _fee_before_proposal(history: Sequence[str]) -> _FeeState:
    state = _FeeState()
    for message in history:
        visible = without_quotes(message).strip()
        if _EDIT.match(visible) or _FEE_UNCERTAINTY.search(visible):
            state = _FeeState()
            continue
        if (
            _INITIAL.match(visible)
            or _ACCEPT.search(visible)
            or _REJECT.search(visible)
            or _PROPOSAL.match(visible)
        ):
            state.read(visible)
        else:
            # A topic change breaks a replay of consecutive fee messages.
            state = _FeeState()
    return state


def _rejected_fee_context(
    content: str, preceding_users: Sequence[str]
) -> CorrectionContext | None:
    decision = _REJECTED_FEE_QUESTION.fullmatch(content.strip())
    if decision is None or not _CURRENT_FEE_QUERY.fullmatch(decision["question"]):
        return None
    rejected = _FEE.search(content)
    requested = _FEE.search(decision["question"])
    if (
        rejected is None
        or requested is None
        or rejected[1].casefold() != requested[1].casefold()
    ):
        return None
    recent = preceding_users[-6:]
    state = _fee_before_proposal(recent)
    if (
        state.binding is None
        or state.proposed is None
        or state.field != requested[1].casefold()
    ):
        return None
    # Leave qualified prices to the context that includes their full wording.
    if _ONE_PERSON_TEXT in decision["question"].casefold() or any(
        _PER_PERSON_UNIT.search(message) for message in recent
    ):
        return None
    reply = f"Obowiązuje {state.binding} zł{state.binding_scope}. Propozycja została odrzucona."
    return CorrectionContext("binding_fee", reply, verified_reply=reply)


def _pending_fee_context(
    content: str, preceding_users: Sequence[str]
) -> CorrectionContext | None:
    proposal, question = _proposal_question(content.strip())
    if not preceding_users or _CURRENT_FEE_QUERY.fullmatch(question) is None:
        return None
    history = preceding_users[-6:]
    if not proposal:
        proposal, previous_question = _proposal_question(history[-1].strip())
        if (
            previous_question
            and _CURRENT_FEE_QUERY.fullmatch(previous_question) is None
        ):
            return None
        history = history[:-1]
    if not proposal:
        return None

    requested = _FEE.search(question)
    proposed = _FEE.search(proposal)
    if (
        not requested
        or not proposed
        or requested[1].casefold() != proposed[1].casefold()
    ):
        return None
    state = _fee_before_proposal(history)
    if state.binding is None or state.field != requested[1].casefold():
        return None
    if (
        _ONE_PERSON_TEXT in question.casefold()
        and state.binding_scope != _PER_PERSON_SUFFIX
    ):
        return None
    if not state._read_proposal(proposal):
        return None

    reply = (
        f"Obowiązuje {state.binding} zł{state.binding_scope}. "
        f"Kwota {state.proposed} zł{state.proposed_scope} jest propozycją do zatwierdzenia."
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
