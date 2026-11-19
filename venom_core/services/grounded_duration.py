"""Bind explicit loop durations and the one-time cleanup to calculator evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from venom_core.services.grounded_calculator import calculate
from venom_core.services.grounded_dialogue import (
    CalculationEvidence,
    Evidence,
    EvidenceError,
    PublishedAnswer,
)

DURATION_CALCULATION_ID = "session_duration"
_COUNTS = {"jedną": 1, "dwie": 2, "trzy": 3, "cztery": 4, "pięć": 5, "sześć": 6}
_ORDINALS = {"drugą": 2, "trzecią": 3, "czwartą": 4, "piątą": 5, "szóstą": 6}
_DURATION = r"[0-9]{1,4}(?:[.,][0-9]{1,3})?"
_MINUTES = r"(?:min(?:ut(?:a|y|ę)?)?)"
_BASE = re.compile(
    rf"(?:(?:wykonam|planuję|zaplanowano) )?"
    rf"(?P<count>[1-9][0-9]?|{'|'.join(_COUNTS)}) pętl(?:ę|e|i) "
    rf"po (?P<regular>{_DURATION}) {_MINUTES}(?:,|\.) "
    rf"(?:po całej sesji dojdzie|na koniec (?:dolicz|zaplanowano)) "
    rf"(?P<cleanup>{_DURATION}) {_MINUTES} (?:porządków|sprzątania)(?: jednorazowo)?"
)
_CALCULATE = re.compile(
    r"przelicz|(?:oblicz kalkulatorem|policz kalkulatorem|użyj kalkulatora i podaj) "
    r"(?:całkowity|łączny) czas(?:,? w minutach)?"
)
_ADD = re.compile(
    rf"dodaję (?P<ordinal>{'|'.join(_ORDINALS)}|kolejną|jeszcze jedną) pętlę, "
    rf"(?:ale )?(?:ostatnia|nowa|ta nowa) trwa (?P<duration>{_DURATION})"
    rf" {_MINUTES}(?: zamiast (?P<previous>{_DURATION})(?: {_MINUTES})?)?"
)
_CHANGE_LAST = re.compile(
    rf"zmieniam czas ostatniej pętli na (?P<duration>{_DURATION}) {_MINUTES}"
)
_CHANGE_CLEANUP = re.compile(
    rf"(?:sprzątanie|porządki) zmieniam na (?P<duration>{_DURATION}) {_MINUTES}, nadal raz"
)
_RECAP = re.compile(
    r"(?:wypisz|podaj) (?:aktualny )?czas ostatniej pętli, "
    r"jednorazow(?:y dodatek|e sprzątanie) (?:i|oraz) (?:pełną sumę|łączny czas)"
)


def _normalize(message: str) -> str:
    return " ".join(message.casefold().split()).rstrip(".!?")


def _decimal(duration: str) -> str:
    return format(Decimal(duration.replace(",", ".")).normalize(), "f")


@dataclass(frozen=True)
class DurationState:
    """Operands and their latest literal user clauses."""

    count: int
    regular: str
    cleanup: str
    regular_quote: str
    cleanup_quote: str
    tail: tuple[tuple[str, str], ...] = ()

    @property
    def loops_expression(self) -> str:
        terms = [f"{self.count}*{self.regular}"] if self.count else []
        terms.extend(value for value, _ in self.tail)
        return "+".join(terms)

    @property
    def expression(self) -> str:
        return f"({self.loops_expression})+{self.cleanup}"

    @property
    def last(self) -> str:
        return self.tail[-1][0] if self.tail else self.regular

    def with_clause(self, clause: str, quote: str) -> DurationState | None:
        if (
            _CALCULATE.fullmatch(clause)
            or _RECAP.fullmatch(clause)
            or clause
            in (
                "sprzątanie nadal raz",
                "porządki nadal raz",
            )
        ):
            return self
        if added := _ADD.fullmatch(clause):
            expected = self.count + len(self.tail) + 1
            if _ORDINALS.get(added["ordinal"], expected) != expected or (
                added["previous"] is not None
                and _decimal(added["previous"]) != self.regular
            ):
                return None
            return DurationState(
                count=self.count,
                regular=self.regular,
                cleanup=self.cleanup,
                regular_quote=self.regular_quote,
                cleanup_quote=self.cleanup_quote,
                tail=(*self.tail, (_decimal(added["duration"]), quote)),
            )
        if changed := _CHANGE_LAST.fullmatch(clause):
            last = (_decimal(changed["duration"]), quote)
            return DurationState(
                count=self.count if self.tail else self.count - 1,
                regular=self.regular,
                cleanup=self.cleanup,
                regular_quote=self.regular_quote,
                cleanup_quote=self.cleanup_quote,
                tail=(*self.tail[:-1], last),
            )
        if changed := _CHANGE_CLEANUP.fullmatch(clause):
            return DurationState(
                count=self.count,
                regular=self.regular,
                cleanup=_decimal(changed["duration"]),
                regular_quote=self.regular_quote,
                cleanup_quote=quote,
                tail=self.tail,
            )
        return None

    def proof_material(self) -> dict[str, object]:
        return {
            "regular": self.regular_quote,
            "last_changes": [quote for _, quote in self.tail],
            "cleanup": self.cleanup_quote,
        }


def bind_duration(users: tuple[str, ...]) -> DurationState | None:
    """Bind only complete, unambiguous clauses from the user's own turns."""
    if not 2 <= len(users) <= 8 or any(len(message) > 500 for message in users):
        return None
    initial = _normalize(users[0])
    match = _BASE.fullmatch(initial)
    if match is None:
        return None
    count = (
        _COUNTS[match["count"]] if match["count"] in _COUNTS else int(match["count"])
    )
    state = DurationState(
        count,
        _decimal(match["regular"]),
        _decimal(match["cleanup"]),
        users[0],
        users[0],
    )
    for message in users[1:]:
        for quote in re.split(r"[.!?]\s+", message.strip()):
            updated = state.with_clause(_normalize(quote), quote)
            if updated is None or len(updated.tail) > 5:
                return None
            state = updated
    return state


@dataclass(frozen=True)
class DurationReceipt:
    """A vetted calculation associated with an exact sequence of user turns."""

    users: tuple[str, ...]
    state: DurationState
    calculation: CalculationEvidence

    @classmethod
    def from_evidence(
        cls, users: tuple[str, ...], state: DurationState, evidence: Evidence
    ) -> DurationReceipt:
        expected = CalculationEvidence(
            DURATION_CALCULATION_ID,
            state.expression,
            calculate(state.expression),
            "min",
        )
        if evidence.calculations != (expected,):
            raise EvidenceError("pilot_duration_evidence_mismatch")
        return cls(users, state, expected)

    def summary(self) -> str:
        subtotal = calculate(self.state.loops_expression).replace(".", ",")
        total = self.calculation.value.replace(".", ",")
        last = self.state.last.replace(".", ",")
        cleanup = self.state.cleanup.replace(".", ",")
        return (
            f"Łącznie {total} min ({subtotal} na pętle, w tym {last} na ostatnią, "
            f"oraz {cleanup} na jednorazowe sprzątanie)."
        )

    def recap(self, message: str, users: tuple[str, ...]) -> str | None:
        if _RECAP.fullmatch(_normalize(message)) is None:
            return None
        if users[: len(self.users)] != self.users or any(
            self.state.with_clause(_normalize(clause), clause) is not self.state
            for turn in users[len(self.users) :]
            for clause in re.split(r"[.!?]\s+", turn.strip())
        ):
            return "Po zmianie danych potrzebuję aktualnego wyniku kalkulatora."
        last = self.state.last.replace(".", ",")
        cleanup = self.state.cleanup.replace(".", ",")
        total = self.calculation.value.replace(".", ",")
        return (
            f"Ostatnia pętla — {last} min.\n"
            f"Jednorazowe sprzątanie — {cleanup} min.\n"
            f"Łącznie — {total} min."
        )


@dataclass(frozen=True)
class PilotDurationAnswer(PublishedAnswer):
    duration_receipt: DurationReceipt
