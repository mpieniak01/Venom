"""Bind amounts to the unit and scope explicitly supplied in Studio conversations."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Literal

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat_quote import (
    single_quoted_operand,
    without_quotes,
)
from venom_core.services.grounded_calculator import result_with_unit

_WORD = r"[^\W\d_]+"
_NAME = rf"{_WORD}(?: {_WORD}){{0,3}}"
_MONEY = r"[0-9]{1,6}(?:[,.][0-9]{1,2})?"
_MINUTE = r"min(?:ut(?:a|y|ach)?)?"
_PURCHASE = re.compile(
    rf"(?:na {_NAME}(?: {_WORD}){{0,3}} )?chcę zamówić "
    rf"(?:(?P<count>[1-9][0-9]?|dwie|dwa|trzy|cztery) )?(?:identyczne )?{_NAME}",
    re.I,
)
_DAY_NAMES = {
    "jutro": "jutro",
    "poniedziałek": "poniedziałku",
    "wtorek": "wtorku",
    "środę": "środy",
    "czwartek": "czwartku",
    "piątek": "piątku",
    "sobotę": "soboty",
    "niedzielę": "niedzieli",
}
_DAY = "|".join(_DAY_NAMES)
_DAY_ENDING = "|".join(_DAY_NAMES.values())
_OFFER = re.compile(
    rf"u (?P<seller>{_WORD}(?: {_WORD}){{0,3}}?) "
    rf"(?:(?P<scope>komplet|zestaw|sztuka) )?kosztuje (?P<price>{_MONEY}) zł"
    rf"(?:(?:,| i) (?:jest gotow[ayoe]|odbiór) (?P<direct>jutro|(?:w|we) (?:{_DAY}))"
    rf"| i czeka się do (?P<by>{_DAY_ENDING}))",
    re.I,
)
_PRICE_PRIORITY = re.compile(
    rf"(?P<day>{_DAY}) mi pasuje, "
    r"(?:liczę każdy grosz|zależy mi na najniższej cenie|wybieram niższą cenę)",
    re.I,
)
_COUNT_WORDS = {"dwie": 2, "dwa": 2, "trzy": 3, "cztery": 4}

_DIRECTIONS = re.compile(rf"na dojazd do {_NAME} mam dwa warianty", re.I)
_ROUTE = re.compile(
    rf"przez (?P<label>{_NAME}) idę (?P<walk>[0-9]{{1,3}}) {_MINUTE}"
    rf"(?: i|, ale) (?:jestem(?: na miejscu)? po (?P<after>[0-9]{{1,3}}) {_MINUTE}"
    rf"|cały dojazd trwa (?P<total>[0-9]{{1,3}}) {_MINUTE})",
    re.I,
)
_COMPARE = re.compile(
    r"wypisz różnicę, żebym mógł podjąć decyzję|"
    r"porównaj (?:obie trasy|oba warianty)(?: bez wybierania)?",
    re.I,
)
_SHORTER_ROUTE = re.compile(
    r"(?:no to )?(?:tę|ten) krótsz(?:ą|y)[.!]?|wybierz krótszą trasę[.!]?",
    re.I,
)
_NOTICE_REQUEST = re.compile(
    r"(?:[.] )?zrób z tego trzy krótkie komunikaty, bez wykrzykników,"
    r" (?:do wydruku na kartce|do wydruku|na kartkę)[.]?",
    re.I,
)
_NOTICE = re.compile(
    rf"(?P<opening>wydajemy|rozdajemy) (?P<items>{_WORD}) "
    rf"(?P<place>(?:w|we|na|przy) {_NAME}) do (?P<clock>[0-9]{{1,2}}(?::[0-9]{{2}})?)[.] "
    rf"(?P<free>jedna bezpłatna|jeden bezpłatny|jedno bezpłatne) (?P<item>{_WORD}) "
    rf"na (?P<recipient>{_NAME})[.] (?P<ordinal>drugą|drugi|drugie|każdą kolejną|każdy kolejny|każde kolejne) "
    rf"można (?P<pickup>pobrać|odebrać) za (?P<price>{_MONEY}) zł[.]?",
    re.I,
)
_NOTICE_NAMES = {
    "broszury": ("broszura", "jedna bezpłatna", "drugą", "każdą kolejną"),
    "identyfikatory": ("identyfikator", "jeden bezpłatny", "drugi", "każdy kolejny"),
    "mapy": ("mapa", "jedna bezpłatna", "drugą", "każdą kolejną"),
    "opaski": ("opaska", "jedna bezpłatna", "drugą", "każdą kolejną"),
    "plakietki": ("plakietka", "jedna bezpłatna", "drugą", "każdą kolejną"),
}
_REMOVE_WE = re.compile(
    r"(?:(?:zapomniał(?:em|am), że to kartka dla gości|to kartka dla gości)[.] )?"
    r"usuń formę(?: [.]|[.])?",
    re.I,
)


class _Scope(Enum):
    BUNDLE = "bundle"
    ITEM = "item"
    WALK = "walk"
    WHOLE_ROUTE = "whole_route"
    SECOND = "second"
    EVERY_LATER = "every_later"


@dataclass(frozen=True)
class _Amount:
    value: Decimal
    unit: Literal["zł", "min"]
    scope: _Scope

    def __str__(self) -> str:
        return f"{str(self.value).replace('.', ',')} {self.unit}"

    def difference(self, other: _Amount) -> _Amount | None:
        if self.unit != other.unit or self.scope != other.scope:
            return None
        result = result_with_unit(f"{self.value}-{other.value}", self.unit)["value"]
        return (
            _Amount(Decimal(result), self.unit, self.scope)
            if result is not None
            else None
        )


@dataclass(frozen=True)
class _Offer:
    seller: str
    price: _Amount
    day: str

    def bundle(self, count: int | None) -> _Offer | None:
        if self.price.scope is _Scope.BUNDLE:
            return self
        if count is None:
            return None
        total = result_with_unit(f"{self.price.value}*{count}", self.price.unit)[
            "value"
        ]
        if total is None:
            return None
        return _Offer(
            self.seller,
            _Amount(Decimal(total), self.price.unit, _Scope.BUNDLE),
            self.day,
        )


@dataclass(frozen=True)
class _RouteOption:
    label: str
    walk: _Amount
    total: _Amount


@dataclass(frozen=True)
class _Notice:
    opening: str
    items: str
    place: str
    clock: str
    free_line: str
    second: str
    every_later: str
    pickup: str
    price: _Amount

    def render(self, *, for_guests: bool) -> str:
        first = (
            f"{self.opening.capitalize()} {self.items} {self.place} do {self.clock}."
        )
        if for_guests:
            items = f"{self.items[0].upper()}{self.items[1:]}"
            first = f"{items} do odbioru {self.place} do {self.clock}."
        ordinal = self.second if self.price.scope is _Scope.SECOND else self.every_later
        return f"{first}\n{self.free_line}\n{ordinal.capitalize()} można {self.pickup} za {self.price}."


def _number(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _order_size(value: str | None) -> int | None:
    if value is None:
        return None
    return (
        int(value)
        if value.isascii() and value.isdecimal()
        else _COUNT_WORDS[value.casefold()]
    )


def _offer(clause: str, *, inherited_bundle: bool = False) -> _Offer | None:
    match = _OFFER.fullmatch(clause)
    if match is None:
        return None
    scope = (match["scope"] or "").casefold()
    if not scope and not inherited_bundle:
        return None
    price_scope = _Scope.ITEM if scope == "sztuka" else _Scope.BUNDLE
    price = _Amount(_number(match["price"]), "zł", price_scope)
    direct = match["direct"]
    day = direct.split()[-1].casefold() if direct else match["by"].casefold()
    return _Offer(match["seller"], price, _DAY_NAMES.get(day, day))


def _price_choice(parts: list[str]) -> str | None:
    if len(parts) != 4:
        return None
    intent = _PURCHASE.fullmatch(parts[0])
    priority = _PRICE_PRIORITY.fullmatch(parts[3])
    first = _offer(parts[1])
    if intent is None or priority is None or first is None:
        return None
    second = _offer(parts[2], inherited_bundle=first.price.scope is _Scope.BUNDLE)
    if second is None or first.seller.casefold() == second.seller.casefold():
        return None
    count = _order_size(intent["count"])
    first_bundle, second_bundle = first.bundle(count), second.bundle(count)
    if first_bundle is None or second_bundle is None:
        return None
    lower, higher = sorted(
        (first_bundle, second_bundle), key=lambda offer: offer.price.value
    )
    if (
        lower.day != _DAY_NAMES[priority["day"].casefold()]
        or lower.price.value == higher.price.value
    ):
        return None
    difference = higher.price.difference(lower.price)
    if difference is None:
        return None
    return (
        f"Wybierz ofertę u {lower.seller}. Całe zamówienie kosztuje {lower.price}, "
        f"czyli o {difference} mniej niż u {higher.seller}, a termin Ci odpowiada."
    )


def _route(clause: str) -> _RouteOption | None:
    match = _ROUTE.fullmatch(clause)
    if match is None:
        return None
    walk, total = _number(match["walk"]), _number(match["after"] or match["total"])
    if walk > total:
        return None
    return _RouteOption(
        match["label"],
        _Amount(walk, "min", _Scope.WALK),
        _Amount(total, "min", _Scope.WHOLE_ROUTE),
    )


def _route_options(parts: list[str]) -> tuple[_RouteOption, _RouteOption] | None:
    if (
        len(parts) != 4
        or not _DIRECTIONS.fullmatch(parts[0])
        or not _COMPARE.fullmatch(parts[3])
    ):
        return None
    first, second = _route(parts[1]), _route(parts[2])
    if (
        first is None
        or second is None
        or first.label.casefold() == second.label.casefold()
    ):
        return None
    return first, second


def _route_comparison(options: tuple[_RouteOption, _RouteOption]) -> tuple[str, str]:
    first, second = options
    walk_first, walk_second = sorted(options, key=lambda option: option.walk.value)
    total_first, total_second = sorted(options, key=lambda option: option.total.value)
    if first.walk.value == second.walk.value:
        walk = f"Marsz na obu trasach trwa {first.walk}."
    else:
        walk = f"Krótszy marsz jest przez {walk_first.label} ({walk_first.walk} wobec {walk_second.walk})."
    if first.total.value == second.total.value:
        total = f"Cały dojazd na obu trasach trwa {first.total}."
    else:
        total = f"Krótszy dojazd jest przez {total_first.label} ({total_first.total} wobec {total_second.total})."
    return walk, total


def _notice(text: str) -> _Notice | None:
    visible = " ".join(without_quotes(text).split())
    quoted = single_quoted_operand(text)
    if quoted is None or not _NOTICE_REQUEST.fullmatch(visible):
        return None
    match = _NOTICE.fullmatch(" ".join(quoted.split()))
    if match is None:
        return None
    noun = _NOTICE_NAMES.get(match["items"].casefold())
    if noun is None:
        return None
    item, free, second, every_later = noun
    if (match["item"].casefold(), match["free"].casefold()) != (item, free):
        return None
    ordinal = match["ordinal"].casefold()
    if ordinal not in {second, every_later}:
        return None
    hour, _, minute = match["clock"].partition(":")
    if int(hour) > 23 or (minute and int(minute) > 59):
        return None
    unit_scope = _Scope.SECOND if ordinal == second else _Scope.EVERY_LATER
    return _Notice(
        match["opening"],
        match["items"],
        match["place"],
        f"{int(hour):02}:{minute or '00'}",
        f"{match['free'].capitalize()} {match['item']} na {match['recipient']}.",
        second,
        every_later,
        match["pickup"].casefold(),
        _Amount(_number(match["price"]), "zł", unit_scope),
    )


def _clauses(text: str) -> list[str]:
    return text.rstrip(".!?").split(". ")


def _prior_user(history: Sequence[HistoryMessage]) -> str:
    if len(history) < 2:
        return ""
    previous, reply = history[-2:]
    if previous.role != "user" or reply.role != "assistant" or previous.material_ids:
        return ""
    return " ".join(previous.content.split())


def studio_quantity(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Answer bounded offer, route or notice requests from the current user source."""
    if len(text) > 640:
        return None
    current = " ".join(text.split())
    pieces = _clauses(current)
    if answer := _price_choice(pieces):
        return answer
    if routes := _route_options(pieces):
        return " ".join(_route_comparison(routes))
    if notice := _notice(current):
        return notice.render(for_guests=False)
    previous = _prior_user(history)
    if not previous or len(previous) > 640:
        return None
    if _SHORTER_ROUTE.fullmatch(current) and (
        routes := _route_options(_clauses(previous))
    ):
        return " ".join(
            (*_route_comparison(routes), "Chodzi Ci o marsz czy cały dojazd?")
        )
    visible = " ".join(without_quotes(current).split())
    if single_quoted_operand(current) == "my" and _REMOVE_WE.fullmatch(visible):
        if notice := _notice(previous):
            return notice.render(for_guests=True)
    return None
