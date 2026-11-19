"""Bind historical falls and subsequent returns to their own percentage bases."""

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
from venom_core.services.grounded_presentation import rounded_value

PERCENT_CHANGE_ID = "percent_change"
_AMOUNT = r"[0-9]{1,9}(?:[.,][0-9]{1,4})?"
_OPENING = re.compile(
    rf"czy spadek z (?P<base>{_AMOUNT}) do (?P<low>{_AMOUNT})(?: sztuk)? oznacza, "
    r"że potrzeba potem takiego samego procentu na powrót"
)
_FALL = re.compile(
    rf"użyj kalkulatora\. zaczęliśmy od (?P<base>{_AMOUNT}), zostało (?P<low>{_AMOUNT})"
    r"\. ile procent wynosi spadek"
)
_RETURN = re.compile(
    rf"(?:koryguję stan końcowy na (?P<corrected>{_AMOUNT})\. )?"
    rf"użyj kalkulatora do obliczenia procentowego wzrostu potrzebnego do (?P<goal>{_AMOUNT})"
    r"(?:\. zaokrąglij do (?:[0-6]|zero|jednego|dwóch|trzech|czterech|pięciu|sześciu)"
    r" miejsc(?:a)? po przecinku)?"
)
_RECAP = re.compile(
    rf"napisz tylko, dlaczego dwa razy wyszło {_AMOUNT}\s*% mimo różnych kierunków"
    r"|porównaj krótko procent spadku i procent powrotu\. wyjaśnij podstawy"
)
_UNAVAILABLE = "Do porównania potrzebuję potwierdzonych wyników spadku i powrotu."


def _normalize(message: str) -> str:
    return " ".join(message.casefold().split()).rstrip(".!?")


def _decimal(amount: str) -> Decimal:
    return Decimal(amount.replace(",", "."))


def _local_number(value: Decimal) -> str:
    return format(value.normalize(), "f").replace(".", ",")


@dataclass(frozen=True)
class PercentChange:
    base: Decimal
    goal: Decimal

    @property
    def falling(self) -> bool:
        return self.goal < self.base

    @property
    def expression(self) -> str:
        base, goal = (
            format(self.base.normalize(), "f"),
            format(self.goal.normalize(), "f"),
        )
        delta = f"{base}-{goal}" if self.falling else f"{goal}-{base}"
        return f"({delta})/{base}*100"

    def describe(self, value: str, places: int | None = None) -> str:
        displayed = rounded_value(value, places) if places is not None else value
        rate = displayed.replace(".", ",")
        base, goal = _local_number(self.base), _local_number(self.goal)
        delta = _local_number(abs(self.base - self.goal))
        description = (
            f"Spadek z {base} do {goal} wynosi"
            if self.falling
            else f"Powrót z {base} do {goal} wymaga wzrostu o"
        )
        return f"{description} {rate}% (zmiana o {delta} przy podstawie {base})."


def _fall(message: str) -> PercentChange | None:
    match = _FALL.fullmatch(_normalize(message))
    if match is None:
        return None
    base, low = _decimal(match["base"]), _decimal(match["low"])
    return PercentChange(base, low) if base > low else None


def bind_percent_change(users: tuple[str, ...]) -> PercentChange | None:
    if not users:
        return None
    if fall := _fall(users[-1]):
        return fall
    rise = _RETURN.fullmatch(_normalize(users[-1]))
    if rise is None or len(users) < 2:
        return None
    historical = _fall(users[-2])
    if historical is None or _decimal(rise["goal"]) != historical.base:
        return None
    base = _decimal(rise["corrected"]) if rise["corrected"] else historical.goal
    return PercentChange(base, historical.base) if 0 < base < historical.base else None


@dataclass(frozen=True)
class PercentChangeReceipt:
    users: tuple[str, ...]
    change: PercentChange
    calculation: CalculationEvidence
    places: int | None

    @classmethod
    def from_evidence(
        cls,
        users: tuple[str, ...],
        change: PercentChange,
        evidence: Evidence,
        places: int | None,
    ) -> PercentChangeReceipt:
        expression = change.expression
        expected = CalculationEvidence(
            PERCENT_CHANGE_ID, expression, calculate(expression), "%"
        )
        if evidence.calculations != (expected,):
            raise EvidenceError("pilot_percent_change_evidence_mismatch")
        return cls(users, change, expected, places)

    def describe(self) -> str:
        return self.change.describe(self.calculation.value, self.places)


@dataclass(frozen=True)
class PilotPercentChangeAnswer(PublishedAnswer):
    percent_change_receipt: PercentChangeReceipt


def percent_change_recap(
    message: str, users: tuple[str, ...], receipts: tuple[PercentChangeReceipt, ...]
) -> str | None:
    normalized = _normalize(message)
    if opening := _OPENING.fullmatch(normalized):
        base, low = _decimal(opening["base"]), _decimal(opening["low"])
        if 0 < low < base:
            return (
                f"Nie. Spadek liczysz od {_local_number(base)}, a powrót od {_local_number(low)}. "
                "Ta sama różnica stanowi większy procent mniejszej podstawy."
            )
    if _RECAP.fullmatch(normalized) is None:
        return None
    by_history = {item.users: item for item in receipts}
    fall, rise = by_history.get(users[:-1]), by_history.get(users)
    if (
        fall is None
        or rise is None
        or not fall.change.falling
        or rise.change.falling
        or fall.change.base != rise.change.goal
    ):
        return _UNAVAILABLE
    reason = (
        "Oba stosunki zmiany do podstawy są równe, choć podstawy są różne."
        if fall.calculation.value == rise.calculation.value
        else "Każdy procent odnosi wielkość zmiany do własnej podstawy."
    )
    return f"{fall.describe()} {rise.describe()} {reason}"
