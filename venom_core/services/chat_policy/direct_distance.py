"""Plan bounded two-segment distance calculations from user-provided facts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from venom_core.services.chat_policy.qualified_chat_quote import (
    is_text_transformation,
    without_quotes,
)
from venom_core.services.grounded_calculator import result_with_unit

_NUMBER = r"[0-9]{1,12}(?:[,.][0-9]{1,6})?"
_UNIT = r"km|cm|m"
_QUANTITY = rf"(?P<amount>{_NUMBER})\s*(?P<unit>{_UNIT})\b"
_EXPLICIT_NUMBER = re.compile(r"\d")
_CORRECTION = re.compile(r"^(?:korekta|poprawka|doprecyzujmy|poprawiam)\b", re.I)
_DISTANCE = re.compile(rf"(?<![\w.,+\-−]){_QUANTITY}", re.I)
_SUBJECT = r"(?:tras[ayę]|odcinek|odcinki|odcinka|fragment|fragmenty)"
_SEGMENT = re.compile(
    rf"(?:^|[,:;.!?]\s*(?:a\s+)?|\bi\s+|\boraz\s+)"
    rf"(?:{_SUBJECT}\s+)?(?P<name>[a-z])\s*"
    r"(?:(?:ma|mierzy|wynosi)(?: teraz| długość)?\s+|to(?: teraz)?\s+|"
    r"(?:zmierzono(?: faktycznie)?|popraw|zmieniono)\s*(?:na)?\s+|"
    r"jest równ[ay]\s+|[:=–-]\s*)?"
    rf"(?<!\w){_QUANTITY}",
    re.I,
)
_TARGET = re.compile(rf"\bdo\s+(?:celu\s+)?{_QUANTITY}", re.I)
_SCOPE = re.compile(rf"\b{_SUBJECT}\s+[a-z]\b", re.I)
_TOTAL = re.compile(
    r"\b(?:ile (?:to )?(?:razem|łącznie)|jaka (?:jest )?(?:suma|łączna długość)|"
    r"(?:oblicz|policz|podaj) (?:sumę|łączną długość))\b",
    re.I,
)
_GAP = re.compile(
    r"\b(?:ile (?:jeszcze )?brakuje|(?:przelicz|oblicz|policz|podaj) (?:brak|różnicę))\b",
    re.I,
)
_SUMMARY = re.compile(
    r"\b(?:z (?:wynikiem|sumą|łączną długością) i brakiem|"
    r"(?:podsumuj|podaj) (?:wynik|sumę|łączną długość) (?:oraz|i) (?:brak|ile brakuje))\b",
    re.I,
)
_AMBIGUITY = re.compile(
    r"\b(?:albo|lub|około|chyba|co najmniej|co najwyżej|nie wiadomo|nie znam)\b",
    re.I,
)
_NON_CALCULATION = re.compile(
    r"\bnie\s+(?:obliczaj|licz|przeliczaj|podawaj wyniku)\b|"
    r"\b(?:trasie|odcinkowi|fragmentowi)\s+[a-z]\b",
    re.I,
)
_CLARIFICATION = (
    "Podaj dokładne długości obu odcinków"
    " oraz długość docelową, jeśli mam obliczyć, ile brakuje."
)

Mode = Literal["sum", "gap", "recalculation", "summary"]
_UNIT_SCALE = {"cm": -2, "m": 0, "km": 3}


@dataclass(frozen=True)
class Distance:
    metres: str
    unit: str

    @classmethod
    def from_match(cls, match: re.Match[str]) -> Distance:
        unit = match["unit"].lower()
        amount = Decimal(match["amount"].replace(",", ".")).scaleb(_UNIT_SCALE[unit])
        return cls(format(amount, "f"), unit)


@dataclass(frozen=True)
class DistanceCalculation:
    segments: tuple[Distance, Distance]
    mode: Mode
    target: Distance | None = None
    repeat: bool = False

    @property
    def sum_expression(self) -> str:
        return " + ".join(segment.metres for segment in self.segments)


@dataclass(frozen=True)
class DistanceClarification:
    text: str = _CLARIFICATION


@dataclass(frozen=True)
class DistanceTurn:
    segments: dict[str, Distance]
    target: Distance | None
    mode: Mode | None
    scoped: bool
    ambiguous: bool
    correction: bool


def _calculation_mode(visible: str, has_segments: bool) -> Mode | None:
    total = _TOTAL.search(visible)
    gap = _GAP.search(visible)
    if _SUMMARY.search(visible) or (total and gap):
        return "summary"
    if gap:
        return "recalculation" if has_segments else "gap"
    return "sum" if total else None


def _read_turn(content: str) -> DistanceTurn | None:
    if len(content) > 512 or is_text_transformation(content):
        return None
    visible = without_quotes(content).strip()
    if _NON_CALCULATION.search(visible):
        return None
    segments = list(_SEGMENT.finditer(visible))
    targets = list(_TARGET.finditer(visible))
    values = {match["name"].lower(): Distance.from_match(match) for match in segments}
    mode = _calculation_mode(visible, bool(segments))
    if not (mode or segments or targets):
        return None
    ambiguous = (
        len(segments) != len(values)
        or len(segments) > 2
        or len(targets) > 1
        or len(list(_DISTANCE.finditer(visible))) != len(segments) + len(targets)
        or bool(_AMBIGUITY.search(visible))
    )
    if not (segments or targets or ambiguous) and _EXPLICIT_NUMBER.search(visible):
        return None
    target = Distance.from_match(targets[0]) if len(targets) == 1 else None
    return DistanceTurn(
        values,
        target,
        mode,
        bool(_SCOPE.search(visible)),
        ambiguous,
        bool(_CORRECTION.match(visible)),
    )


@dataclass
class DistanceContext:
    segments: dict[str, Distance] = field(default_factory=dict)
    target: Distance | None = None

    def update(self, turn: DistanceTurn) -> bool:
        if turn.ambiguous:
            return False
        if turn.scoped and len(turn.segments) == 2:
            same_exchange = (
                turn.correction and turn.segments.keys() == self.segments.keys()
            )
            self.segments = turn.segments.copy()
            if turn.target is not None or not same_exchange:
                self.target = turn.target
            return True
        if turn.segments.keys() - self.segments.keys():
            return False
        self.segments.update(turn.segments)
        if turn.target is not None:
            self.target = turn.target
        return True


def plan_distance(
    content: str, history: Sequence[dict[str, str]]
) -> DistanceCalculation | DistanceClarification | None:
    """Replay the current distance exchange, trusting only explicit user operands."""
    current = _read_turn(content)
    if current is None or current.mode is None:
        return None
    previous_users = [row["content"] for row in history if row["role"] == "user"][-8:]
    context = DistanceContext()
    scoped = False
    for message in previous_users:
        turn = _read_turn(message)
        if turn is None:
            context, scoped = DistanceContext(), False
            continue
        scoped = scoped or turn.scoped
        if not context.update(turn):
            context = DistanceContext()
    if not (scoped or current.scoped):
        return None
    if not context.update(current) or len(context.segments) != 2:
        return DistanceClarification()
    if current.mode != "sum" and context.target is None:
        return DistanceClarification()
    first, second = context.segments.values()
    return DistanceCalculation((first, second), current.mode, context.target)


def _display_length(metres: str, unit: str = "m") -> str:
    amount = Decimal(metres).scaleb(-_UNIT_SCALE[unit])
    value = format(amount.normalize(), "f").replace(".", ",")
    return f"{value} {unit}"


def _gap_text(value: str) -> str:
    if value.startswith("-"):
        return f"powyżej celu o {_display_length(value[1:])}"
    return f"brakuje {_display_length(value)}"


def _distance_text(plan: DistanceCalculation, total: str, value: str) -> str:
    if plan.target is None or plan.mode == "sum":
        operands = " + ".join(
            _display_length(segment.metres) for segment in plan.segments
        )
        metres = _display_length(total)
        return f"Razem {metres} ({_display_length(total, 'km')}), bo {operands} = {metres}."
    gap = _gap_text(value)
    if plan.mode == "summary":
        unit = plan.target.unit
        return (
            f"Razem {_display_length(total, unit)}, "
            f"do {_display_length(plan.target.metres, unit)} {gap}."
            if not value.startswith("-")
            else f"Razem {_display_length(total, unit)}, {gap}."
        )
    if plan.mode == "recalculation":
        return f"{gap.capitalize()}, razem {_display_length(total)}."
    return f"{gap.capitalize()}."


def execute_distance(plan: DistanceCalculation) -> dict[str, Any]:
    """Use the bounded arithmetic executor and report verified metre values."""
    total = result_with_unit(plan.sum_expression, "m")
    total_value = total["value"]
    receipt = total
    target = (
        plan.target.metres if plan.target is not None and plan.mode != "sum" else None
    )
    if total_value is not None and target is not None:
        receipt = result_with_unit(f"{target} - ({plan.sum_expression})", "m")
    value = receipt["value"]
    if total_value is None or value is None:
        text = "Nie udało się obliczyć wyniku. Sprawdź długości odcinków."
    else:
        text = _distance_text(plan, total_value, value)
    tool: dict[str, Any] = {
        "tool": "calculator",
        **receipt,
        "recomputed": plan.repeat or plan.mode in ("recalculation", "summary"),
    }
    if target is not None and total_value is not None and value is not None:
        tool.update(total=total_value, target=format(Decimal(target).normalize(), "f"))
    return {"text": text, "response_source": "calculator", "tool_result": tool}
