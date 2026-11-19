"""Bind count judgments to a literal Markdown table and an explicit user assignment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict

from .semantic_judge_v5 import MAX_EVIDENCE_TEXT_CHARS, Relation, observed_from_answer

_NAME = r"[^\W\d_]{1,40}"
_COUNT = r"[0-9]{1,9}"
_UNITS = {
    "paczka": "paczki",
    "paczki": "paczki",
    "paczek": "paczki",
    "przesyłka": "przesyłki",
    "przesyłki": "przesyłki",
    "przesyłek": "przesyłki",
    "sztuka": "sztuki",
    "sztuki": "sztuki",
    "sztuk": "sztuki",
    "pudełko": "pudełka",
    "pudełka": "pudełka",
    "pudełek": "pudełka",
    "karton": "kartony",
    "kartony": "kartony",
    "kartonów": "kartony",
    "koperta": "koperty",
    "koperty": "koperty",
    "kopert": "koperty",
}
_UNIT = rf"(?:{'|'.join(_UNITS)})"
_QUANTITY = rf"(?P<value>{_COUNT})\s+(?P<unit>{_UNIT})"
_VERB = r"(?:odbiera|ma odebrać|dostaje|ma otrzymać|liczy)"
_CRITERION = re.compile(
    rf"(?P<entity>{_NAME})(?:\s+{_VERB}\s+|:\s*){_QUANTITY}\.?",
    re.IGNORECASE,
)
_SORTING_PREFIX = "Dla sortowania: "
_PICKUP_DAY = re.compile(
    r"odbiór partii w (?:poniedziałek|wtorek|środę|czwartek|piątek|sobotę|niedzielę)",
    re.IGNORECASE,
)
_FIRST_ASSIGNMENT = re.compile(
    r"(?:(?:W (?:poniedziałek|wtorek|środę|czwartek|piątek|sobotę|niedzielę)|We wtorek)\s+)?"
    rf"(?P<entity>{_NAME})(?:\s+{_VERB}\s+|:\s*){_QUANTITY}",
    re.IGNORECASE,
)
_KNOWN_CONTINUATION = re.compile(
    rf"(?:a |i )?(?P<entity>{_NAME})(?:\s+{_VERB}\s+|:\s*|\s+){_QUANTITY}",
    re.IGNORECASE,
)
_IMPLICIT_SORT_COUNT = re.compile(rf"(?P<entity>{_NAME})\s+(?P<value>{_COUNT})")
_HEADER = re.compile(rf"(?P<entity>{_NAME})\s+\[(?P<unit>{_UNIT})\]", re.IGNORECASE)
_ALIGNMENT = re.compile(r":?-{3,}:?")
_VALUE = re.compile(_COUNT)
_MAX_COLUMNS = 10


class Source(TypedDict):
    message_index: int
    quote: str
    value: str
    unit: str


class Comparison(TypedDict):
    criterion: str
    observed: str
    effective_observed: str
    raw_relation: Relation
    effective_relation: Relation
    header: str
    cell: str
    column: int
    source: Source


@dataclass(frozen=True)
class _Table:
    quote: str
    headers: tuple[str, ...]
    alignment: tuple[str, ...]
    values: tuple[str, ...]


def _cells(line: str, *, projected: bool = False) -> tuple[str, ...]:
    line = line.strip()
    if "\\" in line or (
        not projected and not (line.startswith("|") and line.endswith("|"))
    ):
        return ()
    interior = line.removeprefix("|").removesuffix("|")
    values = tuple(cell.strip() for cell in interior.split("|"))
    return values if all(values) else ()


def _parse_table(candidate: str) -> _Table | None:
    quote = candidate.strip()
    if len(quote) > MAX_EVIDENCE_TEXT_CHARS:
        return None
    lines = quote.splitlines()
    if len(lines) != 3:
        return None
    headers, alignment, values = map(_cells, lines)
    if not (
        2 <= len(headers) <= _MAX_COLUMNS
        and len(headers) == len(alignment) == len(values)
        and len(set(map(str.casefold, headers))) == len(headers)
        and all(_ALIGNMENT.fullmatch(cell) is not None for cell in alignment)
    ):
        return None
    return _Table(quote, headers, alignment, values)


def _entity_columns(table: _Table, entity: str) -> list[tuple[int, str]]:
    columns = []
    for index, cell in enumerate(table.headers):
        header = _HEADER.fullmatch(cell)
        if header is not None and header["entity"].casefold() == entity:
            columns.append((index, _UNITS[header["unit"].casefold()]))
        elif cell.casefold() == entity:
            columns.append((index, ""))
    return columns


def _assignment_clauses(sentence: str) -> list[tuple[str, str, str, str]]:
    clauses = [
        item.strip()
        for item in re.split(r",\s+|\s+(?=[ai]\s+)", sentence.rstrip(".!?"))
    ]
    scoped_sorting = bool(clauses) and clauses[0].startswith(_SORTING_PREFIX)
    if scoped_sorting:
        clauses[0] = clauses[0].removeprefix(_SORTING_PREFIX)
        if len(clauses) > 1 and _PICKUP_DAY.fullmatch(clauses[-1]):
            clauses.pop()
    entries: list[tuple[str, str, str, str]] = []
    for index, clause in enumerate(clauses):
        pattern = _FIRST_ASSIGNMENT if index == 0 else _KNOWN_CONTINUATION
        match = pattern.fullmatch(clause)
        if match is not None:
            unit = _UNITS[match["unit"].casefold()]
        elif (
            scoped_sorting
            and entries
            and (match := _IMPLICIT_SORT_COUNT.fullmatch(clause))
        ):
            units = {entry[3] for entry in entries}
            if len(units) != 1:
                return []
            unit = units.pop()
        else:
            return []
        entries.append((clause, match["entity"], match["value"], unit))
    return entries


def _user_message(material: dict) -> tuple[int, str] | None:
    for index, message in reversed(list(enumerate(material["messages"]))):
        if message["role"] == "user":
            return index, message["content"]
    return None


def _source(material: dict, entity: str) -> Source | None:
    latest = _user_message(material)
    if latest is None:
        return None
    index, text = latest
    matches: list[Source] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        entries = _assignment_clauses(sentence)
        if not entries and entity in {
            token.casefold() for token in re.findall(_NAME, sentence)
        }:
            return None
        for clause, entity_name, value, unit in entries:
            if entity_name.casefold() == entity:
                matches.append(
                    {
                        "message_index": index,
                        "quote": clause,
                        "value": value,
                        "unit": unit,
                    }
                )
    return matches[0] if len(matches) == 1 else None


def _table_projection(observed: str, table: _Table, column: int) -> bool:
    """Check the only tolerated broken quote, an ordered projection of the same table."""
    lines = observed.strip().splitlines()
    if len(lines) != 3:
        return False
    # A quote can start or end inside a border; every quoted cell still has to match.
    headers, alignment, values = (_cells(line, projected=True) for line in lines)
    if not headers or not values or not all(cell in table.headers for cell in headers):
        return False
    selected = tuple(table.headers.index(cell) for cell in headers)
    if (
        selected != tuple(sorted(set(selected)))
        or column not in selected[: len(values)]
    ):
        return False
    projection = tuple(table.values[index] for index in selected)
    return values == projection[: len(values)] and alignment in (
        table.alignment,
        tuple(table.alignment[index] for index in selected),
    )


def compare(
    material: dict,
    candidate: str,
    criterion_id: str,
    observed: str,
    raw_relation: Relation,
) -> Comparison | None:
    description = next(
        (c["description"] for c in material["criteria"] if c["id"] == criterion_id), ""
    )
    criterion = _CRITERION.fullmatch(description)
    if criterion is None:
        return None
    table = _parse_table(candidate)
    if table is None:
        return None
    entity = criterion["entity"].casefold()
    unit = _UNITS[criterion["unit"].casefold()]
    columns = _entity_columns(table, entity)
    if len(columns) != 1 or columns[0][1] != unit:
        return None
    column = columns[0][0]
    cell = table.values[column]
    if _VALUE.fullmatch(cell) is None:
        return None
    source = _source(material, entity)
    if (
        source is None
        or source["unit"] != unit
        or int(source["value"]) != int(criterion["value"])
    ):
        return None
    if not (
        observed_from_answer(observed, raw_relation, candidate)
        or _table_projection(observed, table, column)
    ):
        return None
    effective: Relation = (
        "supported" if int(cell) == int(source["value"]) else "contradicted"
    )
    return {
        "criterion": criterion_id,
        "observed": observed,
        "effective_observed": table.quote,
        "raw_relation": raw_relation,
        "effective_relation": effective,
        "header": table.headers[column],
        "cell": cell,
        "column": column,
        "source": source,
    }
