"""Average-speed measurements with an explicit distance, duration and output unit."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from venom_core.services.grounded_calculator import calculate
from venom_core.services.grounded_dialogue import (
    CalculationEvidence,
    Evidence,
    EvidenceError,
    PublishedAnswer,
)

MEASURED_SPEED_ID = "measured_average_speed"
_A = r"[0-9]{1,8}(?:[.,][0-9]{1,4})?"
_DISTANCE = rf"(?P<distance>{_A}) (?:m|metrów)"
_TIME = rf"(?P<duration>{_A}) (?:s|sekund|sekundy)"
_TARGET = r"(?P<unit>m/s|km/h)"
_INITIAL = re.compile(
    rf"(?:za pierwszym odczytem )?przejazd {_DISTANCE} trwał {_TIME}(?: razem z postojem)?\. "
    rf"oblicz(?: kalkulatorem)? średnią prędkość w {_TARGET}",
    re.IGNORECASE,
)
_UPDATE = re.compile(
    rf"(?:poprawka|korekta): cała droga to nadal {_DISTANCE}, czas łącznie {_TIME}\. "
    rf"użyj kalkulatora i podaj średnią prędkość w {_TARGET}",
    re.IGNORECASE,
)
_RECAP = re.compile(
    rf"(?P<question>napisz krótko, czy liczby {_A} i {_A} znaczą, że po poprawce jechałem szybciej)\. "
    r"odnieś się do jednostki i czasu"
    r"|porównaj obie (?:średnie )?prędkości (?:w|po sprowadzeniu do) m/s i uwzględnij zmianę czasu",
    re.IGNORECASE,
)


def _normal(message: str) -> str:
    return " ".join(message.split()).rstrip(".!?")


def _number(number: Decimal) -> str:
    return format(number.normalize(), "f")


def _decimal(literal: str) -> Decimal:
    return Decimal(literal.replace(",", "."))


def _shown(number: Decimal) -> str:
    return _number(number).replace(".", ",")


@dataclass(frozen=True)
class SpeedMeasurement:
    distance: Decimal
    duration: Decimal
    unit: str

    @property
    def base_expression(self) -> str:
        return f"{_number(self.distance)}/{_number(self.duration)}"

    @classmethod
    def from_match(cls, match: re.Match[str]) -> SpeedMeasurement | None:
        distance, duration = _decimal(match["distance"]), _decimal(match["duration"])
        return (
            cls(distance, duration, match["unit"].casefold()) if duration > 0 else None
        )


def bind_speed_measurement(users: tuple[str, ...]) -> SpeedMeasurement | None:
    if not users:
        return None
    current = _normal(users[-1])
    if first := _INITIAL.fullmatch(current):
        return SpeedMeasurement.from_match(first)
    update = _UPDATE.fullmatch(current)
    if update is None or len(users) < 2:
        return None
    original = _INITIAL.fullmatch(_normal(users[-2]))
    revised = SpeedMeasurement.from_match(update)
    if (
        original is None
        or revised is None
        or SpeedMeasurement.from_match(original) is None
    ):
        return None
    return revised if _decimal(original["distance"]) == revised.distance else None


def _literal(node: ast.AST) -> Fraction | None:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Fraction(str(node.value))
    return None


def _scalar(node: ast.AST) -> Fraction | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        numerator, denominator = _literal(node.left), _literal(node.right)
        if numerator is not None and denominator:
            return numerator / denominator
    return _literal(node)


def _scaled(node: ast.AST, scale: Fraction) -> bool:
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mult):
        return False
    return any(
        isinstance(base, ast.BinOp) and _scalar(factor) == scale
        for base, factor in ((node.left, node.right), (node.right, node.left))
    )


def _outer_scale(node: ast.AST, scale: Fraction) -> bool:
    if _scaled(node, scale):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        if divisor := _literal(node.right):
            return _scaled(node.left, scale * divisor)
    return False


def _requested_multiplier(request: str, scale: Fraction) -> bool:
    if re.match(r"\s*(?:zwiększ|pomnóż)\b", request, re.IGNORECASE) is None:
        return False
    if re.search(r"\b(?:nie|bez|zamiast|albo|lub)\b", request, re.IGNORECASE):
        return False
    factors = [
        Fraction(match[1].replace(",", "."))
        for match in re.finditer(
            r"(?<![\w.,])((?a:\d){1,8}(?:[.,](?a:\d){1,6})?)\s+raz(?:a|y)\b",
            request,
            re.IGNORECASE,
        )
    ]
    return len(factors) == 1 and factors[0] == scale


def has_repeated_speed_scale(
    expression: str, origin: str, target: str, *, request: str = ""
) -> bool:
    """Reject an outer conversion of an arithmetic result before scaling again."""
    scale = {("m/s", "km/h"): Fraction(18, 5), ("km/h", "m/s"): Fraction(5, 18)}.get(
        (origin, target)
    )
    if scale is None:
        return False
    try:
        node = ast.parse(expression.strip(), mode="eval").body
    except SyntaxError:
        return False
    if not _outer_scale(node, scale):
        return False
    if _requested_multiplier(request, scale):
        return sum(_outer_scale(part, scale) for part in ast.walk(node)) > 1
    return True


@dataclass(frozen=True)
class SpeedMeasurementReceipt:
    users: tuple[str, ...]
    state: SpeedMeasurement
    calculation: CalculationEvidence

    @classmethod
    def from_evidence(
        cls, users: tuple[str, ...], state: SpeedMeasurement, evidence: Evidence
    ) -> SpeedMeasurementReceipt:
        expression = state.base_expression
        if state.unit == "km/h":
            expression = f"({expression})*18/5"
        expected = CalculationEvidence(
            MEASURED_SPEED_ID, expression, calculate(expression), state.unit
        )
        if evidence.calculations != (expected,):
            raise EvidenceError("pilot_speed_evidence_mismatch")
        return cls(users, state, expected)


@dataclass(frozen=True)
class PilotSpeedMeasurementAnswer(PublishedAnswer):
    speed_measurement_receipt: SpeedMeasurementReceipt


def speed_measurement_recap(
    message: str, users: tuple[str, ...], receipts: tuple[SpeedMeasurementReceipt, ...]
) -> str | None:
    if not receipts or (request := _RECAP.fullmatch(_normal(message))) is None:
        return None
    by_history = {item.users: item for item in receipts}
    before, after = by_history.get(users[:-1]), by_history.get(users)
    if before is None or after is None or before.state.distance != after.state.distance:
        return "Do porównania potrzebuję potwierdzonych prędkości sprzed korekty i po niej."
    old = Decimal(calculate(before.state.base_expression))
    new = Decimal(calculate(after.state.base_expression))
    certainty = ""
    if request["question"]:
        certainty = "Tak. " if new > old else "Nie. "
    correction = (
        f"({_shown(_decimal(after.calculation.value))} km/h)"
        if after.calculation.unit == "km/h"
        else ""
    )
    speeds = (
        f"Przed korektą średnia wynosiła {_shown(old)} m/s, a po niej {_shown(new)} m/s"
    )
    times = (
        f"Dystans pozostał ten sam, a zmierzony czas to wcześniej {_shown(before.state.duration)} s "
        f"i po korekcie {_shown(after.state.duration)} s."
    )
    return f"{certainty}{speeds}{' ' + correction if correction else ''}. {times}"
