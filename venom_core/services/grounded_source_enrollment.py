"""Bind an enrollment recap to literal role-specific clauses in verified cards."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from venom_core.services.grounded_dialogue import (
    EvidenceError,
    SourceDocument,
    SourceQuote,
    _verified_document,
    requested_citation_ids,
)

_RECAP = re.compile(
    r"(?:w (?:dokładnie )?dwóch zdaniach )?"
    r"(?:przypomnij|podsumuj|podaj) "
    r"(?:(?:kanał|sposób)(?: zgłoszeń| zapisów)?(?:,| i) termin "
    r"(?:składania )?(?:zgłosze(?:nia|nie|ń)|złożenia formularza)(?: z godziną)?,? "
    r"(?:a następnie|oraz|i) datę (?:ogłoszenia |publikacji )?wyników|"
    r"gdzie i do kiedy (?:mam się zgłosić|można się zgłosić) "
    r"(?:oraz|i) kiedy (?:poznam listę uczestników|ogłoszą wyniki))"
    r"(?: w (?:dokładnie )?dwóch zdaniach)?[.!?]?",
    re.IGNORECASE,
)
_MONTH_LENGTHS = {
    "stycznia": 31,
    "lutego": 29,
    "marca": 31,
    "kwietnia": 30,
    "maja": 31,
    "czerwca": 30,
    "lipca": 31,
    "sierpnia": 31,
    "września": 30,
    "października": 31,
    "listopada": 30,
    "grudnia": 31,
}
_DATE = rf"(?P<day>0?[1-9]|[12][0-9]|3[01]) (?P<month>{'|'.join(_MONTH_LENGTHS)})"
_TIME = r"(?P<time>(?:[01]?[0-9]|2[0-3]):[0-5][0-9])"
_DEADLINE = rf"do {_DATE} (?:do godziny|o(?: godzinie)?) {_TIME}"
_CHANNEL = r"(?P<channel>[^\W\d_](?:[^\W\d_]|[ -]){0,79}?)"
_CHANNEL_WORDS = r"(?:(?:na|do) (?:[^\W\d_][\w-]* ){1,7})?"
_ACCEPT = rf"(?:(?:zgłoszenie|zgłoszenia|formularze) {_CHANNEL_WORDS}przyjmuje|zapisy {_CHANNEL_WORDS}obsługuje)"
_COMBINED = re.compile(rf"{_ACCEPT} {_CHANNEL} {_DEADLINE}\.?", re.IGNORECASE)
_CHANNEL_ONLY = re.compile(
    rf"(?:{_ACCEPT} |kanał (?:zgłoszeń|zapisów): ){_CHANNEL}\.?",
    re.IGNORECASE,
)
_DEADLINE_ONLY = re.compile(
    rf"(?:(?:zgłoszenia|formularze) przyjmujemy|termin (?:składania )?zgłoszeń:) {_DEADLINE}\.?",
    re.IGNORECASE,
)
_RESULTS = re.compile(
    r"(?:wyniki(?: naboru| rekrutacji| przeglądu| konkursu| kwalifikacji)? "
    r"(?:zostaną ogłoszone|ogłosimy)|"
    r"listę uczestników(?: zajęć)? opublikujemy|"
    r"(?:data )?(?:ogłoszenie|ogłoszenia|publikacji) wyników:) "
    rf"{_DATE}\.?",
    re.IGNORECASE,
)
_CLAUSES = re.compile(r"(?<=[.!?])\s+|\n+")
_SENTENCE_CLAUSES = re.compile(r"(?<=[.!?])\s+")

_CARD = r"(?:\[[\w.-]{1,64}\]|[^\W\d_][\w-]{1,63})"
_CARD_LIST = rf"(?:kartę|karty) {_CARD}(?:(?:, | i | oraz )(?:kart[ęy] )?{_CARD})*"
_RESULTS_CITATION = re.compile(
    rf"(?:przeczytaj(?: ponownie)? (?:(?:obie|wszystkie) )?{_CARD_LIST}[.!] )?"
    rf"zacytuj kartę {_CARD} (?:i|oraz) podaj (?:tylko|wyłącznie) "
    r"datę (?:ogłoszenia |publikacji )?wyników[.!?]?",
    re.IGNORECASE,
)
_RESULTS_ROLE = re.compile(r"\b(?:wynik\w*|list(?:a|ę) uczestników)\b", re.IGNORECASE)
_OTHER_DATED_RESULT = re.compile(
    rf"{_DATE}|\b[0-9]{{1,4}}[./-][0-9]{{1,2}}\b", re.IGNORECASE
)


@dataclass(frozen=True)
class EnrollmentField:
    value: str
    proof: SourceQuote


@dataclass(frozen=True)
class EnrollmentEvidence:
    channel: EnrollmentField
    deadline: EnrollmentField
    results_date: EnrollmentField

    def render(self) -> str:
        return (
            f"Kanał zgłoszeń to {self.channel.value}, a termin mija {self.deadline.value}. "
            f"Wyniki zostaną ogłoszone {self.results_date.value}."
        )


def requests_enrollment_recap(message: str) -> bool:
    """Route only explicit requests for the full three-field recap."""
    return _RECAP.fullmatch(" ".join(message.split())) is not None


def _date(match: re.Match[str]) -> str:
    day, month = int(match["day"]), match["month"].casefold()
    if day > _MONTH_LENGTHS[month]:
        raise EvidenceError("enrollment_invalid_date")
    return f"{day} {month}"


def _deadline(match: re.Match[str]) -> str:
    hours, minutes = match["time"].split(":")
    return f"{_date(match)} o {int(hours):02d}:{minutes}"


def _one(candidates: list[EnrollmentField], role: str) -> tuple[EnrollmentField, ...]:
    if not candidates:
        raise EvidenceError(f"enrollment_missing_{role}")
    if len({field.value.casefold() for field in candidates}) != 1:
        raise EvidenceError(f"enrollment_conflicting_{role}")
    return tuple(candidates)


def _verified_clauses(
    documents: tuple[SourceDocument, ...], *, split: re.Pattern[str] = _CLAUSES
) -> Iterator[tuple[SourceDocument, str]]:
    for doc in documents:
        if not _verified_document(doc):
            raise EvidenceError("source_incomplete")
        for clause in split.split(doc.text):
            yield doc, clause.strip()


def requested_results_date_quote(
    message: str, documents: tuple[SourceDocument, ...]
) -> SourceQuote | None:
    """Select one literal results date from the explicitly cited card."""
    if _RESULTS_CITATION.fullmatch(" ".join(message.split())) is None:
        return None
    citations = requested_citation_ids(message)
    if len(citations) != 1:
        raise EvidenceError("enrollment_results_citation_required")
    fields: list[EnrollmentField] = []
    for document, clause in _verified_clauses(documents, split=_SENTENCE_CLAUSES):
        match = _RESULTS.fullmatch(clause)
        if match:
            proof = SourceQuote(document.ref.source_id, document.ref.version, clause)
            fields.append(EnrollmentField(_date(match), proof))
        elif _RESULTS_ROLE.search(clause) and _OTHER_DATED_RESULT.search(clause):
            raise EvidenceError("enrollment_results_date_ambiguous")
    supported = _one(fields, "results_date")
    eligible = [
        field.proof for field in supported if field.proof.source_id == citations[0]
    ]
    if not eligible:
        raise EvidenceError("enrollment_results_quote_missing")
    return min(eligible, key=lambda proof: len(proof.quote))


def bind_enrollment_evidence(
    documents: tuple[SourceDocument, ...],
) -> EnrollmentEvidence:
    """Require unique supported fields; keep channel and deadline on the same card."""
    channels: list[EnrollmentField] = []
    deadlines: list[EnrollmentField] = []
    results: list[EnrollmentField] = []
    source_ids = {doc.ref.source_id.casefold() for doc in documents}
    for doc, sentence in _verified_clauses(documents):
        proof = SourceQuote(doc.ref.source_id, doc.ref.version, sentence)
        combined = _COMBINED.fullmatch(sentence)
        if channel := combined or _CHANNEL_ONLY.fullmatch(sentence):
            value = " ".join(channel["channel"].split())
            if value.casefold().removeprefix("karta ") in source_ids:
                raise EvidenceError("enrollment_channel_is_source_id")
            channels.append(EnrollmentField(value, proof))
        if deadline := combined or _DEADLINE_ONLY.fullmatch(sentence):
            deadlines.append(EnrollmentField(_deadline(deadline), proof))
        if result := _RESULTS.fullmatch(sentence):
            results.append(EnrollmentField(_date(result), proof))
    channel_fields = _one(channels, "channel")
    deadline_fields = _one(deadlines, "deadline")
    (results_date, *_) = _one(results, "results_date")
    deadline_by_source = {field.proof.source_id: field for field in deadline_fields}
    for channel_field in channel_fields:
        if deadline_field := deadline_by_source.get(channel_field.proof.source_id):
            return EnrollmentEvidence(channel_field, deadline_field, results_date)
    raise EvidenceError("enrollment_unbound_submission")
