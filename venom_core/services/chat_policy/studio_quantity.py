"""Bind amounts to the unit and scope explicitly supplied in Studio conversations."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
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

_DURATION_VALUE = r"[0-9]{1,3}"
_DIRECTIONS = re.compile(rf"na dojazd do (?P<target>{_NAME}) mam dwa warianty", re.I)
_VIA_ROUTE = re.compile(
    rf"(?:do (?P<target>{_NAME}) )?przez (?P<label>{_NAME}) idę (?P<times>.+)", re.I
)
_NAMED_ROUTE = re.compile(
    rf"(?:trasa )?(?P<label>{_WORD}(?: {_WORD}){{0,3}}?)(?: zajmuje| trwa)? "
    rf"(?P<times>(?:{_DURATION_VALUE}|pieszo|łącznie) .+)",
    re.I,
)
_AXIS_JOIN = re.compile(r", (?:a|ale|lecz) | (?:i|oraz) ", re.I)
_BARE_MINUTES = re.compile(rf"(?P<value>{_DURATION_VALUE}) {_MINUTE}", re.I)
_VIA_TOTAL = re.compile(
    rf"(?:jestem(?: na miejscu)? po|cał[ay] (?:dojazd|podróż) trwa) "
    rf"(?P<value>{_DURATION_VALUE}) {_MINUTE}",
    re.I,
)
_AXIS_AMOUNT = re.compile(
    rf"(?P<value>{_DURATION_VALUE})(?: (?P<unit>{_MINUTE}))? (?P<scope>pieszo|łącznie|w sumie)"
    rf"|(?P<leading_scope>pieszo|łącznie|w sumie) (?P<leading_value>{_DURATION_VALUE})"
    rf"(?: (?P<leading_unit>{_MINUTE}))?",
    re.I,
)
_COMPARE = re.compile(
    r"wypisz różnicę, żebym mógł podjąć decyzję|"
    r"porównaj (?:obie trasy|oba warianty)(?: bez wybierania)?",
    re.I,
)
_SHORTER_ROUTE = re.compile(
    r"(?:no to )?(?:tę|ten) krótsz(?:ą|y)[.!]?|"
    r"(?:w takim razie )?wybierz krótszą(?: trasę)?[.!]?",
    re.I,
)
_WALK_DIFFERENCE = re.compile(
    r"(?:o ile różni się |a różnica )(?:sam |samego )?czas(?:u)? marszu\??", re.I
)
_TOTAL_DIFFERENCE = re.compile(
    r"(?:o ile różni się |a różnica )czas(?:u)? (?:łączn(?:y|ego)|całej podróży)\??",
    re.I,
)
_NOTICE_REQUEST = re.compile(
    r"(?:[.] )?(?:zrób z tego|podaj) trzy krótkie komunikaty,? bez wykrzykników"
    r"(?:,? (?:do wydruku na kartce|do wydruku|na kartkę))?[.]?",
    re.I,
)
_NOTICE_OPENING = r"(?:wydajemy|rozdajemy|odbieramy)"
_CLOCK = r"[0-9]{1,2}(?::[0-9]{2})?"
_NOTICE_SERVICE = re.compile(
    rf"(?P<service>(?:{_NOTICE_OPENING} (?P<items>{_WORD})"
    rf"|(?P<front_items>{_WORD}) {_NOTICE_OPENING}) (?P<place>(?:w|we|na|przy) {_NAME}))"
    rf" do (?P<clock>{_CLOCK})",
    re.I,
)
_STATUS = r"(?:bezpłatn|darmow|zniżkow)[aey]"
_ENTITLEMENT = re.compile(
    rf"(?P<count>jedna|jeden|pierwsza|pierwszy)"
    rf"(?: (?P<before>{_STATUS}))? (?P<item>{_WORD})(?: (?P<after>{_STATUS}))?"
    rf" na {_WORD}(?: {_WORD}){{0,3}}?(?: jest (?P<end>{_STATUS}))?",
    re.I,
)
_PAID_ITEM = re.compile(
    rf"(?P<ordinal>drug(?:a|ą|i)|każd[aąy] (?:kolejn|następn)[aąy]) "
    rf"(?P<phrase>można (?:pobrać|odebrać|kupić) za|kosztuje) (?P<price>{_MONEY}) zł",
    re.I,
)
_NOTICE_NAMES = {
    "bilety": ("bilet", "y"),
    "broszury": ("broszura", "a"),
    "identyfikatory": ("identyfikator", "y"),
    "mapy": ("mapa", "a"),
    "opaski": ("opaska", "a"),
    "plakietki": ("plakietka", "a"),
    "torby": ("torba", "a"),
}
_ENTITLEMENT_COUNT = {"a": {"jedna", "pierwsza"}, "y": {"jeden", "pierwszy"}}
_REMOVE_WE = re.compile(
    r"(?:(?:zapomniał(?:em|am), że to kartka dla gości|to kartka dla gości)[.] )?"
    r"usuń formę(?: [.]|[.]| , to kartka dla gości[.])?"
    r"(?: zachowaj wszystkie dane[.])?",
    re.I,
)
_CLOCK_CHANGE = re.compile(
    rf"zmień tylko godzinę odbioru na (?P<clock>{_CLOCK})[.]?", re.I
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
    target: str = ""
    via: bool = False

    def duration(self, scope: _Scope) -> _Amount:
        return self.walk if scope is _Scope.WALK else self.total


@dataclass(frozen=True)
class _RouteQuestion:
    options: tuple[_RouteOption, _RouteOption]
    scope: _Scope | None


@dataclass(frozen=True)
class _Notice:
    service: str
    items: str
    place: str
    clock: str
    entitlement: str
    ordinal: str
    price_phrase: str
    price: _Amount

    def render(self, *, for_guests: bool) -> str:
        opening = f"{self.service[0].upper()}{self.service[1:]}"
        if for_guests:
            items = f"{self.items[0].upper()}{self.items[1:]}"
            opening = f"{items} do odbioru {self.place}"
        return (
            f"{opening} do {self.clock}.\n{self.entitlement}.\n"
            f"{self.ordinal.capitalize()} {self.price_phrase} {self.price}."
        )


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


def _axis_amount(clause: str) -> tuple[_Amount, bool] | None:
    match = _AXIS_AMOUNT.fullmatch(clause)
    if match is None:
        return None
    unit = match["unit"] or match["leading_unit"]
    value = _number(match["value"] or match["leading_value"])
    kind = (match["scope"] or match["leading_scope"]).casefold()
    return _Amount(
        value, "min", _Scope.WALK if kind == "pieszo" else _Scope.WHOLE_ROUTE
    ), bool(unit)


def _route(clause: str) -> _RouteOption | None:
    via = _VIA_ROUTE.fullmatch(clause)
    match = via or _NAMED_ROUTE.fullmatch(clause)
    if match is None:
        return None
    parts = _AXIS_JOIN.split(match["times"])
    if len(parts) != 2:
        return None
    if via:
        walk_clause, total_clause = (
            _BARE_MINUTES.fullmatch(parts[0]),
            _VIA_TOTAL.fullmatch(parts[1]),
        )
        if walk_clause is None or total_clause is None:
            return None
        walk = _Amount(_number(walk_clause["value"]), "min", _Scope.WALK)
        total = _Amount(_number(total_clause["value"]), "min", _Scope.WHOLE_ROUTE)
    else:
        left, right = _axis_amount(parts[0]), _axis_amount(parts[1])
        if (
            left is None
            or right is None
            or not (left[1] or right[1])
            or left[0].scope is right[0].scope
        ):
            return None
        walk, total = (
            (left[0], right[0]) if left[0].scope is _Scope.WALK else (right[0], left[0])
        )
    if walk.value > total.value:
        return None
    return _RouteOption(
        match["label"], walk, total, (via["target"] or "") if via else "", bool(via)
    )


def _comparison_scope(question: str) -> _Scope | None:
    if _WALK_DIFFERENCE.fullmatch(question):
        return _Scope.WALK
    return _Scope.WHOLE_ROUTE if _TOTAL_DIFFERENCE.fullmatch(question) else None


def _route_question(parts: list[str]) -> _RouteQuestion | None:
    target = ""
    if len(parts) == 4 and (header := _DIRECTIONS.fullmatch(parts[0])):
        target = header["target"]
        parts = parts[1:]
    if len(parts) != 3:
        return None
    scope = _comparison_scope(parts[2])
    if scope is None and not _COMPARE.fullmatch(parts[2]):
        return None
    first, second = _route(parts[0]), _route(parts[1])
    if (
        first is None
        or second is None
        or first.label.casefold() == second.label.casefold()
        or first.via != second.via
    ):
        return None
    if (
        len(
            {
                place.casefold()
                for place in (target, first.target, second.target)
                if place
            }
        )
        > 1
    ):
        return None
    return _RouteQuestion((first, second), scope)


def _route_difference(question: _RouteQuestion, scope: _Scope) -> str | None:
    shorter, longer = sorted(
        question.options, key=lambda option: option.duration(scope).value
    )
    difference = longer.duration(scope).difference(shorter.duration(scope))
    if difference is None:
        return None
    metric = "Czas marszu" if scope is _Scope.WALK else "Czas całej podróży"
    if difference.value == 0:
        return f"{metric} jest taki sam w obu wariantach. Różnica: {difference}."
    route = f"przez {shorter.label}" if shorter.via else f"na trasie: {shorter.label}"
    return f"{metric} różni się o {difference}. Krócej jest {route}."


def _route_comparison(options: tuple[_RouteOption, _RouteOption]) -> tuple[str, str]:
    first, second = options
    walk_first, walk_second = sorted(options, key=lambda option: option.walk.value)
    total_first, total_second = sorted(options, key=lambda option: option.total.value)
    walk_path = (
        f"przez {walk_first.label}"
        if walk_first.via
        else f"na trasie: {walk_first.label}"
    )
    total_path = (
        f"przez {total_first.label}"
        if total_first.via
        else f"na trasie: {total_first.label}"
    )
    if first.walk.value == second.walk.value:
        walk = f"Marsz na obu trasach trwa {first.walk}."
    else:
        walk = f"Krótszy marsz jest {walk_path} ({walk_first.walk} wobec {walk_second.walk})."
    if first.total.value == second.total.value:
        total = f"Cały dojazd na obu trasach trwa {first.total}."
    else:
        total = f"Krótszy dojazd jest {total_path} ({total_first.total} wobec {total_second.total})."
    return walk, total


def _clock(value: str) -> str | None:
    hour, _, minute = value.partition(":")
    if int(hour) > 23 or (minute and int(minute) > 59):
        return None
    return f"{int(hour):02}:{minute or '00'}"


def _ordinal_scope(ordinal: str, gender: str, *, nominative: bool) -> _Scope | None:
    end = "y" if gender == "y" else ("a" if nominative else "ą")
    second = "drugi" if gender == "y" else f"drug{end}"
    if ordinal == second:
        return _Scope.SECOND
    if ordinal in {f"każd{end} kolejn{end}", f"każd{end} następn{end}"}:
        return _Scope.EVERY_LATER
    return None


def _notice(text: str) -> _Notice | None:
    visible = " ".join(without_quotes(text).split())
    quoted = single_quoted_operand(text)
    if quoted is None or not _NOTICE_REQUEST.fullmatch(visible):
        return None
    parts = _clauses(" ".join(quoted.split()))
    if len(parts) != 3:
        return None
    service = _NOTICE_SERVICE.fullmatch(parts[0])
    entitlement = _ENTITLEMENT.fullmatch(parts[1])
    paid = _PAID_ITEM.fullmatch(parts[2])
    if service is None or entitlement is None or paid is None:
        return None
    items = service["items"] or service["front_items"]
    noun = _NOTICE_NAMES.get(items.casefold())
    if noun is None:
        return None
    item, gender = noun
    statuses = [
        entitlement[key].casefold()
        for key in ("before", "after", "end")
        if entitlement[key]
    ]
    if (
        entitlement["item"].casefold() != item
        or entitlement["count"].casefold() not in _ENTITLEMENT_COUNT[gender]
        or len(statuses) != 1
        or not statuses[0].endswith(gender)
    ):
        return None
    ordinal = paid["ordinal"].casefold()
    price_phrase = paid["phrase"].casefold()
    scope = _ordinal_scope(ordinal, gender, nominative=price_phrase == "kosztuje")
    clock = _clock(service["clock"])
    if scope is None or clock is None:
        return None
    benefit = f"{parts[1][0].upper()}{parts[1][1:]}"
    return _Notice(
        service["service"],
        items,
        service["place"],
        clock,
        benefit,
        ordinal,
        price_phrase,
        _Amount(_number(paid["price"]), "zł", scope),
    )


def _notice_followup(current: str, previous: str) -> str | None:
    correction = _CLOCK_CHANGE.fullmatch(current)
    visible = " ".join(without_quotes(current).split())
    for_guests = single_quoted_operand(current) == "my" and bool(
        _REMOVE_WE.fullmatch(visible)
    )
    if correction is None and not for_guests:
        return None
    notice = _notice(previous)
    if notice is None:
        return None
    if correction is None:
        return notice.render(for_guests=for_guests)
    clock = _clock(correction["clock"])
    return replace(notice, clock=clock).render(for_guests=False) if clock else None


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
    if route := _route_question(pieces):
        if route.scope is not None:
            return _route_difference(route, route.scope)
        return " ".join(_route_comparison(route.options))
    if notice := _notice(current):
        return notice.render(for_guests=False)
    previous = _prior_user(history)
    if not previous or len(previous) > 640:
        return None
    scope = _comparison_scope(current)
    shorter = _SHORTER_ROUTE.fullmatch(current)
    if (scope is not None or shorter) and (
        route := _route_question(_clauses(previous))
    ):
        if scope is not None:
            return _route_difference(route, scope)
        return " ".join(
            (*_route_comparison(route.options), "Chodzi Ci o marsz czy cały dojazd?")
        )
    return _notice_followup(current, previous)
