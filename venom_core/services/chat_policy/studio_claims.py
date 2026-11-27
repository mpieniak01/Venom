"""Check narrow, source-bound Studio claims before publishing a draft."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from venom_core.api.schemas.llm_simple import HistoryMessage

_NAME = r"[^\W\d_]+(?:[- ][^\W\d_]+){0,2}"
_SUBJECT = r"[\w -]{2,45}"
_BREAK = re.compile(
    r"[.!?;\n]+|,\s+(?=(?:a|ale|natomiast|to|więc)\b)| i (?=nie wiadomo\b)", re.I
)
_QUESTION = re.compile(r"^(?:a )?(?:czy|gdzie)\b", re.I)
_GUARDED = re.compile(
    r"\b(?:jeżeli|jeśli|o ile|gdyby|można (?:użyć|pakować|zabezpieczyć)|"
    r"nie (?:wiadomo|potwierdzono|potwierdza|można potwierdzić|możemy potwierdzić|"
    r"szło|wynika|wpisuj|zapisuj)|brak potwierdzenia|bez potwierdzenia|"
    r"nie ma (?:dowodu|potwierdzenia))\b",
    re.I,
)
_SMS_DRAFT = re.compile(
    rf"(?:napisz|ułóż|przygotuj) (?:krótki )?sms do (?P<subject>{_NAME})(?=[,.!?])",
    re.I,
)
_PHONE = re.compile(
    rf"(?:(?:zdążył[ae]m (?:jednak )?zadzwonić|"
    rf"(?:przed chwilą )?zadzwonił[ae]m)(?: do (?P<subject>{_NAME}))?)",
    re.I,
)
_SENT = re.compile(rf"wysłał[ae]m sms(?:-a)? do (?P<subject>{_NAME})", re.I)
_SMS_QUERY = re.compile(
    r"czy (?:mogę|można) (?:w notatce )?(?:zaznaczyć|zapisać|wpisać|odnotować)"
    r".{0,65}\bsms\b.{0,35}",
    re.I,
)
_SENT_CLAIM = re.compile(
    r"\b(?:sms(?:-u|-a)?\b.{0,65}\b(?:wysłan[oy]|poszedł|został nadany)|"
    r"(?:wysłano|wysłał(?:am|em|aś|eś)) sms(?:-a)?)\b",
    re.I,
)
_SMS_RECIPIENT = re.compile(
    rf"\bsms(?:-u|-a)? do (?P<subject>{_NAME}?) "
    r"(?:(?:nie )?został )?(?:wysłan[oy]|poszedł)\b|"
    rf"\b(?:wysłan[oy]|poszedł)(?: sms(?:-a)?)? do (?P<recipient>{_NAME})$",
    re.I,
)
_SMS_YES = re.compile(r"^tak(?:[, ]+możesz (?:to zrobić|tak zapisać))?$", re.I)

_LEDGER = re.compile(
    r"na (?:papierowej )?(?:liście|karcie) wypożyczeń (?:mam|jest): (?P<rows>[^.!?]{5,360})",
    re.I,
)
_ROW = re.compile(rf"(?P<subject>{_SUBJECT})\s+[—–-]\s+(?P<status>[\w :/-]{{3,65}})")
_RETURN_QUESTION = re.compile(
    r"czy .{1,80}(?:z powrotem|wrócił[oy]?|na miejscu|w pracowni)|"
    r"czego (?:jeszcze )?nie potwierdziliśmy",
    re.I,
)
_SHELF_OBSERVATION = re.compile(
    rf"(?:przed chwilą |teraz )?(?:odłożył[ae]m|położył[ae]m) "
    rf"(?P<subject>{_SUBJECT}?) na półkę",
    re.I,
)
_LOCATION = re.compile(
    r"\b(?:poza pracownią|w pracowni|na półce|na miejscu|wrócił[yao]?|zwrócono|"
    r"nie (?:wrócił[yao]?|zwrócono)|(?:są|jest) już z powrotem)\b",
    re.I,
)
_REGISTERED_RETURN = re.compile(r"\b(?:wpisano|odnotowano), że\b", re.I)
_FIRSTHAND_CHECK = re.compile(
    r"\b(?:sprawdził[ae]m|widział[ae]m|obejrzał[ae]m) (?:sam(?:a)? )?"
    r"(?:półkę|na półce|w pracowni)\b",
    re.I,
)
_NEGATIVE_LOCATION = re.compile(r"\bnie (?:jest|są|znajduje się|leży)\b", re.I)
_COLLECTIVE = re.compile(r"\b(?:nie )?wszystk(?:ie|o)\b", re.I)

_PACKAGES = {
    "tuba": r"tub(?:a|y|ę|ach|ami|ie)",
    "pudełko": r"pudeł(?:ko|ka|ku|ek|kach|kami)",
    "opakowanie": r"opakowa(?:nie|nia|niu|ń|niach|niami)",
    "papier": r"papier(?:u|em)?(?: ochronny| ochronnego|em ochronnym)?",
    "folia": r"foli(?:a|ę|ą|i)(?: bąbelkow[aąej])?",
    "pokrowiec": r"pokrow(?:iec|ca|ce|cach|cami)",
    "woreczek": r"worecz(?:ek|ka|ki|kach|kami)",
}
_PACKAGING = re.compile(
    rf"na (?P<subject>{_SUBJECT}?) (?:mamy|są|przygotowaliśmy) (?P<package>[^.!?]{{2,70}})",
    re.I,
)
_PACKAGE_QUESTION = re.compile(
    rf"(?:a )?(?:z|ze) (?P<subject>{_SUBJECT}?) "
    r"(?:pod tym samym względem|w tym samym kontekście|pod względem pakowania)\?",
    re.I,
)
_PACKED_DONE = re.compile(
    r"\b(?:(?:są|jest|został[yao]?) (?:już )?(?:zapakowan|spakowan)[yea]|"
    r"zapakowano|zapakowaliśmy)\b",
    re.I,
)
_PACKED_CLAIM = re.compile(
    r"\b(?:są (?:już )?(?:pakowane|zapakowane)|"
    r"jest (?:już )?(?:pakowan[yea]|zapakowan[yea])|"
    r"pakujemy|dostają|mają|mamy do (?:nich|niego|niej)|"
    r"dostępne są|są dostępne|zapewniamy)\b",
    re.I,
)


class Proof(StrEnum):
    PHONE = "phone"
    SENT_SMS = "sent_sms"
    RETURN_ENTRY = "return_entry"
    RETURN_DUE = "return_due"
    RETURN_MISSING = "return_missing"
    ON_SHELF = "on_shelf"
    PACKAGE = "package"


@dataclass(frozen=True)
class Evidence:
    subject: str
    proof: Proof
    value: str = ""


class StudioClaimCheck(Protocol):
    def publish(self, draft: str) -> str:
        """Keep the draft unless it asserts something its evidence does not support."""
        ...


def _clauses(text: str) -> list[str]:
    return [piece.strip(' *"„”') for piece in _BREAK.split(text) if piece.strip()]


def _statements(text: str) -> list[str]:
    # Keep the wording within each user's statement, including names from sources.
    return [piece.strip() for piece in re.split(r"[.!?]+", text) if piece.strip()]


def _supports(
    evidence: Sequence[Evidence], subject: str, proof: Proof, value: str = ""
) -> bool:
    return any(
        row.subject.casefold() == subject.casefold()
        and row.proof == proof
        and (not value or row.value == value)
        for row in evidence
    )


@dataclass(frozen=True)
class _SmsCheck:
    subject: str
    evidence: tuple[Evidence, ...]

    def publish(self, draft: str) -> str:
        if not any(self._unsupported(clause) for clause in _clauses(draft)):
            return draft
        if _supports(self.evidence, self.subject, Proof.SENT_SMS):
            return f"Potwierdzono wysłanie SMS-u do {self.subject}."
        if _supports(self.evidence, self.subject, Proof.PHONE):
            return (
                f"Możesz odnotować telefon do {self.subject}. "
                "Sam telefon nie potwierdza wysłania SMS-u."
            )
        return "Telefon nie potwierdza wysłania SMS-u. Zapisz wysłanie dopiero po jego potwierdzeniu."

    def _unsupported(self, clause: str) -> bool:
        if _QUESTION.match(clause) or _GUARDED.search(clause):
            return False
        recipient = _SMS_RECIPIENT.search(clause)
        claimed_subject = (
            (recipient["subject"] or recipient["recipient"])
            if recipient
            else self.subject
        )
        return bool(
            _SENT_CLAIM.search(clause) or _SMS_YES.fullmatch(clause)
        ) and not _supports(self.evidence, claimed_subject, Proof.SENT_SMS)


def _sms_check(text: str, users: Sequence[str]) -> StudioClaimCheck | None:
    if not users or not (original := _SMS_DRAFT.match(users[-1])):
        return None
    pieces = _statements(text)
    if not pieces or not _SMS_QUERY.fullmatch(pieces[-1]):
        return None
    subject = original["subject"]
    evidence: list[Evidence] = []
    for piece in pieces[:-1]:
        if call := _PHONE.fullmatch(piece):
            evidence.append(Evidence(call["subject"] or subject, Proof.PHONE))
        if sent := _SENT.fullmatch(piece):
            evidence.append(Evidence(sent["subject"], Proof.SENT_SMS))
    if not evidence:
        return None
    return _SmsCheck(subject, tuple(evidence))


def _row_status(subject: str, status: str) -> Evidence | None:
    lowered = status.casefold()
    if lowered in {"zwrot wpisany", "wpisano zwrot"}:
        return Evidence(subject, Proof.RETURN_ENTRY)
    if lowered in {"brak wpisu o zwrocie", "bez wpisu o zwrocie"}:
        return Evidence(subject, Proof.RETURN_MISSING)
    if lowered.startswith(("termin ", "termin zwrotu ")):
        rest = re.sub(r"^termin(?: zwrotu)? ", "", status, flags=re.I)
        return Evidence(subject, Proof.RETURN_DUE, rest)
    return None


def _ledger_rows(text: str) -> tuple[Evidence, ...]:
    ledger = _LEDGER.match(text)
    if not ledger:
        return ()
    evidence: list[Evidence] = []
    for row in ledger["rows"].split(","):
        if (parsed := _ROW.fullmatch(row.strip())) and (
            entry := _row_status(parsed["subject"].strip(), parsed["status"].strip())
        ):
            evidence.append(entry)
        else:
            return ()
    if len({row.subject.casefold() for row in evidence}) != len(evidence):
        return ()
    return tuple(evidence)


def _resolve_subject(raw: str, subjects: Sequence[str]) -> str | None:
    name = raw.casefold()
    for subject in subjects:
        if name == subject.casefold():
            return subject
    matches = [subject for subject in subjects if name == subject.casefold().split()[0]]
    return matches[0] if len(matches) == 1 else None


def _mentioned_subjects(clause: str, labels: Sequence[str]) -> list[str]:
    result: list[str] = []
    for label in labels:
        if re.search(rf"\b{re.escape(label)}(?:a|u|em)?\b", clause, re.I):
            result.append(label)
    return result


def _has_unsupported_location(
    draft: str, labels: Sequence[str], evidence: Sequence[Evidence]
) -> bool:
    previous: list[str] = []
    for clause in _clauses(draft):
        if _FIRSTHAND_CHECK.search(clause):
            return True
        subjects = _mentioned_subjects(clause, labels)
        if not subjects:
            subjects = list(labels) if _COLLECTIVE.search(clause) else previous
        if subjects:
            previous = subjects
        claim = _LOCATION.search(clause)
        if (
            not subjects
            or claim is None
            or _QUESTION.match(clause)
            or _GUARDED.search(clause)
        ):
            continue
        location = claim[0].casefold()
        if location.startswith(("wrócił", "zwrócono")) and _REGISTERED_RETURN.search(
            clause[: claim.start()]
        ):
            continue
        if (
            location != "na półce"
            or _NEGATIVE_LOCATION.search(clause)
            or any(not _supports(evidence, item, Proof.ON_SHELF) for item in subjects)
        ):
            return True
    return False


@dataclass(frozen=True)
class _InventoryCheck:
    rows: tuple[Evidence, ...]
    observations: tuple[Evidence, ...]

    def publish(self, draft: str) -> str:
        labels = [entry.subject for entry in self.rows]
        if not _has_unsupported_location(draft, labels, self.observations):
            return draft
        notes = []
        for entry in self.rows:
            label = entry.subject[0].upper() + entry.subject[1:]
            if _supports(self.observations, entry.subject, Proof.ON_SHELF):
                continue
            if entry.proof == Proof.RETURN_ENTRY:
                if not self.observations:
                    notes.append(f"{label}: zwrot wpisany na liście.")
            elif entry.proof == Proof.RETURN_DUE:
                notes.append(f"{label}: zwrot niepotwierdzony (termin {entry.value}).")
            else:
                notes.append(f"{label}: brak wpisu potwierdzającego zwrot.")
        return " ".join(notes)


def _inventory_check(text: str, users: Sequence[str]) -> StudioClaimCheck | None:
    pieces = _statements(text)
    if not pieces or not _RETURN_QUESTION.fullmatch(pieces[-1]):
        return None
    if current := _ledger_rows(text):
        return _InventoryCheck(current, ())
    if not users or not (rows := _ledger_rows(users[-1])):
        return None
    if len(pieces) != 2 or not (placement := _SHELF_OBSERVATION.fullmatch(pieces[0])):
        return None
    subject = _resolve_subject(placement["subject"], [entry.subject for entry in rows])
    return (
        _InventoryCheck(rows, (Evidence(subject, Proof.ON_SHELF),)) if subject else None
    )


def _package_values(text: str) -> tuple[str, ...]:
    return tuple(
        name
        for name, form in _PACKAGES.items()
        if re.search(rf"\b{form}\b", text, re.I)
    )


def _package_source(text: str) -> tuple[Evidence, ...]:
    pieces = _statements(text)
    if not pieces or not (fact := _PACKAGING.fullmatch(pieces[0])):
        return ()
    return tuple(
        Evidence(fact["subject"], Proof.PACKAGE, value)
        for value in _package_values(fact["package"])
    )


def _package_subject_forms(subject: str) -> tuple[str, ...]:
    subject = subject.casefold()
    if subject.endswith(("y", "i", "e")) and len(subject) > 3 and " " not in subject:
        stem = subject[:-1]
        return (subject, stem + "ami", stem + "ów", stem + "ach")
    return (subject,)


@dataclass(frozen=True)
class _PackagingCheck:
    subject: str
    evidence: tuple[Evidence, ...]

    def publish(self, draft: str) -> str:
        for sentence in _clauses(draft):
            packed_done = _PACKED_DONE.search(sentence)
            if (
                _QUESTION.match(sentence)
                or _GUARDED.search(sentence)
                or not (packed_done or _PACKED_CLAIM.search(sentence))
            ):
                continue
            packages = _package_values(sentence)
            if not packages and not packed_done:
                continue
            earlier = {
                row.subject
                for row in self.evidence
                if any(
                    re.search(rf"\b{re.escape(form)}\b", sentence, re.I)
                    for form in _package_subject_forms(row.subject)
                )
            }
            if (
                earlier
                and not packed_done
                and self.subject not in earlier
                and not re.search(rf"\b{re.escape(self.subject)}\b", sentence, re.I)
                and all(
                    _supports(self.evidence, item, Proof.PACKAGE, value)
                    for item in earlier
                    for value in packages
                )
            ):
                continue
            if packed_done or any(
                not _supports(self.evidence, self.subject, Proof.PACKAGE, value)
                for value in packages
            ):
                known = [
                    row.value
                    for row in self.evidence
                    if row.subject == self.subject and row.proof == Proof.PACKAGE
                ]
                if known:
                    return f"Dostępne opakowanie dla tych rzeczy: {', '.join(known)}."
                return (
                    "Czy macie papier ochronny albo pudełka, "
                    "żeby zabezpieczyć je na czas podróży?"
                )
        return draft


def _packaging_check(text: str, users: Sequence[str]) -> StudioClaimCheck | None:
    if not users or not (focus := _PACKAGE_QUESTION.fullmatch(text)):
        return None
    if not _package_source(users[-1]):
        return None
    evidence = tuple(row for message in users[-3:] for row in _package_source(message))
    subject = focus["subject"]
    for row in evidence:
        if subject.casefold() in _package_subject_forms(row.subject):
            subject = row.subject
            break
    return _PackagingCheck(subject, evidence)


def prepare_studio_claim_check(
    text: str, history: Sequence[HistoryMessage]
) -> StudioClaimCheck | None:
    """Select a claim check from user-provided evidence in the adjacent discussion."""
    current = " ".join(text.split())
    users = [" ".join(turn.content.split()) for turn in history if turn.role == "user"]
    return (
        _sms_check(current, users)
        or _inventory_check(current, users)
        or _packaging_check(current, users)
    )
