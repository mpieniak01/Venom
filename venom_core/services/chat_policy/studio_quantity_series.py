"""Bind ordered values and scoped volume allocations before calculating."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum, auto

from venom_core.services.chat_policy.studio_calculation_plan import StudioCalculation

_NUM = r"-?[0-9]{1,7}(?:[,.][0-9]{1,4})?"
_UNITS = r"sekund(?:y|ę|ach)?|minut(?:y|ę|ach)?|kg|ml|min|s|g|l"
_LIST = re.compile(
    rf"(?<![\w.,-])(?P<values>{_NUM}(?:,\s+{_NUM}){{0,6}}(?:\s+(?:i|oraz)\s+|,\s+){_NUM})"
    rf"(?:\s+(?P<unit>{_UNITS})\b)?",
    re.I,
)
_NUMBER = re.compile(rf"(?<![\w-]){_NUM}(?![\w-]|[,.][0-9])")
_CLAUSE = re.compile(r"[.!?](?:\s+|$)")
_MEASUREMENT = re.compile(rf"(?P<value>{_NUM})\s*(?P<unit>{_UNITS})\b", re.I)
_SOURCE = re.compile(
    r"\b(?:odczyt\w*|pomiar\w*|odcink\w*|ocen\w*|wynik\w*|list[ay]|obserwacj\w*|dane|zanotowano)\b",
    re.I,
)
_SPECULATIVE = re.compile(
    r"\b(?:jeśli|jeżeli|gdyby|może|prawdopodobnie|przypuśćmy|załóżmy)\b", re.I
)
_PENDING = re.compile(
    r"\b(?:jeszcze nie|brak|nie mamy|nie powstał\w*|niewykonan\w*)\b", re.I
)
_ORDINALS = ("pierwsz", "drug", "trzec", "czwart", "piąt", "szóst", "siódm", "ósm")
_COUNTS = {
    "dwa": 2,
    "dwie": 2,
    "dwóch": 2,
    "trzy": 3,
    "trzech": 3,
    "cztery": 4,
    "czterech": 4,
    "pięć": 5,
    "pięciu": 5,
    "sześć": 6,
    "sześciu": 6,
    "siedem": 7,
    "siedmiu": 7,
    "osiem": 8,
    "ośmiu": 8,
}
_CARDINAL = rf"(?:[2-8]|{'|'.join(_COUNTS)})"
_DECLARE_COUNT = re.compile(
    rf"\b(?P<count>{_CARDINAL}) (?:wykonan\w+ )?(?:pomiar\w*|odczyt\w*|odcink\w*|ocen\w*|wynik\w*|obserwacj\w*)\b",
    re.I,
)
_MEDIAN = re.compile(r"\bmedian[ęay]\b", re.I)
_MEAN = re.compile(r"\bśredni[ąaeę]\b", re.I)
_MINUTES = re.compile(r"\b(?:w minutach|ile minut|na minuty)\b", re.I)
_TOTAL = re.compile(r"\b(?:z?sum\w+|łączn\w*|razem|całoś\w*)\b", re.I)
_PRECISION = re.compile(
    r"\bdo (jednego miejsca|dwóch miejsc|trzech miejsc|[123] miejsc)(?: po przecinku)?\b",
    re.I,
)
_PLACES = {"jednego miejsca": 1, "dwóch miejsc": 2, "trzech miejsc": 3}
_REMOVE = re.compile(
    rf"(?:skreśl|usuń|wykreśl)(?:\s+wynik)?\s+(?P<value>{_NUM})(?=$|[\s,])", re.I
)
_REPLACE = re.compile(
    rf"(?:z\s+(?P<old>{_NUM})(?:\s+(?P<old_unit>{_UNITS})\b)?\s+na\s+(?P<new>{_NUM})|"
    rf"(?P<replacement>{_NUM})(?:\s+(?P<new_unit>{_UNITS})\b)?(?:\s+zamiast\s+|,\s*nie\s+)(?P<before>{_NUM}))"
    rf"(?:\s+(?P<unit>{_UNITS})\b)?",
    re.I,
)
_POSITION_WORD = rf"(?:{'|'.join(_ORDINALS)})\w*"
_SET_POSITION = re.compile(
    rf"(?P<ordinal>{_POSITION_WORD}) "
    r"(?:odczyt|wpis|pomiar|próbk\w*|czas|odcinek) "
    rf"(?:koryguję do|poprawiam na|zmieniam na|(?:teraz |jednak )?wynosi) "
    rf"(?P<value>{_NUM}) (?P<unit>{_UNITS})",
    re.I,
)
_WRITE_INSTEAD = re.compile(
    rf"\bzamiast\s+(?P<old>{_NUM})(?:\s+(?P<old_unit>{_UNITS})\b)?[, ]+"
    rf"(?:wpisz|wstaw|przyjmij|zapisz|powinno być)\s+(?P<new>{_NUM})(?:\s+(?P<new_unit>{_UNITS})\b)?",
    re.I,
)
_REVISE = re.compile(
    r"\b(?:zmien\w*|zapis\w*|korek[tc]\w*|był[oa]?|jest|trwał\w*|odcinek)\b", re.I
)
_DIMENSIONS = {
    "s": ("time", Decimal(1)),
    "min": ("time", Decimal(60)),
    "ml": ("volume", Decimal(1)),
    "l": ("volume", Decimal(1000)),
    "g": ("mass", Decimal(1)),
    "kg": ("mass", Decimal(1000)),
}
_REMAINING = re.compile(
    r"\bile\b[^.!?]{0,36}(?:\bzost(?:anie|aje)\b(?: poza rezerwą)?|"
    r"\bdo wykorzystania poza rezerwą\b)",
    re.I,
)
_VOLUME = rf"(?P<value>{_NUM})\s*l\b"
_VOLUME_TOTAL = re.compile(rf"^(?:z|mamy|jest|dostępn\w+ jest)\s+{_VOLUME}", re.I)
_VOLUME_RESERVE = re.compile(
    rf"\b(?:(?:z czego )?{_VOLUME}\s+ma\s+osobn\w+\s+odbiorc\w+|"
    rf"rezerw\w+\s+{_VOLUME.replace('value', 'reserved')}\s+dla\s+(?:oddzieln\w+|osobn\w+)\s+odbiorc\w+)",
    re.I,
)
_HELD_RESERVE = re.compile(rf"(?:zostawiono|odłożono) {_VOLUME} na rezerwę", re.I)
_GROUP_PORTIONS = re.compile(
    rf"\b(?P<count>{_CARDINAL}) (?:zespoł\w*|grup\w*) (?:pobrał\w*|zużył\w*) po {_VOLUME}",
    re.I,
)
_TWO_GROUP_CHANGE = re.compile(
    rf"pierwsz[ya] (?:zespół|grupa) (?:zużył[oa]?|pobrał[oa]?) (?:jednak |teraz )?{_VOLUME}, "
    rf"drug[ia] (?:nadal |wciąż )(?P<unchanged>{_NUM})(?: l)?",
    re.I,
)
_VOLUME_PORTIONS = re.compile(
    rf"\bpo\s+{_VOLUME}\s+na\s+(?P<count>{_CARDINAL}) stanowisk\w*\b", re.I
)
_VOLUME_CHANGE = re.compile(
    rf"jedno stanowisko (?:dostało|otrzymało|wzięło|bierze)\s+{_VOLUME},\s*"
    rf"pozostałe (?P<count>{_CARDINAL}) (?:nadal )?po\s+"
    rf"{_VOLUME.replace('value', 'unchanged')}",
    re.I,
)


class _Operation(Enum):
    MEDIAN = auto()
    MEAN = auto()
    MINUTE_TOTAL = auto()


def _clauses(turn: str) -> list[str]:
    return [part.strip() for part in _CLAUSE.split(turn) if part.strip()]


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _show(value: Decimal) -> str:
    return _number(value).replace(".", ",")


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _unit(raw: str) -> str:
    unit = raw.casefold()
    if unit.startswith("sekund"):
        return "s"
    if unit.startswith("minut"):
        return "min"
    return unit


def _count(token: str) -> int:
    return int(token) if token.isdecimal() else _COUNTS[token.casefold()]


def _operation(query: str) -> _Operation | None:
    signals = (
        (_MEDIAN.search(query), _Operation.MEDIAN),
        (_MEAN.search(query), _Operation.MEAN),
        (_MINUTES.search(query) and _TOTAL.search(query), _Operation.MINUTE_TOTAL),
    )
    parsed = [operation for matched, operation in signals if matched]
    return parsed[0] if len(parsed) == 1 else None


def _precision(query: str) -> int | None:
    p = _PRECISION.search(query)
    if p is None:
        return None
    prefix = p[1].casefold()
    return int(prefix[0]) if prefix[0].isdecimal() else _PLACES[prefix]


@dataclass(frozen=True)
class _Series:
    operation: _Operation
    values: tuple[Decimal, ...]
    unit: str
    places: int | None
    uniform_unit: bool = True


_CONNECTOR = re.compile(r"\s*(?:,|;|,?\s+(?:i|oraz|potem|następnie)\s+)\s*", re.I)
_DURATION_CONTEXT = re.compile(
    r"\b(?:czas\w*|odcink\w*|etap\w*|trwa\w*|przebieg\w*|serii|odczyt\w*|pomiar\w*|długości)\b",
    re.I,
)
_TIME_TARGET = re.compile(
    r"\b(?:zsum\w*|sum\w*|łączn\w*|razem|wszystk\w*|całoś\w*)\b", re.I
)
_EXCLUDED_TIME = re.compile(
    r"\b(?:oprócz|poza|bez|zamiast|przerwa\w*|limit\w*|tylko|samych|minus|nie licząc)\b",
    re.I,
)


def _individual_durations(source: str, query: str) -> _Series | None:
    """Read a complete list of independently unit-tagged durations."""
    if not _DURATION_CONTEXT.search(source) or _EXCLUDED_TIME.search(
        source + " " + query
    ):
        return None
    rows = list(_MEASUREMENT.finditer(source))
    if not 2 <= len(rows) <= 8:
        return None
    if _NUMBER.search(_MEASUREMENT.sub("", source)):
        return None
    if any(_unit(m["unit"]) not in {"min", "s"} for m in rows):
        return None
    # Each boundary must denote a list operation, never an estimate or subtraction.
    if any(
        not _CONNECTOR.fullmatch(source[a.end() : b.start()])
        for a, b in zip(rows, rows[1:])
    ):
        return None
    if source[rows[-1].end() :].strip(" .,:;") or _MEASUREMENT.search(query):
        return None
    count = _DECLARE_COUNT.search(source[: rows[0].start()])
    if count and _count(count["count"]) != len(rows):
        return None
    units = {_unit(row["unit"]) for row in rows}
    unit = next(iter(units)) if len(units) == 1 else "s"
    scale = _DIMENSIONS[unit][1]
    values = tuple(
        _decimal(row["value"]) * _DIMENSIONS[_unit(row["unit"])][1] / scale
        for row in rows
    )
    if min(values) < 0:
        return None
    return _Series(_Operation.MINUTE_TOTAL, values, unit, None, len(units) == 1)


def _series_source(turn: str) -> _Series | None:
    *facts, query = _clauses(turn) or [""]
    operation = _operation(query)
    if (
        operation is None
        and _MINUTES.search(query)
        and facts
        and re.match(r"(?:dodaj|zsumuj|podlicz)\b", facts[0], re.I)
    ):
        operation = _Operation.MINUTE_TOTAL
    if (
        operation is None
        or not facts
        or not (_SOURCE.search(" ".join(facts)) or operation is _Operation.MINUTE_TOTAL)
        or _NUMBER.search(_PRECISION.sub("", query))
    ):
        return None
    source = " ".join(facts)
    if operation is _Operation.MINUTE_TOTAL:
        individual = _individual_durations(source, query)
        if individual is not None:
            return individual
    matches = list(_LIST.finditer(source))
    if len(matches) != 1:
        return None
    match = matches[0]
    prefix, suffix = source[: match.start()], source[match.end() :].strip()
    unit = _unit(match["unit"] or "")
    values = tuple(_decimal(m[0]) for m in _NUMBER.finditer(match["values"]))
    if len(values) < 2 or (
        suffix not in {"", "jednostek"}
        and not _PENDING.search(suffix)
        and not re.fullmatch(
            r"w (?:dwóch|trzech|czterech|pięciu|[2-8]) odcinkach", suffix, re.I
        )
    ):
        return None
    duration_count = re.fullmatch(r"w (\w+) odcinkach", suffix, re.I)
    if duration_count and _count(duration_count[1]) != len(values):
        return None
    declared = _DECLARE_COUNT.search(prefix)
    rest = _DECLARE_COUNT.sub("", prefix, count=1)
    requested = re.search(
        rf"\b(?:z|dla) (?:wszystkich )?(?P<count>{_CARDINAL}) "
        r"(?:obserwacj\w*|pomiar\w*|wynik\w*|odczyt\w*)",
        query,
        re.I,
    )
    if requested and _count(requested["count"]) != len(values):
        return None
    if _NUMBER.search(rest) or _NUMBER.search(suffix):
        return None
    if declared is not None and _count(declared["count"]) != len(values):
        return None
    if operation is _Operation.MEDIAN and unit:
        return None
    if operation is _Operation.MEAN and unit not in {"g", "kg", "ml", "l"}:
        return None
    if operation is _Operation.MINUTE_TOTAL and unit not in {"min", "s"}:
        return None
    if operation is not _Operation.MEDIAN and min(values) < 0:
        return None
    places = _precision(query)
    if "po przecinku" in query.casefold() and places is None:
        return None
    return _Series(operation, values, unit, places)


def _series_position(state: _Series, change: str, old: Decimal) -> int | None:
    words = re.findall(r"[^\W\d_]+", change.casefold())
    ordinals = {
        i for i, stem in enumerate(_ORDINALS) if any(x.startswith(stem) for x in words)
    }
    if not ordinals:
        return state.values.index(old) if state.values.count(old) == 1 else None
    if len(ordinals) != 1:
        return None
    position = next(iter(ordinals))
    return (
        position
        if position < len(state.values) and state.values[position] == old
        else None
    )


def _revised_values(state: _Series, change: str) -> tuple[Decimal, ...] | None:
    values = list(state.values)
    if deletion := _REMOVE.match(change):
        value = _decimal(deletion["value"])
        if (
            state.operation is not _Operation.MEDIAN
            or len(values) < 2
            or values.count(value) != 1
        ):
            return None
        if _NUMBER.search(change[deletion.end() :]):
            return None
        values.remove(value)
        return tuple(values)
    position_edit = _SET_POSITION.fullmatch(change)
    if position_edit and state.unit:
        ordinal = position_edit["ordinal"].casefold()
        position = next(
            i for i, stem in enumerate(_ORDINALS) if ordinal.startswith(stem)
        )
        dimension, scale = _DIMENSIONS[state.unit]
        new_dimension, new_scale = _DIMENSIONS[_unit(position_edit["unit"])]
        value = _decimal(position_edit["value"]) * new_scale / scale
        if position >= len(values) or dimension != new_dimension or value < 0:
            return None
        values[position] = value
        return tuple(values)
    instruction = _WRITE_INSTEAD.search(change)
    edit = instruction or _REPLACE.search(change)
    if edit is None or not (
        instruction
        or _REVISE.search(change[: edit.start()])
        or change[: edit.start()].rstrip().endswith(":")
    ):
        return None
    if _NUMBER.search(change[: edit.start()]) or _NUMBER.search(change[edit.end() :]):
        return None
    tail_unit = edit.groupdict().get("unit")
    if instruction and not (tail_unit or edit["old_unit"] or edit["new_unit"]):
        if not state.uniform_unit:
            return None
        tail_unit = state.unit
    old_unit = edit["old_unit"] or tail_unit or edit["new_unit"]
    new_unit = edit["new_unit"] or tail_unit or edit["old_unit"]
    if not state.unit or not old_unit or not new_unit:
        return None
    dimension, scale = _DIMENSIONS[state.unit]
    old_dimension, old_scale = _DIMENSIONS[_unit(old_unit)]
    new_dimension, new_scale = _DIMENSIONS[_unit(new_unit)]
    if dimension != old_dimension or dimension != new_dimension:
        return None
    old = _decimal(edit["old"] or edit["before"]) * old_scale / scale
    new = _decimal(edit["new"] or edit["replacement"]) * new_scale / scale
    position = _series_position(state, change[: edit.start()], old)
    if position is None or new < 0:
        return None
    values[position] = new
    return tuple(values)


def _series_update(state: _Series, turn: str) -> _Series | None:
    parts = _clauses(turn)
    if (
        len(parts) != 2
        or not (
            _operation(parts[-1]) is state.operation
            or state.operation is _Operation.MINUTE_TOTAL
            and _TIME_TARGET.search(parts[-1])
            and not _EXCLUDED_TIME.search(parts[-1])
            and not _MEASUREMENT.search(parts[-1])
        )
        or _NUMBER.search(_PRECISION.sub("", parts[-1]))
    ):
        return None
    change, query = parts
    values = _revised_values(state, change)
    if values is None:
        return None
    places = _precision(query)
    if "po przecinku" in query.casefold() and places is None:
        return None
    return replace(
        state, values=values, places=state.places if places is None else places
    )


def _series_plan(state: _Series) -> StudioCalculation:
    values = state.values
    if state.operation is _Operation.MEDIAN:
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return StudioCalculation(
                _number(ordered[mid]), None, lambda result: f"Mediana: {result}."
            )
        left, right = ordered[mid - 1 : mid + 1]
        return StudioCalculation(
            f"({_number(left)}+{_number(right)})/2",
            None,
            lambda result: f"Środkowe wartości: {_show(left)} i {_show(right)}. Mediana: {result}.",
        )
    expression = " + ".join(_number(value) for value in values)
    if state.operation is _Operation.MINUTE_TOTAL:
        if state.unit == "s":
            return StudioCalculation(
                f"({expression})/60",
                "min",
                lambda result: f"Suma: {_show(sum(values, Decimal(0)))} sekund, czyli {result}.",
            )
        return StudioCalculation(expression, "min", lambda result: f"Suma: {result}.")
    prefix = f"Średnia z {len(values)} pomiarów"
    terms = " + ".join(_show(value) for value in values)

    def render(result: str) -> str:
        if state.places is not None:
            value = _decimal(result.split()[0]).quantize(
                Decimal(1).scaleb(-state.places), rounding=ROUND_HALF_UP
            )
            result = f"{format(value, 'f').replace('.', ',')} {state.unit}"
        return f"{prefix}: {result} (({terms}) ÷ {len(values)})."

    return StudioCalculation(f"({expression})/{len(values)}", state.unit, render)


@dataclass(frozen=True)
class _Allocation:
    total: Decimal
    reserve: Decimal
    quantity: Decimal
    count: int


def _allocation_source(turn: str) -> _Allocation | None:
    total = _VOLUME_TOTAL.search(turn)
    reserve = _VOLUME_RESERVE.search(turn) or _HELD_RESERVE.search(turn)
    portions = _VOLUME_PORTIONS.search(turn) or _GROUP_PORTIONS.search(turn)
    *_, query = _clauses(turn) or [""]
    if not total or not reserve or not portions or not _REMAINING.search(query):
        return None
    if re.search(
        r"\b(?:dla (?:osobn\w+ |oddzieln\w+ )?odbiorc\w*|w rezerwie)\b", query, re.I
    ):
        return None
    count = _count(portions["count"])
    operands = _MEASUREMENT.findall(turn)
    if len(operands) != 3 or any(_unit(unit) != "l" for _, unit in operands):
        return None
    budget = _decimal(total["value"])
    protected = _decimal(reserve["value"] or reserve["reserved"])
    per_station = _decimal(portions["value"])
    if (
        min(budget, protected, per_station) < 0
        or protected + count * per_station > budget
    ):
        return None
    return _Allocation(budget, protected, per_station, count)


def _allocation_plan(turns: Sequence[str]) -> StudioCalculation | None:
    if any(_SPECULATIVE.search(turn) for turn in turns[-2:]):
        return None
    if not _REMAINING.search(turns[-1]):
        return None
    source = _allocation_source(turns[-1])
    source_text = turns[-1]
    if source is not None:
        used = f"{source.count}*{_number(source.quantity)}"
    elif len(turns) > 1 and (source := _allocation_source(turns[-2])) is not None:
        source_text = turns[-2]
        *facts, query = _clauses(turns[-1]) or [""]
        if len(facts) != 1 or not _REMAINING.fullmatch(query):
            return None
        change = _VOLUME_CHANGE.fullmatch(facts[0]) or _TWO_GROUP_CHANGE.fullmatch(
            facts[0]
        )
        if (
            change is None
            or _count(change.groupdict().get("count") or "1") != source.count - 1
            or _decimal(change["unchanged"]) != source.quantity
        ):
            return None
        amended = _decimal(change["value"])
        if (
            amended < 0
            or source.reserve + amended + (source.count - 1) * source.quantity
            > source.total
        ):
            return None
        used = f"{_number(amended)}+{source.count - 1}*{_number(source.quantity)}"
    else:
        return None
    consumption = (
        "pobranych porcji"
        if _GROUP_PORTIONS.search(source_text)
        else "rozlanych porcji"
    )
    calculation = f"{_number(source.total)}-{_number(source.reserve)}-({used})"
    return StudioCalculation(
        calculation,
        "l",
        lambda result: f"Po odjęciu rezerwy i {consumption} zostaje {result}.",
    )


def plan_numeric_series(turns: Sequence[str]) -> StudioCalculation | None:
    """Use the most recent measured series, applying only recognised bound edits."""
    state = None
    for turn in turns:
        if _SPECULATIVE.search(turn):
            state = None
            continue
        current = _series_source(turn)
        if current is not None:
            state = current
        elif state is not None:
            state = _series_update(state, turn)
    if state is not None:
        return _series_plan(state)
    return _allocation_plan(turns)


_SESSION_ROW = re.compile(
    r"po (?P<ordinal>pierwszej|drugiej)(?: sesji)?(?: (?:zliczono|zanotowano))? "
    r"(?P<passed>[0-9]{1,6}) poprawnych i (?P<pending>[0-9]{1,6}) do sprawdzenia",
    re.I,
)
_SESSION_MOVE = re.compile(
    rf"(?P<count>{_CARDINAL}) wpisy z (?P<from>poprawnych|do sprawdzenia) "
    r"po (?P<ordinal>pierwszej|drugiej) sesji (?:przenoszę|przenieś) do "
    r"(?:„(?P<quoted>do sprawdzenia|poprawnych)”|(?P<plain>do sprawdzenia|poprawnych))",
    re.I,
)
_STATION_ROW = re.compile(
    r"(?:na )?(?:stanowisku )?(?P<label>[a-z]) (?:wpisano )?"
    r"(?P<passed>[0-9]{1,6})(?: sztuk)? dobrych i (?P<pending>[0-9]{1,6}) do przeglądu",
    re.I,
)
_STATION_MOVE = re.compile(
    rf"na (?P<label>[a-z]) (?P<count>{_CARDINAL}|jedną|1) dobre (?:przenoszę|przenieś) do przeglądu",
    re.I,
)
_STATION_REPORT = re.compile(
    r"podaj (?:aktualne )?obie liczby na (?P<label>[a-z])", re.I
)
_STATION_TOTAL = re.compile(
    r"ile dobrych (?:łącznie|w obu stanowiskach(?: po zmianie)?)", re.I
)
_SESSION_TOTAL = re.compile(r"ile(?: teraz)? poprawnych (?:z|w) obu(?: sesjach)?", re.I)
_SESSION_REPORT = re.compile(r"podaj oba liczniki tej sesji", re.I)


@dataclass(frozen=True)
class _SessionCounts:
    passed: int
    pending: int

    def transfer(self, take_passed: bool, quantity: int) -> _SessionCounts | None:
        if quantity > (self.passed if take_passed else self.pending):
            return None
        delta = -quantity if take_passed else quantity
        return _SessionCounts(self.passed + delta, self.pending - delta)


def _session_rows(turn: str) -> dict[str, _SessionCounts] | None:
    parts = _clauses(turn)
    if len(parts) == 3 and _STATION_TOTAL.fullmatch(parts[-1]):
        rows = {}
        for phrase in parts[:-1]:
            item = _STATION_ROW.fullmatch(phrase)
            if item is None or item["label"].casefold() in rows:
                return None
            rows[item["label"].casefold()] = _SessionCounts(
                int(item["passed"]), int(item["pending"])
            )
        return rows
    if len(parts) != 2 or not _SESSION_TOTAL.fullmatch(parts[1]):
        return None
    source = parts[0].split(", ")
    if len(source) != 2:
        return None
    rows = {}
    for phrase in source:
        row = _SESSION_ROW.fullmatch(phrase)
        if row is None or row["ordinal"].casefold() in rows:
            return None
        rows[row["ordinal"].casefold()] = _SessionCounts(
            int(row["passed"]), int(row["pending"])
        )
    return rows


def plan_session_counts(turns: Sequence[str]) -> StudioCalculation | None:
    """Apply a sourced reclassification to one session, preserving its total."""
    rows = None
    report = None
    for turn in turns:
        report = None
        if current := _session_rows(turn):
            rows = current
            continue
        if rows is None:
            continue
        parts = _clauses(turn)
        if len(parts) == 1 and (
            _SESSION_TOTAL.fullmatch(parts[0]) or _STATION_TOTAL.fullmatch(parts[0])
        ):
            continue
        if len(parts) == 2 and (amendment := _STATION_MOVE.fullmatch(parts[0])):
            label = amendment["label"].casefold()
            asked = _STATION_REPORT.fullmatch(parts[1])
            if not asked or asked["label"].casefold() != label or label not in rows:
                return None
            count = amendment["count"].casefold()
            report = rows[label].transfer(
                True, 1 if count == "jedną" else _count(count)
            )
            if report is None:
                return None
            rows[label] = report
            continue
        move = _SESSION_MOVE.fullmatch(parts[0]) if len(parts) == 2 else None
        if move is None or not _SESSION_REPORT.fullmatch(parts[-1]):
            rows = None
            continue
        source = move["from"].casefold()
        destination = (move["quoted"] or move["plain"]).casefold()
        ordinal = move["ordinal"].casefold()
        if source == destination or move["ordinal"].casefold() not in rows:
            return None
        report = rows[ordinal].transfer(source == "poprawnych", _count(move["count"]))
        if report is None:
            return None
        rows[ordinal] = report
    if rows is None:
        return None
    if report is not None:
        pending_label = "do sprawdzenia" if "pierwszej" in rows else "do przeglądu"
        passed_label = "poprawnych" if "pierwszej" in rows else "dobrych"
        return StudioCalculation(
            f"{report.passed}+{report.pending}",
            None,
            lambda result: f"{report.passed} {passed_label} i {report.pending} {pending_label}. Łącznie {result}.",
        )
    before, after = (row.passed for row in rows.values())
    scope = "obu sesji" if "pierwszej" in rows else "obu stanowisk"
    label = "poprawnych" if "pierwszej" in rows else "dobrych"
    return StudioCalculation(
        f"{before}+{after}",
        None,
        lambda result: f"Z {scope}: {before} + {after} = {result} {label}.",
    )
