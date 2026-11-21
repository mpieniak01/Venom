"""Recognize a bounded calculator command in Direct chat."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_PREFIX = re.compile(
    r"(?:oblicz|policz|użyj kalkulatora)(?:[ \t]*:[ \t]*|[ \t]+|(?=[.!]?$))",
    re.IGNORECASE,
)
_UNIT_CLAUSE = re.compile(
    r"\s*(?:[.;]\s*jednostka\s*:\s*|\s+i podaj wynik w\s+)", re.IGNORECASE
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
_INLINE_UNIT = re.compile(r"(.+?)[ \t]+([A-Za-złŁ²³]+\.?)$")
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
    parts = _UNIT_CLAUSE.split(body, maxsplit=1)
    expression = parts[0].strip()
    unit = ""
    if len(parts) == 2:
        unit = parts[1].strip().removesuffix(".")
    elif inline := _INLINE_UNIT.fullmatch(expression):
        expression, unit = inline[1], inline[2].removesuffix(".")
    if unit and unit.casefold() not in _UNITS:
        return None
    expression = expression.strip().removesuffix(".").rstrip()
    if expression and _ARITHMETIC.fullmatch(expression) is None:
        return None
    return CalculatorRequest(
        expression.translate(_OPERATORS), _UNITS.get(unit.casefold())
    )


def plan_calculator(
    content: str, history: Sequence[dict[str, str]]
) -> CalculatorRequest | None:
    """Repeat only an immediately preceding explicit calculation."""
    if _REPEAT.fullmatch(content.strip()) is None:
        return _command(content)
    if len(history) < 2 or [row["role"] for row in history[-2:]] != [
        "user",
        "assistant",
    ]:
        return None
    previous = _command(history[-2]["content"])
    if previous is None or not previous.expression:
        return None
    return CalculatorRequest(previous.expression, previous.unit, repeat=True)
