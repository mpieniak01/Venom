"""Interpret explicit fitting measurements and bounds."""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat_quote import (
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
_EXTERNAL = re.compile(r"\b(?:na zewnątrz|zewnętrzn\w*)\b", re.I)
_OTHER_TASK = re.compile(
    r"\b(?:oblicz|wylicz|policz|wyznacz|oszacuj|przelicz|przetłumacz|zmieniam temat)\b",
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
    if not _CAPACITY.search(area) or _UNCERTAIN.search(area) or _EXTERNAL.search(area):
        return None
    return _dimensions(pair)


def _item(turns: Sequence[str]) -> Size | None:
    if len(turns) not in {1, 2} or any(
        _UNSUPPORTED.search(turn)
        or _UNCERTAIN.search(turn)
        or _EXTERNAL.search(turn)
        or (_OTHER_TASK.search(turn) and not _FIT.search(turn))
        for turn in turns
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


def _fit_capacity_hint(users: Sequence[str], index: int, capacity: Size) -> str:
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


def fit_hint(text: str, history: Sequence[HistoryMessage]) -> str:
    """Use only clear capacity, item and explicit side dimensions from users."""
    if is_text_transformation(text):
        return ""
    users = [without_quotes(turn.content) for turn in history if turn.role == "user"]
    users.append(without_quotes(text))
    for index in range(len(users) - 1, -1, -1):
        capacity = _capacity(users[index])
        if capacity is not None:
            return _fit_capacity_hint(users, index, capacity)
    return ""


_MINIMUM = re.compile(r"\b(?:co najmniej|minimum|minimaln\w*)\b", re.I)
_MAXIMUM = re.compile(r"\b(?:co najwyżej|maksimum|maksymaln\w*|najwyżej)\b", re.I)
_INTERNAL = re.compile(r"\b(?:wewnątrz|wewnętrzn\w*)\b", re.I)
_AXIS = re.compile(r"\b(długo|szeroko|wysoko|głęboko)(?:ść|ści)\b", re.I)
_CLAUSE_END = re.compile(r"[;!?\n]|[.,](?=\s|$)")
_BOUND_CORRECTION = re.compile(r"^\s*(?:korekta|poprawka)\s*:", re.I)
_CHECK_FIT = re.compile(r"\b(?:przymiark\w*|dopasowan\w*|zmieści\w*)\b", re.I)
_EXTERIOR_ONLY = re.compile(r"^\s*czy\s+sama?\b", re.I)
_FIT_CONTAINER = re.compile(r"\b(?:skrzynk|skrzync|futerał|futeral)\w*\b", re.I)
_CARRY_BOUND = re.compile(r"\b(?:bez zmian|nadal obowiązuje|zostaje)\b", re.I)
_ASK_DIMENSION = re.compile(
    r"\b(?:poproś|zapytaj)\s+o\s+(?:(?:potrzebn|właściw)[ye]\s+)?wymiar(?:y)?\b",
    re.I,
)
_NON_LITERAL_BOUND = re.compile(
    r"\b(?:około|chyba|mniej więcej|albo|lub|nie|jeśli|gdyby)\b|[×+/–−-]", re.I
)
_AXIS_LABELS = {
    "długo": "długość",
    "szeroko": "szerokość",
    "wysoko": "wysokość",
    "głęboko": "głębokość",
}


def _fit_bounds(text: str) -> dict[str, tuple[str, str]]:
    bounds: dict[str, tuple[str, str]] = {}
    for clause in _CLAUSE_END.split(text):
        minimum = bool(_MINIMUM.search(clause) and _INTERNAL.search(clause))
        maximum = bool(_MAXIMUM.search(clause) and _EXTERNAL.search(clause))
        if minimum == maximum:
            continue
        axes = _AXIS.findall(clause)
        length = _one_measurement(_LENGTH, clause)
        if (
            length is None
            and not _LENGTH.search(clause)
            and _CARRY_BOUND.search(clause)
        ):
            continue
        side = "minimum" if minimum else "maximum"
        if (
            length is None
            or len(axes) != 1
            or _NON_LITERAL_BOUND.search(clause)
            or side in bounds
        ):
            return {}
        bounds[side] = (_AXIS_LABELS[axes[0].casefold()], length[0])
    return bounds


def fit_bounds_hint(text: str, history: Sequence[HistoryMessage]) -> str:
    """Keep explicit interior fit requirements separate from exterior limits."""
    if is_text_transformation(text):
        return ""
    visible = without_quotes(text)
    if (
        (_CAPACITY.search(visible) or _FIT_CONTAINER.search(visible))
        and _ASK_DIMENSION.search(visible)
        and not _LENGTH.search(visible)
    ):
        return "Zadaj tylko jedno krótkie pytanie o wymiar potrzebny do przymiarki."
    if _OTHER_TASK.search(visible):
        return ""
    if (
        _EXTERIOR_ONLY.match(visible)
        and _EXTERNAL.search(visible)
        and _CHECK_FIT.search(visible)
        and not _INTERNAL.search(visible)
        and _one_measurement(_LENGTH, visible)
    ):
        return (
            "Sam pomiar zewnętrzny nie potwierdza dopasowania. "
            "W jednym lub dwóch zdaniach wskaż potrzebny pomiar wewnętrzny "
            "oraz jego minimum, jeśli jest w ustaleniach użytkownika."
        )
    bounds = _fit_bounds(visible)
    if (
        len(bounds) == 1
        and _BOUND_CORRECTION.match(visible)
        and _CHECK_FIT.search(visible)
    ):
        prior = next((t.content for t in reversed(history) if t.role == "user"), "")
        previous = (
            _fit_bounds(without_quotes(prior))
            if not is_text_transformation(prior)
            else {}
        )
        bounds = previous | bounds
    if len(bounds) != 2:
        return ""
    axis, minimum = bounds["minimum"]
    outer_axis, maximum = bounds["maximum"]
    if axis != outer_axis:
        return ""
    return (
        f"Podaj w odpowiedzi obie granice. Wymagana {axis} wewnętrzna "
        f"to co najmniej {minimum}. Dopuszczalna {axis} zewnętrzna to co najwyżej {maximum}. "
        "Do potwierdzenia dopasowania brakuje pomiaru. Z tych granic nie obliczaj luzu. "
        "Jeśli użytkownik chce instrukcji, w jednym zdaniu poleć osobno zmierzyć wnętrze i zewnętrze "
        "oraz porównać je z odpowiednimi granicami. Zachowaj podane jednostki. "
        "Zakończ po tej instrukcji bez dodatkowych zaleceń."
    )
