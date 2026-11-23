"""Recognize a bounded calculator command in Direct chat."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from venom_core.services.chat_policy.direct_distance import (
    DistanceCalculation,
    DistanceClarification,
    plan_distance,
)

_PREFIX = re.compile(
    r"(?:oblicz|policz|użyj kalkulatora)(?:[ \t]*:[ \t]*|[ \t]+|(?=[.!]?$))",
    re.IGNORECASE,
)
_UNIT_CLAUSE = re.compile(
    r"[.;][ \t]*jednostka[ \t]*:[ \t]*|"
    r"[ \t]+i[ \t]+podaj[ \t]+wynik[ \t]+w[ \t]+",
    re.IGNORECASE,
)
_UNITS = {
    "zł": "zł",
    "pln": "PLN",
    "l": "l",
    "litry": "l",
    "litrach": "l",
    "ml": "ml",
    "kg": "kg",
    "g": "g",
    "km": "km",
    "m": "m",
    "cm": "cm",
    "m²": "m²",
    "m³": "m³",
    "s": "s",
    "min": "min",
    "h": "h",
    "kwh": "kWh",
    "szt": "szt.",
    "sztukach": "szt.",
    "puszkach": "puszki",
    "puszki": "puszki",
}
_ARITHMETIC = re.compile(r"[0-9.,()+*/ \t×÷−-]+")
_NUMERIC_START = re.compile(r"[0-9.,(+−-]")
_UNIT_SUFFIX = re.compile(r"[A-Za-złŁ²³]+\.?\Z")
_REPEAT = re.compile(
    r"powtórz(?: tylko)? (?:wynik|ostatni wynik)(?: obliczenia)?[.!]?", re.IGNORECASE
)
_OPERATORS = str.maketrans({",": ".", "×": "*", "÷": "/", "−": "-"})

MAX_COMMAND_CHARS = 256


@dataclass(frozen=True)
class CalculatorRequest:
    expression: str
    unit: str | None = None
    repeat: bool = False


def _command(content: str) -> CalculatorRequest | None:
    text = content.strip()
    if len(text) > MAX_COMMAND_CHARS or "\n" in text or "\r" in text:
        return None
    prefix = _PREFIX.match(text)
    if prefix is None:
        return None
    body = text[prefix.end() :].strip().removesuffix("!").strip()
    if body in {"", "."}:
        return CalculatorRequest("")
    if _NUMERIC_START.match(body) is None:
        return None
    unit_clause = _UNIT_CLAUSE.search(body)
    expression = body[: unit_clause.start()].strip() if unit_clause else body.strip()
    unit = ""
    if unit_clause is not None:
        unit = body[unit_clause.end() :].strip().removesuffix(".")
    else:
        expression, unit = _split_inline_unit(expression)
    if unit and unit.casefold() not in _UNITS:
        return None
    expression = expression.strip().removesuffix(".").rstrip()
    if expression and _ARITHMETIC.fullmatch(expression) is None:
        return None
    return CalculatorRequest(
        expression.translate(_OPERATORS), _UNITS.get(unit.casefold())
    )


def _split_inline_unit(expression: str) -> tuple[str, str]:
    parts = expression.rsplit(maxsplit=1)
    if len(parts) != 2 or _UNIT_SUFFIX.fullmatch(parts[1]) is None:
        return expression, ""
    return parts[0], parts[1].removesuffix(".")


def plan_calculator(
    content: str, history: Sequence[dict[str, str]]
) -> CalculatorRequest | DistanceCalculation | DistanceClarification | None:
    """Plan an explicit command or a supported calculation from the conversation."""
    if _REPEAT.fullmatch(content.strip()) is None:
        return _command(content) or plan_distance(content, history)
    if len(history) < 2 or [row["role"] for row in history[-2:]] != [
        "user",
        "assistant",
    ]:
        return None
    previous = _command(history[-2]["content"])
    if previous is None or not previous.expression:
        return None
    return CalculatorRequest(previous.expression, previous.unit, repeat=True)
