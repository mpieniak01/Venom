"""Resolve explicit order and group corrections from the user's current data."""

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
from venom_core.services.grounded_presentation import people_noun

_PRICE = r"[0-9]{1,7}(?:[.,][0-9]{1,4})?"
_COUNT = r"[0-9]{1,4}"
_ORDER = re.compile(
    rf"Potrzebuję (?P<quantity>[1-9][0-9]{{0,3}}) (?P<product>[^\W\d_]+) po (?P<price>{_PRICE}) zł, "
    rf"dostawa jednorazowo (?P<delivery>{_PRICE}) zł\.",
    re.IGNORECASE,
)
_ORDER_TOTAL = re.compile(
    r"Użyj kalkulatora i podaj koszt całości z dostawą\.", re.IGNORECASE
)
_ORDER_CHANGE = re.compile(
    rf"Cena jednej (?:wzrosła|spadła) do (?P<price>{_PRICE}) zł\. "
    r"Zmieniam też dostawę na darmowy odbiór\. Użyj kalkulatora\.",
    re.IGNORECASE,
)
_ORDER_RECAP = re.compile(
    r"Napisz SMS z aktualną liczbą, ceną jednej, sposobem odbioru i sumą\.",
    re.IGNORECASE,
)

_GROUP = re.compile(
    rf"W grupie(?: wycieczkowej)? jest (?P<adults>{_COUNT}) dorosłych, (?P<children>{_COUNT}) dzieci\. "
    r"Jedna opiekunka wlicza się już do dorosłych\.",
    re.IGNORECASE,
)
_GROUP_GROWTH = re.compile(
    rf"Dołącza (?P<children>{_COUNT}) dzieci, dorośli bez zmian\. Kalkulatorem policz całą grupę\.",
    re.IGNORECASE,
)
_ADULTS = {"dwóch": 2, "trzech": 3, "czterech": 4, "pięciu": 5}
_CHILDREN = {"dwojga": 2, "trojga": 3}
_ADULTS_LEFT = re.compile(
    rf"(?P<adults>{_COUNT}|{'|'.join(_ADULTS)}) dorosłych odwołało obecność\. "
    r"Próba dopisania (?P<children>dwojga|trojga|[0-9]{1,4}) dzieci nieaktualna\. Użyj kalkulatora ponownie\.",
    re.IGNORECASE,
)
_GROUP_RECAP = re.compile(
    r"Podaj ile dorosłych, ile dzieci i czy opiekunka jest liczbą dodatkową\.",
    re.IGNORECASE,
)


def _normalized_price(value: str) -> str:
    return format(Decimal(value.replace(",", ".")).normalize(), "f")


def _polish(value: str) -> str:
    return value.replace(".", ",")


@dataclass(frozen=True)
class OrderTotal:
    quantity: int
    product: str
    price: str
    delivery: str
    pickup: bool

    @property
    def expression(self) -> str:
        return f"{self.quantity}*{self.price}+{self.delivery}"

    def details(self, result: str, *, final: bool) -> str:
        purchase = f"{self.quantity} {self.product} po {_polish(self.price)}"
        delivery = (
            "darmowy odbiór"
            if self.pickup
            else f"jednorazowa dostawa za {_polish(self.delivery)}"
        )
        if final:
            cost = delivery if self.pickup else f"{delivery} zł"
            return f"{purchase} zł, {cost}. Razem {_polish(result)} zł."
        return f"Łącznie {_polish(result)} zł ({purchase}, {delivery})."


@dataclass(frozen=True)
class GroupTotal:
    adults: int
    children: int

    @property
    def expression(self) -> str:
        return f"{self.adults}+{self.children}"

    def details(self, result: str, *, final: bool) -> str:
        if final:
            return (
                f"{self.adults} dorosłych i {self.children} dzieci. "
                "Opiekunka jest już wliczona do dorosłych."
            )
        return (
            f"Łącznie {result} {people_noun(int(result))} ({self.adults} dorosłych, w tym opiekunka, "
            f"oraz {self.children} dzieci)."
        )


def explicit_group_intro(message: str) -> str | None:
    match = _GROUP.fullmatch(message)
    if match is None or int(match["adults"]) < 1:
        return None
    return GroupTotal(int(match["adults"]), int(match["children"])).details(
        "", final=True
    )


def _bind_order(users: tuple[str, ...]) -> OrderTotal | None:
    base = _ORDER.fullmatch(users[0])
    if base is None or _ORDER_TOTAL.fullmatch(users[1]) is None:
        return None
    pickup = _ORDER_CHANGE.fullmatch(users[2]) if len(users) == 3 else None
    if len(users) == 3 and pickup is None:
        return None
    return OrderTotal(
        int(base["quantity"]),
        base["product"],
        _normalized_price(pickup["price"] if pickup else base["price"]),
        "0" if pickup else _normalized_price(base["delivery"]),
        pickup is not None,
    )


def _bind_group(users: tuple[str, ...]) -> GroupTotal | None:
    base = _GROUP.fullmatch(users[0])
    growth = _GROUP_GROWTH.fullmatch(users[1])
    if base is None or growth is None:
        return None
    adults = int(base["adults"])
    growth_count = int(growth["children"])
    if len(users) == 3:
        left = _ADULTS_LEFT.fullmatch(users[2])
        if left is None:
            return None
        value = left["adults"].casefold()
        adults -= int(value) if value.isdecimal() else _ADULTS[value]
        cancelled = left["children"].casefold()
        cancelled_count = (
            int(cancelled) if cancelled.isdecimal() else _CHILDREN[cancelled]
        )
        if cancelled_count == growth_count:
            growth_count = 0
    if adults < 1:
        return None
    return GroupTotal(adults, int(base["children"]) + growth_count)


def bind_explicit_total(users: tuple[str, ...]) -> OrderTotal | GroupTotal | None:
    if len(users) not in (2, 3):
        return None
    return _bind_order(users) or _bind_group(users)


def total_identity(state: OrderTotal | GroupTotal) -> tuple[str, str]:
    return (
        ("explicit_order_total", "zł")
        if isinstance(state, OrderTotal)
        else ("explicit_group_total", "osób")
    )


@dataclass(frozen=True)
class ExplicitTotalReceipt:
    users: tuple[str, ...]
    state: OrderTotal | GroupTotal
    calculation: CalculationEvidence

    @classmethod
    def from_evidence(
        cls, users: tuple[str, ...], state: OrderTotal | GroupTotal, evidence: Evidence
    ) -> ExplicitTotalReceipt:
        ident, unit = total_identity(state)
        expected = CalculationEvidence(
            ident, state.expression, calculate(state.expression), unit
        )
        if evidence.calculations != (expected,):
            raise EvidenceError("pilot_explicit_total_evidence_mismatch")
        return cls(users, state, expected)

    def recap(self, message: str, users: tuple[str, ...]) -> str | None:
        intent = _ORDER_RECAP if isinstance(self.state, OrderTotal) else _GROUP_RECAP
        if intent.fullmatch(message) is None:
            return None
        if users != self.users:
            return "Po zmianie danych potrzebuję aktualnego wyniku kalkulatora."
        return self.state.details(self.calculation.value, final=True)


@dataclass(frozen=True)
class PilotExplicitTotalAnswer(PublishedAnswer):
    explicit_total_receipt: ExplicitTotalReceipt
