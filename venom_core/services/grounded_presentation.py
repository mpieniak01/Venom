"""Explicit decimal presentation; exact calculator evidence is never rounded."""

from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, localcontext

ROUNDING_MODE = "ROUND_HALF_UP"
_PLACES = {
    "zero": 0,
    "jednego": 1,
    "dwoch": 2,
    "trzech": 3,
    "czterech": 4,
    "pieciu": 5,
    "szesciu": 6,
}
_PRECISION = re.compile(
    r"\bdo\s+([0-9]+|zero|jednego|dwoch|trzech|czterech|pieciu|szesciu)"
    r"\s+miejsc(?:a)?\s+po\s+przecinku\b"
)
_NO_ROUNDING = re.compile(r"\b(?:bez zaokraglania|nie zaokraglaj)\b")


def requested_precision(message: str) -> int | None:
    """Only an explicit current-user instruction can authorize rounding."""
    plain = "".join(
        c
        for c in unicodedata.normalize("NFKD", message.casefold())
        if not unicodedata.combining(c)
    )
    values = {
        _PLACES.get(m[1], int(m[1]) if m[1].isdigit() else -1)
        for m in _PRECISION.finditer(plain)
    }
    if not values:
        return None
    if len(values) != 1 or _NO_ROUNDING.search(plain):
        raise ValueError("answer_precision_ambiguous")
    places = values.pop()
    if not 0 <= places <= 6:
        raise ValueError("answer_precision_unsupported")
    return places


def rounded_value(value: str, places: int) -> str:
    """Round once, at the display boundary, using decimal HALF_UP."""
    if type(places) is not int or not 0 <= places <= 6 or len(value) > 200:
        raise ValueError("answer_precision_unsupported")
    number = Decimal(value)
    if not number.is_finite() or abs(number.adjusted()) > 200:
        raise ValueError("answer_precision_unsupported")
    with localcontext() as ctx:
        ctx.prec = max(
            28, len(number.as_tuple().digits) + abs(number.adjusted()) + places + 2
        )
        return format(
            number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP), "f"
        )


def normalize_claim(value: str, unit: str) -> str:
    """Normalize a lone decimal and an optional redundant, matching unit."""
    separation = r"\s*" if unit == "%" else r"\s+"
    suffix = rf"(?:{separation}{re.escape(unit)})?" if unit else ""
    match = re.fullmatch(rf"\s*([+−-]?[0-9]+(?:[.,][0-9]+)?){suffix}\s*", value)
    return match[1].replace(",", ".").replace("−", "-") if match else value
