"""Compare explicitly supplied two-dimensional fitting measurements."""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.academy.qualified_chat_quote import (
    is_text_transformation,
    without_quotes,
)

_NUMBER = r"[0-9]{1,5}(?:[.,][0-9]{1,3})?"
_UNIT = r"(?:mm|cm|m)\b"
_DIMENSIONS = re.compile(
    rf"(?<![\w.,+\-])(?P<first>{_NUMBER})\s*(?P<first_unit>{_UNIT})?\s*"
    rf"(?:na\b|[×x])\s*(?P<second>{_NUMBER})\s*(?P<second_unit>{_UNIT})?",
    re.I,
)
_LENGTH = re.compile(rf"(?<![\w.,+\-]){_NUMBER}\s*{_UNIT}", re.I)
_THIRD_AXIS = re.compile(rf"\s*(?:na\b|[×x])\s*{_NUMBER}", re.I)
_SIDE = re.compile(
    rf"\b(?P<side>dłuższ|krótsz)y\s+bok\s+(?:ma|mierzy|wynosi|to)\s+"
    rf"(?P<number>{_NUMBER})\s*(?P<unit>{_UNIT})",
    re.I,
)
_CAPACITY = re.compile(
    r"\b(?:skrytk|skrytc|pudełk|szuflad|kopert|koperc|ramk|ramc|otwor|otwór|pojemn|kiesze|waliz)\w*\b",
    re.I,
)
_FIT = re.compile(
    r"\b(?:pasuj|mieści|zmieści|wpas|włoż|wkład|wsun|wsuw|umieść|"
    r"zostawi|większ|mniejsz)\w*\b",
    re.I,
)
_NO_FOLD = re.compile(
    r"\b(?:bez (?:zginania|gięcia|składania|zwijania)|"
    r"nie (?:zginaj|składaj|zwijaj)|"
    r"nie (?:chcę|mogę|można|wolno)(?: [^\W\d_]+){0,2} "
    r"(?:zginać|zgiąć|składać|złożyć|zwijać|zwinąć))\b",
    re.I,
)
_UNSUPPORTED = re.compile(
    r"\b(?:bez (?:obrotu|obracania)|"
    r"nie (?:obracaj|obracam|(?:mogę|można|wolno)(?: [^\W\d_]+){0,2} (?:obrócić|obracać))|"
    r"głębokoś\w*|gruboś\w*|przekątn\w*|margines\w*|luz\w*)\b",
    re.I,
)
_UNCERTAIN = re.compile(
    r"\b(?:około|chyba|mniej więcej|co najmniej|co najwyżej|albo|lub)\b", re.I
)
_CENTIMETERS = {"mm": Decimal("0.1"), "cm": Decimal(1), "m": Decimal(100)}
Size = tuple[Decimal, Decimal]


def _measurement(number: str, unit: str) -> Decimal:
    return Decimal(number.replace(",", ".")) * _CENTIMETERS[unit.casefold()]


def _one_measurement(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    remainder = f"{text[: match.start()]} {text[match.end() :]}"
    if _LENGTH.search(remainder) or _THIRD_AXIS.match(text, match.end()):
        return None
    return match


def _dimensions(match: re.Match[str]) -> Size | None:
    first_unit = match["first_unit"] or match["second_unit"]
    if first_unit is None:
        return None
    first = _measurement(match["first"], first_unit)
    second = _measurement(match["second"], match["second_unit"] or first_unit)
    if min(first, second) <= 0:
        return None
    return min(first, second), max(first, second)


def _capacity(text: str) -> Size | None:
    if not (_NO_FOLD.search(text) and _FIT.search(text)) or _UNSUPPORTED.search(text):
        return None
    pair = _one_measurement(_DIMENSIONS, text)
    if pair is None:
        return None
    area = text[max(0, pair.start() - 32) : pair.end() + 32]
    if not _CAPACITY.search(area) or _UNCERTAIN.search(area):
        return None
    return _dimensions(pair)


def _item(turns: Sequence[str]) -> Size | None:
    if len(turns) not in {1, 2} or any(
        _UNSUPPORTED.search(turn) or _UNCERTAIN.search(turn) for turn in turns
    ):
        return None
    pair = _one_measurement(_DIMENSIONS, turns[0])
    if pair is None or _CAPACITY.search(turns[0]):
        return None
    size = _dimensions(pair)
    if size is None or len(turns) == 1:
        return size
    correction = _one_measurement(_SIDE, turns[1])
    if correction is None or _CAPACITY.search(turns[1]):
        return None
    revised = _measurement(correction["number"], correction["unit"])
    if correction["side"].casefold() == "dłuższ":
        size = size[0], revised
    else:
        size = revised, size[1]
    return size if 0 < size[0] <= size[1] else None


def _display(number: Decimal) -> str:
    return format(number.normalize(), "f").replace(".", ",")


def fit_hint(text: str, history: Sequence[HistoryMessage]) -> str:
    """Use only clear capacity, item and explicit side dimensions from users."""
    if is_text_transformation(text):
        return ""
    users = [without_quotes(turn.content) for turn in history if turn.role == "user"]
    users.append(without_quotes(text))
    for index in range(len(users) - 1, -1, -1):
        capacity = _capacity(users[index])
        if capacity is None:
            continue

        if index == len(users) - 1:
            if any(_DIMENSIONS.search(turn) for turn in users[:index]):
                return ""
            return "Brakuje wymiarów przedmiotu. Zapytaj krótko o długości obu boków."

        size = _item(users[index + 1 :])
        if size is None:
            return ""
        fits = size[0] <= capacity[0] and size[1] <= capacity[1]
        comparisons = " oraz ".join(
            f"{_display(side)} cm {'≤' if side <= limit else '>'} {_display(limit)} cm"
            for side, limit in zip(size, capacity, strict=True)
        )
        outcome = "mieści się" if fits else "nie mieści się"
        return (
            f"Aktualne porównanie boków wynosi {comparisons}. "
            f"Przedmiot {outcome} bez składania. "
            "Zacznij od nazwy miejsca lub wyboru zgodnego z regułą użytkownika. "
            "Uzasadnij go krótko decydującym porównaniem i zakończ odpowiedź."
        )
    return ""
