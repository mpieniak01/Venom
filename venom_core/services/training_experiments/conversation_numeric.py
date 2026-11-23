"""Prove contradictions in single quantity claims against a frozen rubric."""

import re
from decimal import Decimal

from venom_core.services.grounded_calculator import calculate

_UNITS = {
    "arkusz": ("sheet", 0),
    "arkusze": ("sheet", 0),
    "arkuszy": ("sheet", 0),
    "km": ("length", 3),
    "m": ("length", 0),
    "cm": ("length", -2),
    "zł": ("money", 0),
    "pln": ("money", 0),
}
_ROLES = {
    "zostało": "remaining",
    "pozostało": "remaining",
    "razem": "total",
    "łącznie": "total",
    "brakuje": "gap",
    "wynik": "result",
}
_NUMBER = (
    r"[+-]?(?:[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3}){1,2}|[0-9]{1,9})(?:[.,][0-9]{1,6})?"
)
_CLAIM = re.compile(
    rf"(?P<label>{'|'.join(_ROLES)}):?[ \t]+"
    rf"(?P<value>{_NUMBER})[ \t]+(?P<unit>{'|'.join(_UNITS)})\.?",
    re.IGNORECASE,
)


def numeric_expectation(case: dict) -> dict | None:
    """Resolve the optional operator-authored calculation from the bound case."""
    if "numeric_claim" not in case:
        return None
    rule = case["numeric_claim"]
    if not isinstance(rule, dict) or rule.keys() != {
        "criterion",
        "expression",
        "unit",
        "role",
    }:
        raise ValueError("conversation_review_numeric_rule_invalid")
    if (
        not isinstance(rule["criterion"], str)
        or rule["criterion"]
        not in {item["id"] for item in case["criteria"] if item["kind"] == "content"}
        or not isinstance(rule["expression"], str)
        or not isinstance(rule["unit"], str)
        or rule["unit"] not in _UNITS
        or not isinstance(rule["role"], str)
        or rule["role"] not in _ROLES.values()
    ):
        raise ValueError("conversation_review_numeric_rule_invalid")
    return {**rule, "value": calculate(rule["expression"])}


def _normalize(value: str, unit: str) -> tuple[str, Decimal]:
    kind, scale = _UNITS[unit]
    number = Decimal("".join(value.split()).replace(",", "."))
    return kind, number.scaleb(scale)


def numeric_contradiction(answer: dict, expected: dict | None) -> dict | None:
    """Return evidence for a wrong explicit claim. Ambiguous text needs review."""
    if expected is None or answer.get("finish") == "length":
        return None
    text = answer["text"].strip()
    match = _CLAIM.fullmatch(text) if len(text) <= 96 else None
    if match is None or _ROLES[match["label"].lower()] != expected["role"]:
        return None
    unit = match["unit"].lower()
    if _normalize(match["value"], unit) == _normalize(
        expected["value"], expected["unit"]
    ):
        return None
    return {
        "criterion": expected["criterion"],
        "expression": expected["expression"],
        "expected_value": expected["value"],
        "expected_unit": expected["unit"],
        "quote": match[0],
    }
