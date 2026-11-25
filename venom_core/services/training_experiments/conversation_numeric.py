"""Check bounded numeric claims and fee coverage against a frozen rubric."""

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
    **dict.fromkeys(("metr", "metry", "metrów"), ("length", 0)),
    **dict.fromkeys(("kilometr", "kilometry", "kilometrów"), ("length", 3)),
    **dict.fromkeys(("centymetr", "centymetry", "centymetrów"), ("length", -2)),
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
    rf"(?:(?P<label>{'|'.join(_ROLES)}):?[ \t]+)?"
    rf"(?P<value>{_NUMBER})[ \t]+(?P<unit>{'|'.join(_UNITS)})\.?",
    re.IGNORECASE,
)

_FEE_BINDING_ONLY = re.compile(
    rf"(?:obowiązuje (?:nadal )?(?:opłata )?|"
    rf"obowiązująca opłata (?:to|wynosi) |aktualna opłata (?:to|wynosi) )"
    rf"(?P<value>{_NUMBER})[ \t]*(?:zł(?:otych)?|pln)"
    r"(?: (?:za komplet(?: materiałów)?|za osobę|na osobę|za grupę))?\.?",
    re.IGNORECASE,
)
_AMOUNT = re.compile(_NUMBER)


def _content_criterion(case: dict, criterion: object) -> bool:
    return isinstance(criterion, str) and any(
        item["id"] == criterion and item["kind"] == "content"
        for item in case["criteria"]
    )


def numeric_expectation(case: dict) -> dict | None:
    """Resolve the optional operator-authored calculation from the bound case."""
    if "numeric_claim" not in case:
        return None
    rule = case["numeric_claim"]
    required = {"criterion", "expression", "unit", "role"}
    if (
        not isinstance(rule, dict)
        or not required <= rule.keys() <= required | {"allow_bare"}
        or type(rule.get("allow_bare", False)) is not bool
    ):
        raise ValueError("conversation_review_numeric_rule_invalid")
    if (
        not _content_criterion(case, rule["criterion"])
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
    if match is None:
        return None
    label = match["label"]
    if label is None:
        if not expected.get("allow_bare", False):
            return None
    elif _ROLES[label.lower()] != expected["role"]:
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


def fee_expectation(case: dict) -> dict | None:
    """Read explicitly required binding and proposed PLN amounts from the dataset."""
    if "fee_state" not in case:
        return None
    rule = case["fee_state"]
    if not isinstance(rule, dict) or rule.keys() != {
        "criterion",
        "binding",
        "proposed",
    }:
        raise ValueError("conversation_review_fee_rule_invalid")
    if not _content_criterion(case, rule["criterion"]) or any(
        not isinstance(rule[field], str) or not _AMOUNT.fullmatch(rule[field])
        for field in ("binding", "proposed")
    ):
        raise ValueError("conversation_review_fee_rule_invalid")
    binding, proposed = (
        _normalize(rule[field], "pln")[1] for field in ("binding", "proposed")
    )
    if binding < 0 or proposed < 0 or binding == proposed:
        raise ValueError("conversation_review_fee_rule_invalid")
    return rule


def fee_omission(answer: dict, expected: dict | None) -> dict | None:
    """Identify complete replies that give only the binding fee on a two-fact rubric."""
    if expected is None or answer.get("finish") == "length":
        return None
    text = answer["text"].strip()
    match = _FEE_BINDING_ONLY.fullmatch(text) if len(text) <= 96 else None
    if match is None or _normalize(match["value"], "pln") != _normalize(
        expected["binding"], "pln"
    ):
        return None
    return {
        "criterion": expected["criterion"],
        "present_binding_pln": expected["binding"],
        "missing_proposed_pln": expected["proposed"],
        "quote": match[0],
    }
