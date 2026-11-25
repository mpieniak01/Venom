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
_SPLIT_NUMBER = re.compile(r"[0-9][ \t\u00a0\u202f]+[0-9]")
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
    if len(matches) != 1 or _SPLIT_NUMBER.search(text):
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


_MINIMUM = re.compile(r"\b(?:co najmniej|przynajmniej|minimum|minimaln\w*)\b", re.I)
_MAXIMUM = re.compile(r"\b(?:co najwyżej|maksimum|maksymaln\w*|najwyżej)\b", re.I)
_INTERNAL = re.compile(r"\b(?:wewnątrz|wewnętrzn\w*|w środku)\b", re.I)
_AXIS_STEM = r"długo|szeroko|wysoko|głęboko"
_AXIS = re.compile(rf"\b({_AXIS_STEM})(?:ść|ści)\b", re.I)
_CLAUSE_END = re.compile(
    r"[;!?\n]|\.(?=\s|$)|(?:,\s*|(?<!\s)\s+)(?:a|natomiast)\s+", re.I
)
_BOUND_CORRECTION = re.compile(r"^\s*(?:korekta|poprawka|zmiana)\s*:", re.I)
_EXTERIOR_MEASURE = re.compile(
    rf"(?:(?P<question>czy)\s+(?:sam[ao]?\s+)?)?"
    rf"(?:zmierzon[ay]\s+)?(?:(?:{_AXIS_STEM})ść|pomiar|wymiar)\s+"
    r"(?:na zewnątrz|zewnętrzn[ay])(?:\s+(?:ma|wynosi|to))?",
    re.I,
)
_FIT_CONFIRMATION = (
    r"(?:wystarcz[ay]\s+do\s+(?:potwierdzenia\s+)?dopasowania"
    r"|pozwala\s+potwierdzić\s+dopasowanie|potwierdza\s+dopasowanie)"
)
_MEASURE_QUESTION_END = re.compile(rf"{_FIT_CONFIRMATION}\?", re.I)
_SEPARATE_FIT_QUESTION = re.compile(
    rf"\.\s*czy\s+(?:to\s+{_FIT_CONFIRMATION}|"
    r"(?:skrzynka|futerał|pudełko|pojemnik|przedmiot|kartka)\s+"
    r"(?:pasuje|będzie pasując[ay]|zmieści się|się zmieści))\?",
    re.I,
)
_FIT_CONTAINER = re.compile(r"\b(?:skrzynk|skrzync|futerał|futeral)\w*\b", re.I)
_CARRY_BOUND = re.compile(
    r"\b(?:bez zmian|nadal obowiązuje|zostaje|ten sam|ta sama)\b", re.I
)
_ASK_DIMENSION = re.compile(
    r"(?:poproś|zapytaj)\s+o\s+(?:(?:potrzebn|właściw)[ye]\s+)?"
    r"wymiary?\s+(?P<container>[^\W\d_]+)[.!?]?",
    re.I,
)
_FIT_INSTRUCTION = re.compile(r"\b(?:przymiark\w*|dopasowan\w*|co zmierzyć)\b", re.I)
_EXTRA_TASK = re.compile(
    r"\b(?:napisz|podaj|wyjaśnij|zaproponuj|poleć|porównaj|dobierz|"
    r"przygotuj|przepisz|zacytuj|streść|zrób|podsumuj|sprawdź|opisz|przetłumacz)\b",
    re.I,
)
_FIT_COMMAND = re.compile(
    r"^\s*(?:napisz|podaj|wyjaśnij|opisz)\s*,?\s*(?:co zmierzyć|"
    r"(?:krótką\s+)?instrukcję (?:przymiarki|dopasowania)|"
    r"jak (?:sprawdzić dopasowanie|zmierzyć oba wymiary))\s*$",
    re.I,
)
_CANCEL_BOUND = re.compile(r"\b(?:nie obowiązuje|już nie|anuluj|rezygnuję)\b", re.I)
_BOUND_VALUE = re.compile(rf"({_NUMBER})\s*({_UNIT})", re.I)
_NON_LITERAL_BOUND = re.compile(
    r"\b(?:około|chyba|mniej więcej|albo|lub|nie|jeśli|gdyby)\b|[×+/–−-]", re.I
)
_AXIS_LABELS = {
    "długo": "długość",
    "szeroko": "szerokość",
    "wysoko": "wysokość",
    "głęboko": "głębokość",
}
Bound = tuple[str, str]
Bounds = dict[str, Bound]


def _axis_labels(text: str) -> set[str]:
    return {_AXIS_LABELS[axis.casefold()] for axis in _AXIS.findall(text)}


def _literal_bound(clause: str) -> Bound | None:
    axes = _axis_labels(clause)
    length = _one_measurement(_LENGTH, clause)
    if length is None or len(axes) != 1:
        return None
    return axes.pop(), length[0]


def _fit_bounds(text: str) -> Bounds | None:
    bounds: Bounds = {}
    for clause in _CLAUSE_END.split(text):
        minimum = bool(_MINIMUM.search(clause) and _INTERNAL.search(clause))
        maximum = bool(_MAXIMUM.search(clause) and _EXTERNAL.search(clause))
        if minimum and maximum:
            return None
        if not (minimum or maximum):
            continue
        if _NON_LITERAL_BOUND.search(clause):
            return None
        if _CARRY_BOUND.search(clause) and not _LENGTH.search(clause):
            continue
        side = "minimum" if minimum else "maximum"
        bound = _literal_bound(clause)
        if bound is None or side in bounds:
            return None
        bounds[side] = bound
    return bounds


def _visible_bounds(text: str) -> Bounds | None:
    if (
        is_text_transformation(text)
        or without_quotes(text) != text
        or _OTHER_TASK.search(text)
    ):
        return None
    for clause in _CLAUSE_END.split(text):
        if _EXTRA_TASK.search(clause) and not _FIT_COMMAND.fullmatch(clause):
            return None
        if _CANCEL_BOUND.search(clause) and (
            any(
                marker.search(clause)
                for marker in (_MINIMUM, _MAXIMUM, _INTERNAL, _EXTERNAL)
            )
        ):
            return None
    return _fit_bounds(text)


def _earlier_bounds(history: Sequence[HistoryMessage]) -> Bounds:
    updates: Bounds = {}
    for turn in reversed(history):
        if turn.role != "user":
            continue
        parsed = _visible_bounds(turn.content)
        if not parsed:
            break
        if len(parsed) == 2:
            return parsed | updates
        if not _BOUND_CORRECTION.match(turn.content) or not _FIT_INSTRUCTION.search(
            turn.content
        ):
            break
        updates = parsed | updates
    return {}


def _in_centimeters(value: str) -> Decimal:
    match = _BOUND_VALUE.fullmatch(value)
    assert match is not None
    return _measurement(*match.groups())


def _bounds_conflict(axis: str, minimum: str, maximum: str) -> str | None:
    if _in_centimeters(minimum) <= _in_centimeters(maximum):
        return None
    return (
        f"Granice dla wymiaru „{axis}” są sprzeczne. "
        f"Minimum wewnętrzne {minimum} przekracza maksimum zewnętrzne {maximum}. "
        "Podaj zgodne wymiary."
    )


def _exterior_measurement(text: str) -> re.Match[str] | None:
    length = _one_measurement(_LENGTH, text)
    if length is None:
        return None
    prefix = _EXTERIOR_MEASURE.fullmatch(text[: length.start()].strip())
    if prefix is None:
        return None
    suffix = text[length.end() :].strip()
    question = _MEASURE_QUESTION_END if prefix["question"] else _SEPARATE_FIT_QUESTION
    return length if question.fullmatch(suffix) else None


def fit_bounds_reply(text: str, history: Sequence[HistoryMessage]) -> str | None:
    """Report independent constraints or verify a single exterior measurement."""
    bounds = _visible_bounds(text)
    if bounds is None:
        return None
    if (
        len(bounds) == 1
        and _BOUND_CORRECTION.match(text)
        and _FIT_INSTRUCTION.search(text)
    ):
        bounds = _earlier_bounds(history) | bounds
    if (
        len(bounds) == 2
        and bounds["minimum"][0] == bounds["maximum"][0]
        and "?" not in text
    ):
        axis, minimum = bounds["minimum"]
        _, maximum = bounds["maximum"]
        return _bounds_conflict(axis, minimum, maximum) or (
            f"Wewnętrzna {axis} musi wynosić co najmniej {minimum}, a zewnętrzna "
            f"co najwyżej {maximum}. Zmierz obie osobno i porównaj z tymi granicami."
        )
    if bounds or (length := _exterior_measurement(text)) is None:
        return None
    return _compare_exterior_measurement(length[0], text, history)


def _compare_exterior_measurement(
    value: str, text: str, history: Sequence[HistoryMessage]
) -> str | None:
    prior = _earlier_bounds(history)
    if len(prior) != 2:
        return None
    axis, minimum = prior["minimum"]
    outer_axis, maximum = prior["maximum"]
    if axis != outer_axis or _axis_labels(text) - {axis}:
        return None
    if conflict := _bounds_conflict(axis, minimum, maximum):
        return conflict
    outcome = (
        "mieści się w limicie"
        if _in_centimeters(value) <= _in_centimeters(maximum)
        else "przekracza limit"
    )
    return (
        f"Zewnętrzna {axis} {value} {outcome} {maximum}. "
        f"Sam ten pomiar nie potwierdza dopasowania. Zmierz też {axis} wewnętrzną, która musi wynosić co najmniej {minimum}."
    )


def fit_bounds_hint(text: str, history: Sequence[HistoryMessage]) -> str:
    """Request a missing dimension or use the bounds as context on the model path."""
    if answer := fit_bounds_reply(text, history):
        return answer
    if is_text_transformation(text):
        return ""
    visible = without_quotes(text)
    request = _ASK_DIMENSION.fullmatch(visible.strip())
    if request and (
        _CAPACITY.fullmatch(request["container"])
        or _FIT_CONTAINER.fullmatch(request["container"])
    ):
        return "Zadaj tylko jedno krótkie pytanie o wymiar potrzebny do przymiarki."
    if re.match(r"\s*czy\s+sam[ao]?\b", visible, re.I) and _exterior_measurement(
        visible
    ):
        return (
            "Sam pomiar zewnętrzny nie potwierdza dopasowania. "
            "Krótko wskaż potrzebny pomiar wewnętrzny."
        )
    return ""
