"""Bind straightforward Studio calculations to the user's current quantities."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.direct_calculator import (
    CalculatorRequest,
    execute_calculator,
)
from venom_core.services.chat_policy.qualified_chat_quote import (
    is_text_transformation,
    without_quotes,
)
from venom_core.services.grounded_calculator import calculate

_NUMBER = r"[0-9]{1,7}(?:[.,][0-9]{1,4})?"
_WORD_COUNTS = {
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
    "dziewięć": 9,
    "dziewięciu": 9,
    "dziesięć": 10,
    "dziesięciu": 10,
}
_COUNT = rf"(?:[1-9][0-9]{{0,3}}|{'|'.join(_WORD_COUNTS)})"
_LENGTH = rf"(?P<value>{_NUMBER})\s*(?P<unit>mm|cm|m)\b"
_LENGTH_VALUE = re.compile(rf"\b{_LENGTH}", re.I)
_WORD = r"[^\W\d_]+"
_LENGTH_GROUP = re.compile(
    rf"\b(?P<count>{_COUNT})\s+(?P<label>{_WORD}(?:\s+{_WORD}){{0,3}}?)"
    rf"\s+po\s+{_LENGTH}",
    re.I,
)
_LENGTH_TOTAL = re.compile(
    r"\b(?:ile\s+(?:dokładnie\s+)?(?:cm|centymetr\w*|łącznie|razem)"
    r"|(?:policz|oblicz|podaj)\s+łączną\s+długość)\b",
    re.I,
)
_OTHER_LENGTH_UNIT = re.compile(
    r"\b(?:w\s+(?:milimetrach|metrach|kilometrach)|"
    r"ile\s+(?:(?:razem|łącznie)\s+)?(?:milimetr\w*|metr\w*|kilometr\w*|mm|m|km))\b",
    re.I,
)
_LENGTH_GAP = re.compile(
    r"\bile\s+(?:dokładnie\s+|jeszcze\s+)?(?:(?:cm|centymetr\w*)\s+)?brakuje\b", re.I
)
_LENGTH_CHANGE = re.compile(
    rf"\bkażd[ay]\s+(?P<label>krótk\w*|dług\w*)\s+(?:ma(?:\s+mieć)?|zmieniam\s+na)\s+{_LENGTH}",
    re.I,
)
_AVAILABLE = re.compile(
    rf"\b(?:odciął[ae]m|odcięt[eo]|odmierzy[łl][ae]m)\s+{_LENGTH}", re.I
)

_RATE_NAME = r"krajow\w*|zagraniczn\w*|normaln\w*|zwykł\w*|ulgow\w*"
_RATE = re.compile(
    rf"\b(?P<count>[1-9][0-9]{{0,3}})\s+(?:{_WORD}\s+)?(?P<label>{_RATE_NAME})"
    rf"\s+(?:(?:kosztuje|kosztują)\s+)?po\s+(?P<value>{_NUMBER})\s*zł\b",
    re.I,
)
_RATE_CHANGE = re.compile(
    rf"\b(?P<label>{_RATE_NAME})\s+(?:(?:są|był[yo]|były|jednak|teraz)\s+){{0,3}}"
    rf"(?:po|kosztują)\s+(?P<value>{_NUMBER})\s*zł\b",
    re.I,
)
_MONEY_VALUE = re.compile(rf"\b{_NUMBER}\s*zł\b", re.I)
_RATE_ONLY = re.compile(
    rf"\b(?:tylko\s+(?:za\s+)?|sam(?:ych|e|ymi)\s+)(?P<label>{_RATE_NAME})\b", re.I
)
_RATE_TOTAL = re.compile(
    r"(?:\b(?:kwot[ayę]|koszt|ile|sum[ayę])\b[^.!?\n]{0,42}"
    r"\b(?:wszystk\w*|całoś\w*|łącznie|razem)\b)"
    r"|\bile\s+łącznie\s+za\s+obie\s+grupy\b",
    re.I,
)

_MASS = rf"(?P<value>{_NUMBER})\s*(?P<unit>kg|g)\b"
_MASS_VALUE = re.compile(rf"\b{_MASS}", re.I)
_MASS_SCOPE = re.compile(r"\b(?:obciążniki|odważniki)\b", re.I)
_MASS_ENTRY = re.compile(
    rf"(?:^|,\s*)(?P<label>{_WORD}(?:\s+{_WORD}){{0,2}}?)\s+(?:waży\s+)?{_MASS}",
    re.I,
)
_MASS_UPDATE = re.compile(
    rf"^(?P<label>{_WORD})\s+(?:pomylon\w*[^.!?]{{0,42}},\s*właściw\w* waży"
    rf"|jednak waży|waży teraz)\s+{_MASS}[.!]",
    re.I,
)
_MASS_WITH_CASE = re.compile(
    r"\b(?:mas[ęay]|waż\w*)\b[^.!?]{0,45}\bkomplet\w*\s+z\s+"
    r"(?:pokrowcem|etui|opakowaniem)\b",
    re.I,
)
_MASS_WITHOUT_CASE = re.compile(
    r"\bile ważą same (?:obciążniki|odważniki) w gramach\b", re.I
)
_MASS_CASE = re.compile(r"\b(?:pokrowiec|etui|opakowanie)$", re.I)

_WIDTHS = re.compile(
    r"\b(?:odczyt(?:y)?\s+)?szerokości(?:\s+desek|\s+listew|\s+płyt)?\s*:\s*", re.I
)
_WIDTH = re.compile(
    rf"(?:^|[,;]\s*|\s+(?:i|oraz)\s+)(?P<label>{_WORD}(?:\s+{_WORD}){{0,3}}?)"
    rf"\s+{_LENGTH}",
    re.I,
)
_WIDTH_CHANGE = re.compile(
    rf"\b(?:poszerz\w*|zwę[żz]\w*|zmieniam)\s+(?P<label>{_WORD}(?:\s+{_WORD}){{0,3}}?)"
    rf"\s+(?:do|na)\s+{_LENGTH}",
    re.I,
)
_WIDTH_REPLACEMENT = re.compile(
    rf"\b(?:deskę|listwę|płytę)\s+(?P<label>{_WORD})\s+wymieniliśm[yi]\s+na\s+{_LENGTH}",
    re.I,
)
_WIDTH_QUERY = re.compile(r"\b(?P<widest>najszer\w*)\b|\bnajwęż\w*\b", re.I)
_UNCERTAIN = re.compile(
    r"\b(?:około|maksymalnie|co najmniej|co najwyżej|chyba|albo|nie wiem|nie znam)\b",
    re.I,
)
_NO_CALCULATION = re.compile(
    r"\bnie\s+(?:licz|obliczaj|przeliczaj|podawaj\s+wyniku)\b", re.I
)
_SCALES = {"mm": -1, "cm": 0, "m": 2}


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _length_in_cm(match: re.Match[str]) -> Decimal:
    return _decimal(match["value"]).scaleb(_SCALES[match["unit"].casefold()])


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _polish(value: Decimal) -> str:
    return _number(value).replace(".", ",")


def _rate_key(text: str) -> str:
    text = text.casefold()
    if text.startswith("zwykł"):
        return "normaln"
    return next(
        key
        for key in ("krajow", "zagraniczn", "normaln", "ulgow")
        if text.startswith(key)
    )


def _length_key(text: str) -> str:
    return next(
        (
            key
            for key in ("krótk", "dług")
            if re.search(rf"\b{key}\w*", text.casefold())
        ),
        "",
    )


@dataclass(frozen=True)
class _Term:
    count: int
    value: Decimal

    @property
    def expression(self) -> str:
        return f"{self.count}*{_number(self.value)}"

    def readable(self, unit: str) -> str:
        return f"{self.count} × {_polish(self.value)} {unit}"


@dataclass(frozen=True)
class StudioCalculation:
    expression: str
    unit: str
    render: Callable[[str], str]

    def publish(self) -> dict[str, Any]:
        reply = execute_calculator(CalculatorRequest(self.expression, self.unit))
        if reply["tool_result"]["status"] == "succeeded":
            reply["text"] = self.render(reply["text"])
        return reply


def _read_total_lengths(message: str) -> dict[str, _Term]:
    groups = list(_LENGTH_GROUP.finditer(message))
    if (
        not _LENGTH_TOTAL.search(message)
        or re.search(r"\d", _LENGTH_GROUP.sub("", message))
        or len(groups) != 2
        or len(_LENGTH_VALUE.findall(message)) != len(groups)
    ):
        return {}
    terms = [
        _Term(
            int(m["count"])
            if m["count"].isdecimal()
            else _WORD_COUNTS[m["count"].casefold()],
            _length_in_cm(m),
        )
        for m in groups
    ]
    keys = [_length_key(m["label"]) for m in groups]
    if set(keys) == {"dług", "krótk"}:
        return dict(zip(keys, terms, strict=True))
    labels = {m["label"].casefold() for m in groups}
    if not any(keys) and len(labels) == 1 and terms[0].value != terms[1].value:
        shorter, longer = sorted(terms, key=lambda term: term.value)
        return {"krótk": shorter, "dług": longer}
    return {}


def _length_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    lengths: dict[str, _Term] = {}
    available = None
    for message in turns:
        available = list(_AVAILABLE.finditer(message))
        changes = list(_LENGTH_CHANGE.finditer(message))
        if current := _read_total_lengths(message):
            lengths = current
        elif (
            lengths
            and len(changes) == 1
            and len(_LENGTH_VALUE.findall(message)) == 1 + len(available)
        ):
            change = changes[0]
            key = _length_key(change["label"])
            lengths[key] = replace(lengths[key], value=_length_in_cm(change))
        elif not (
            lengths
            and len(available) == 1
            and not changes
            and len(_LENGTH_VALUE.findall(message)) == 1
        ):
            lengths = {}
    if not lengths or _OTHER_LENGTH_UNIT.search(turns[-1]):
        return None
    total = "+".join(term.expression for term in lengths.values())
    formula = " + ".join(term.readable("cm") for term in lengths.values())
    if available and _LENGTH_GAP.search(turns[-1]):
        measured = _length_in_cm(available[0])
        difference = f"({total})-{_number(measured)}"

        def render_gap(result: str) -> str:
            result_quantity = result.removeprefix("-")
            if result.startswith("-"):
                return f"Jest o {result_quantity} więcej, niż potrzeba."
            return f"Brakuje {result} ({formula} − {_polish(measured)} cm)."

        return StudioCalculation(difference, "cm", render_gap)
    if available:
        return None
    return StudioCalculation(total, "cm", lambda result: f"{formula} = {result}.")


def _rate_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    rates: dict[str, _Term] = {}
    for message in turns:
        entries = list(_RATE.finditer(message))
        changes = list(_RATE_CHANGE.finditer(message))
        amount_count = len(_MONEY_VALUE.findall(message))
        if len(entries) >= 2 and amount_count == len(entries):
            rates = {
                _rate_key(m["label"]): _Term(int(m["count"]), _decimal(m["value"]))
                for m in entries
            }
            if len(entries) != len(rates):
                rates = {}
        elif (
            len(changes) == amount_count == 1
            and not re.search(r"\d", _RATE_CHANGE.sub("", message))
            and (key := _rate_key(changes[0]["label"])) in rates
        ):
            rates[key] = replace(rates[key], value=_decimal(changes[0]["value"]))
        elif (
            entries
            or re.search(r"\d", message)
            or not (_RATE_ONLY.search(message) or _RATE_TOTAL.search(message))
        ):
            rates = {}
    if wanted := _RATE_ONLY.search(turns[-1]):
        term = rates.get(_rate_key(wanted["label"]))
        return (
            StudioCalculation(
                term.expression,
                "zł",
                lambda result: f"{term.readable('zł')} = {result}.",
            )
            if term is not None
            else None
        )
    if len(rates) < 2 or not _RATE_TOTAL.search(turns[-1]):
        return None
    parts = [_polish(_decimal(calculate(term.expression))) for term in rates.values()]
    formula = " + ".join(f"{part} zł" for part in parts)
    expression = "+".join(term.expression for term in rates.values())
    return StudioCalculation(expression, "zł", lambda result: f"{formula} = {result}.")


def _width_key(label: str) -> str:
    return label.casefold().rstrip("aąęy")


def _width_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    widths: dict[str, tuple[str, Decimal]] = {}
    for message in turns:
        if header := _WIDTHS.search(message):
            fields = message[header.end() :].split(". ", 1)[0].rstrip(".?!")
            matches = list(_WIDTH.finditer(fields))
            if not 2 <= len(matches) <= 6 or _WIDTH.sub("", fields).strip(" ,;"):
                return None
            widths = {
                _width_key(m["label"]): (m["label"], _length_in_cm(m)) for m in matches
            }
            if len(widths) != len(matches):
                return None
        elif widths and (
            update := _WIDTH_CHANGE.search(message)
            or _WIDTH_REPLACEMENT.search(message)
        ):
            key = _width_key(update["label"])
            if key not in widths or len(_LENGTH_VALUE.findall(message)) != 1:
                return None
            widths[key] = (widths[key][0], _length_in_cm(update))
        elif not _WIDTH_QUERY.search(message) or _LENGTH_VALUE.search(message):
            widths = {}
    question = _WIDTH_QUERY.search(turns[-1])
    if not widths or question is None or len(_WIDTH_QUERY.findall(turns[-1])) != 1:
        return None
    label, amount = (max if question["widest"] else min)(
        widths.values(), key=lambda item: item[1]
    )
    if sum(value == amount for _, value in widths.values()) != 1:
        return None
    comparison = (
        "Największa szerokość" if question["widest"] else "Najmniejsza szerokość"
    )
    choices = ", ".join(
        f"{name} {_polish(value)} cm" for name, value in widths.values()
    )
    return StudioCalculation(
        _number(amount),
        "cm",
        lambda result: f"{comparison}: {label}, {result}. Porównanie: {choices}.",
    )


def _grams(match: re.Match[str]) -> Decimal:
    value = _decimal(match["value"])
    return value.scaleb(3) if match["unit"].casefold() == "kg" else value


def _mass_start(text: str) -> tuple[dict[str, Decimal], str] | None:
    *lead, rest = text.split(". ", 1)
    if not lead or not _MASS_SCOPE.search(lead[0]):
        return None
    raw, _, _ = rest.partition(". ")
    fields = list(_MASS_ENTRY.finditer(raw))
    if len(fields) != 3 or _MASS_ENTRY.sub("", raw).strip(" ,."):
        return None
    weights = {entry["label"].casefold(): _grams(entry) for entry in fields}
    containers = [label for label in weights if _MASS_CASE.search(label)]
    return (
        (weights, containers[0]) if len(weights) == 3 and len(containers) == 1 else None
    )


def _mass_calculation(turns: Sequence[str]) -> StudioCalculation | None:
    current = turns[-1]
    if not (_MASS_WITHOUT_CASE.search(current) or _MASS_WITH_CASE.search(current)):
        return None
    initial = _mass_start(current)
    start = initial or (_mass_start(turns[-2]) if len(turns) > 1 else None)
    if start is None:
        return None
    weights, container = start
    if initial is None:
        update = _MASS_UPDATE.match(current)
        if update is None or len(_MASS_VALUE.findall(current)) != 1:
            return None
        label = update["label"].casefold()
        if label not in weights or label == container:
            return None
        weights[label] = _grams(update)
    if not _MASS_WITH_CASE.search(current):
        del weights[container]
    expression = "+".join(_number(value) for value in weights.values())
    formula = " + ".join(f"{_polish(value)} g" for value in weights.values())
    return StudioCalculation(expression, "g", lambda result: f"{formula} = {result}.")


def plan_studio_calculation(
    content: str, history: Sequence[HistoryMessage]
) -> StudioCalculation | None:
    """Rebuild a supported calculation from the recent user turns only."""
    users = [turn.content for turn in history if turn.role == "user"][-5:]
    turns = [without_quotes(text) for text in (*users, content)]
    if is_text_transformation(content) or _NO_CALCULATION.search(turns[-1]):
        return None
    latest_uncertain = max(
        (
            i
            for i, turn in enumerate(turns)
            if len(turn) > 512
            or _UNCERTAIN.search(turn)
            or _NO_CALCULATION.search(turn)
        ),
        default=-1,
    )
    active = turns[latest_uncertain + 1 :]
    if not active:
        return None
    return (
        _length_calculation(active)
        or _rate_calculation(active)
        or _width_calculation(active)
        or _mass_calculation(active)
    )
