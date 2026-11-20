"""Bind explicit price lists and a correction to verified mean calculations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from venom_core.services.grounded_calculator import MAX_EXPRESSION_CHARS, calculate
from venom_core.services.grounded_dialogue import (
    CalculationEvidence,
    Evidence,
    EvidenceError,
    PublishedAnswer,
)

PRICE_MEAN_ID = "price_mean"
_PRICE = r"[0-9]{1,7}(?:[.,][0-9]{1,4})?"
_LIST = re.compile(
    rf"użyj kalkulatora dla cen (?P<prices>{_PRICE}(?:(?:, | i ){_PRICE}){{1,7}}) zł"
    r"\. podaj średnią w złotych",
    re.IGNORECASE,
)
_CORRECTION = re.compile(
    rf"(?:koryguję (?:tylko )?(?P<extreme>skrajną )?pozycję|zmieniam (?:jedną )?cenę) "
    rf"z (?P<old>{_PRICE}) na (?P<new>{_PRICE}) zł\. przelicz kalkulatorem średnią",
    re.IGNORECASE,
)
_RECAP = re.compile(
    r"(?:a co ze średnią i medianą przed korektą oraz po niej\? chcę krótkie porównanie"
    r"|porównaj krótko średnią i medianę przed korektą i po niej)",
    re.IGNORECASE,
)


def mean_expression(values: list[str] | tuple[str, ...]) -> str | None:
    """Build one expression with the division applied to all operands."""
    addends = "+".join(f"({value.replace(',', '.')})" for value in values)
    expression = f"({addends})/{len(values)}"
    return expression if len(expression) <= MAX_EXPRESSION_CHARS else None


def _normalize(message: str) -> str:
    return " ".join(message.split()).rstrip(".!?")


def _price(value: str) -> str:
    return format(Decimal(value.replace(",", ".")).normalize(), "f")


@dataclass(frozen=True)
class PriceMeanState:
    prices: tuple[str, ...]
    previous: tuple[str, ...] | None
    expression: str


def _listed_prices(message: str) -> tuple[str, ...]:
    match = _LIST.fullmatch(_normalize(message))
    if match is None:
        return ()
    return tuple(map(_price, re.split(r", | i ", match["prices"], flags=re.I)))


def bind_price_mean(users: tuple[str, ...]) -> PriceMeanState | None:
    if not users:
        return None
    listed = _listed_prices(users[-1])
    if listed:
        expression = mean_expression(listed)
        return PriceMeanState(listed, None, expression) if expression else None
    correction = _CORRECTION.fullmatch(_normalize(users[-1]))
    if correction is None or len(users) < 2:
        return None
    original = _listed_prices(users[-2])
    if not original:
        return None
    old, new = _price(correction["old"]), _price(correction["new"])
    if original.count(old) != 1 or (
        correction["extreme"]
        and old
        not in (
            min(original, key=Decimal),
            max(original, key=Decimal),
        )
    ):
        return None
    updated = tuple(new if price == old else price for price in original)
    expression = mean_expression(updated)
    return PriceMeanState(updated, original, expression) if expression else None


def _median(prices: tuple[str, ...]) -> str:
    ordered = sorted(prices, key=Decimal)
    mid, remainder = divmod(len(ordered), 2)
    return (
        ordered[mid]
        if remainder
        else calculate(f"({ordered[mid - 1]}+{ordered[mid]})/2")
    )


def _money(value: str) -> str:
    return f"{value.replace('.', ',')} zł"


@dataclass(frozen=True)
class PriceMeanReceipt:
    users: tuple[str, ...]
    state: PriceMeanState
    calculation: CalculationEvidence

    @classmethod
    def from_evidence(
        cls, users: tuple[str, ...], state: PriceMeanState, evidence: Evidence
    ) -> PriceMeanReceipt:
        execution = CalculationEvidence(
            PRICE_MEAN_ID,
            state.expression,
            calculate(state.expression),
            "zł",
        )
        if evidence.calculations != (execution,):
            raise EvidenceError("pilot_price_mean_evidence_mismatch")
        return cls(users, state, execution)


@dataclass(frozen=True)
class PilotPriceMeanAnswer(PublishedAnswer):
    price_mean_receipt: PriceMeanReceipt


def price_mean_recap(
    message: str, users: tuple[str, ...], receipts: tuple[PriceMeanReceipt, ...]
) -> str | None:
    if not receipts or _RECAP.fullmatch(_normalize(message)) is None:
        return None
    by_history = {item.users: item for item in receipts}
    before, after = by_history.get(users[:-1]), by_history.get(users)
    if before is None or after is None or before.state.prices != after.state.previous:
        return (
            "Do porównania potrzebuję potwierdzonych wyników sprzed korekty i po niej."
        )
    old, new = before.calculation.value, after.calculation.value
    if old == new:
        mean = f"Średnia w obu przypadkach wyniosła {_money(new)}."
    else:
        direction = "spadła" if Decimal(new) < Decimal(old) else "wzrosła"
        mean = f"Średnia {direction} z {_money(old)} do {_money(new)}."
    old_median, new_median = _median(before.state.prices), _median(after.state.prices)
    if old_median == new_median:
        median = f"Mediana pozostała na poziomie {_money(new_median)}, bo środek uporządkowanej listy się nie zmienił."
    else:
        median = f"Mediana zmieniła się z {_money(old_median)} na {_money(new_median)}."
    return f"{mean} {median}"
