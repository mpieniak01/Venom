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
    rf"(?:napisz|ułóż|przygotuj) (?:krótki )?sms do (?P<subject>{_NAME}?)(?=[,.!?]| o )",
    re.I,
)
_TOPIC_SMS = re.compile(
    rf"(?:napisz|ułóż|przygotuj) (?:krótki )?sms do {_NAME} "
    r"o (?P<topic>[^\W\d_]+(?:[- ][^\W\d_]+){0,5})"
    r"(?:\. chcę (?:zobaczyć )?samą treść)?[.!]?",
    re.I,
)
_PHONE = re.compile(
    rf"(?:(?:zdążył[ae]m (?:jednak )?zadzwonić|"
    rf"(?:przed chwilą )?zadzwonił[ae]m)(?: do (?P<subject>{_NAME}))?)",
    re.I,
)
_PHONE_CONVERSATION = re.compile(
    rf"(?:(?:zdążył[ae]m(?: już| jednak)? porozmawiać)|"
    rf"(?:porozmawiał|rozmawiał)[ae]m) "
    rf"(?:z[e]? (?P<person>{_NAME}) przez telefon|przez telefon z[e]? (?P<recipient>{_NAME}))",
    re.I,
)
_SENT = re.compile(rf"wysłał[ae]m sms(?:-a)? do (?P<subject>{_NAME})", re.I)
_SMS_QUERY = re.compile(
    r"(?:(?:czy )?(?:mogę|można) (?:w notatce )?|mam |czy )"
    r"(?:zaznaczyć|zapisać|wpisać|odnotować|oznaczyć)(?: w notatce)?"
    r"(?:,? że)? (?:wysłanie sms(?:-a|-u)?|sms(?:-a)? (?:jako )?"
    r"(?:(?:został )?wysłan[oy]|poszedł)|wysłano sms(?:-a)?)",
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
_SMS_YES = re.compile(
    r"^tak(?:[, ]+(?:możesz|warto|należy) (?:(?:to|tak) )?"
    r"(?:zrobić|zapisać|wpisać|odnotować|oznaczyć)(?: (?:to|tak))?)?(?:$|,)",
    re.I,
)

_LEDGER = re.compile(
    r"na (?:papierowej )?(?:liście|karcie) wypożyczeń (?:mam|jest): (?P<rows>[^.!?]{5,360})",
    re.I,
)
_ROW = re.compile(rf"(?P<subject>{_SUBJECT})\s+[—–-]\s+(?P<status>[\w :/-]{{3,65}})")
_PLACE = r"(?:w|we|na|do) [\w-]+(?: [\w-]+){0,4}"
_RETURN_QUESTION = re.compile(
    rf"czy .{{1,80}}(?:z powrotem|wrócił[yao]?)(?: (?P<place>{_PLACE}))?|"
    rf"czy .{{1,80}}(?:są|jest|znajdują się) (?:już )?(?P<site>{_PLACE})|"
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
_OUTSIDE = re.compile(
    r"\bpoza (?!(?:listą|rejestrem|wykazem|tabelą|kartą|ewidencją|zakresem)\b)[\w-]+",
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
    "obwoluta": r"obwolut(?:a|ę|y|ą|ach|ami)",
}
_PACKAGING = re.compile(
    rf"(?:na|do) (?P<subject>{_SUBJECT}?) (?:mamy|są|przygotowaliśmy) (?P<package>[^.!?]{{2,70}})",
    re.I,
)
_PACKAGE_QUESTION = re.compile(
    rf"(?:a )?(?:z|ze) (?P<subject>{_SUBJECT}?) "
    r"(?:pod tym samym względem|w tym samym kontekście|pod względem pakowania)\?",
    re.I,
)
_PACKING_ADDENDUM = re.compile(r"jak to dopisać (?:w )?jednym zdaniem", re.I)
_PACKING_TRIP_ADVICE = re.compile(
    rf"jak doradzić zabranie (?P<item>{_SUBJECT}?) w podróż", re.I
)
_UNSUPPORTED_FIT = re.compile(r"\b(?:zbyt (?:duż|mał)\w*|inny kształt)\b", re.I)
_FIT_CONDITION = re.compile(r"\b(?:jeśli|jeżeli|gdyby|o ile)\b", re.I)
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
        for call in self.evidence:
            if (
                call.proof != Proof.PHONE
                or call.subject.casefold() != self.subject.casefold()
            ):
                continue
            if call.value:
                return (
                    f"Możesz odnotować rozmowę telefoniczną z {call.value}. "
                    "Rozmowa nie potwierdza wysłania SMS-u."
                )
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
            _SENT_CLAIM.search(clause) or _SMS_YES.match(clause)
        ) and not _supports(self.evidence, claimed_subject, Proof.SENT_SMS)


def _same_phone_recipient(genitive: str, instrumental: str) -> bool:
    def same_name_word(target: str, speaker: str) -> bool:
        if target == speaker:
            return True
        for target_endings, speaker_endings in (
            (("i", "y", "iej"), ("ą", "ją")),
            (("a",), ("em", "iem")),
        ):
            if any(
                target.endswith(target_end)
                and speaker.endswith(speaker_end)
                and len(target) - len(target_end) >= 2
                and target.removesuffix(target_end) == speaker.removesuffix(speaker_end)
                for target_end in target_endings
                for speaker_end in speaker_endings
            ):
                return True
        return False

    target = genitive.casefold().split()
    speaker = instrumental.casefold().split()
    return len(target) == len(speaker) and all(
        same_name_word(first, second)
        for first, second in zip(target, speaker, strict=True)
    )


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
        if conversation := _PHONE_CONVERSATION.fullmatch(piece):
            caller = conversation["person"] or conversation["recipient"]
            resolved = subject if _same_phone_recipient(subject, caller) else caller
            evidence.append(Evidence(resolved, Proof.PHONE, caller))
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
    draft: str, labels: Sequence[str], evidence: Sequence[Evidence], place: str
) -> bool:
    scoped_place = re.compile(rf"\b{re.escape(place)}\b", re.I) if place else None
    previous: list[str] = []
    for clause in _clauses(draft):
        if _FIRSTHAND_CHECK.search(clause):
            return True
        subjects = _mentioned_subjects(clause, labels)
        if not subjects:
            subjects = list(labels) if _COLLECTIVE.search(clause) else previous
        if subjects:
            previous = subjects
        claim = (
            _LOCATION.search(clause)
            or (scoped_place.search(clause) if scoped_place else None)
            or _OUTSIDE.search(clause)
        )
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
    place: str = ""

    def publish(self, draft: str) -> str:
        labels = [entry.subject for entry in self.rows]
        unresolved = [
            item.subject
            for item in self.rows
            if item.proof != Proof.RETURN_ENTRY
            and not _supports(self.observations, item.subject, Proof.ON_SHELF)
        ]
        if not _has_unsupported_location(
            draft, labels, self.observations, self.place
        ) and (
            not self.observations
            or set(unresolved).issubset(_mentioned_subjects(draft, labels))
        ):
            omitted = [
                item
                for item in self.observations
                if not any(
                    item.subject in _mentioned_subjects(clause, labels)
                    and "na półce" in clause.casefold()
                    and not _GUARDED.search(clause)
                    for clause in _clauses(draft)
                )
            ]
            return " ".join((draft, *map(self._location_note, omitted)))
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
        return " ".join((*notes, *map(self._location_note, self.observations)))

    @staticmethod
    def _location_note(item: Evidence) -> str:
        label = item.subject
        return f"{label[0].upper()}{label[1:]} jest na półce według Twojej informacji."


def _return_place(question: re.Match[str] | None) -> str:
    return (question["place"] or question["site"] or "") if question else ""


def _inventory_check(text: str, users: Sequence[str]) -> StudioClaimCheck | None:
    pieces = _statements(text)
    if not pieces or not (question := _RETURN_QUESTION.fullmatch(pieces[-1])):
        return None
    if current := _ledger_rows(text):
        return _InventoryCheck(current, (), _return_place(question))
    if not users or not (rows := _ledger_rows(users[-1])):
        return None
    if len(pieces) != 2 or not (placement := _SHELF_OBSERVATION.fullmatch(pieces[0])):
        return None
    subject = _resolve_subject(placement["subject"], [entry.subject for entry in rows])
    earlier_question = _RETURN_QUESTION.fullmatch(_statements(users[-1])[-1])
    return (
        _InventoryCheck(
            rows,
            (Evidence(subject, Proof.ON_SHELF),),
            _return_place(earlier_question),
        )
        if subject
        else None
    )


def _package_values(text: str) -> tuple[str, ...]:
    return tuple(
        name
        for name, form in _PACKAGES.items()
        if re.search(rf"\b{form}\b", text, re.I)
    )


def _package_source(text: str) -> tuple[Evidence, ...]:
    return tuple(
        Evidence(fact["subject"], Proof.PACKAGE, value)
        for statement in _statements(text)
        if (fact := _PACKAGING.fullmatch(statement))
        and not _GUARDED.search(fact["package"])
        for value in _package_values(fact["package"])
    )


def _package_subject_forms(subject: str) -> tuple[str, ...]:
    subject = subject.casefold()
    if subject.endswith("ów") and len(subject) > 4 and " " not in subject:
        stem = subject[:-2]
        return (subject, stem + "ami", stem + "i", stem + "y", stem + "ach", stem + "a")
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
            unsupported = _UNSUPPORTED_FIT.search(sentence)
            if unsupported and not _FIT_CONDITION.search(
                sentence[: unsupported.start()]
            ):
                return self._grounded_alternative()
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
                return self._grounded_alternative()
        return draft

    def _grounded_alternative(self) -> str:
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


def _stated_packaging(text: str) -> str | None:
    clauses = _statements(text)
    if len(clauses) < 2:
        return None
    addendum = _PACKING_ADDENDUM.fullmatch(clauses[-1])
    advice = _PACKING_TRIP_ADVICE.fullmatch(clauses[-1])
    if not (addendum or advice):
        return None
    facts = [clause for clause in clauses[:-1] if _package_source(clause)]
    if len(facts) != 1:
        return None
    fact = facts[0]
    if advice:
        (subject,) = {row.subject for row in _package_source(fact)}
        if advice["item"].casefold() not in _package_subject_forms(subject):
            return None
        return (
            f"{fact[0].upper()}{fact[1:]}. Skorzystaj z tego zabezpieczenia w podróży."
        )
    return f"{fact[0].upper()}{fact[1:]}."


def stated_packaging_reply(text: str, history: Sequence[HistoryMessage]) -> str | None:
    current = " ".join(text.split())
    if reply := _stated_packaging(current):
        return reply
    users = [" ".join(turn.content.split()) for turn in history if turn.role == "user"]
    previous = _statements(users[-1]) if users else []
    if previous and _PACKING_TRIP_ADVICE.fullmatch(previous[-1]):
        check = _packaging_check(current, users)
        if isinstance(check, _PackagingCheck):
            return check._grounded_alternative()
    return None


def topic_only_sms(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Draft a neutral opener when the request supplies only an SMS topic."""
    if any(turn.role == "user" for turn in history):
        return None
    topic = _TOPIC_SMS.fullmatch(" ".join(text.split()))
    return f"Cześć, piszę o {topic['topic']}." if topic else None


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
