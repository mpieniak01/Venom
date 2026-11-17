"""Opt-in model pilot; full evidence and qualified semantic review before release."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Annotated, Any, Literal, Protocol

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    field_validator,
)

from venom_core.services.grounded_calculator import (
    MAX_EXPRESSION_CHARS,
    CalculationError,
    calculate,
)
from venom_core.services.grounded_dialogue import (
    MAX_CALCULATIONS,
    UNITS,
    AnswerDraft,
    CalculationClaim,
    CalculationEvidence,
    CalculationPlan,
    Evidence,
    EvidenceError,
    GroundedTurn,
    PublishedAnswer,
    Requirements,
    SourceBackend,
    SourceDocument,
    SourceQuote,
    TurnPlan,
    _normal,
    bind_source_quotes,
    explicit_result_unit,
    requested_card_ids,
    requested_meeting_place,
    requested_pickup_details,
    strip_public_bookkeeping,
    text_hash,
    verify_result_prose,
)
from venom_core.services.grounded_presentation import (
    ROUNDING_MODE,
    normalize_claim,
    requested_precision,
    rounded_value,
)

MAX_MODEL_INPUT_BYTES = 6000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceQuery(StrictModel):
    source_query: StrictStr = Field(max_length=500)


def _validate_missing(missing: list[str]) -> list[str]:
    if any(not item.strip() for item in missing):
        raise ValueError("missing input must be named")
    return missing


MissingLabels = Annotated[
    list[Annotated[StrictStr, Field(min_length=1, max_length=160)]],
    Field(max_length=8),
    AfterValidator(_validate_missing),
]


class MissingInputs(StrictModel):
    missing: MissingLabels


class InputAssessment(StrictModel):
    current_state: StrictStr = Field(min_length=1, max_length=700)
    missing: MissingLabels


class Calculation(StrictModel):
    calculation_id: StrictStr = Field(min_length=1, max_length=80)
    expression: StrictStr = Field(
        min_length=1, max_length=MAX_EXPRESSION_CHARS, pattern=r"^[0-9.+*/() -]+$"
    )
    unit: StrictStr = Field(json_schema_extra={"enum": [*sorted(UNITS)]})
    input_unit: StrictStr = Field(
        default="",
        description="Jednostka całego wyrażenia przed konwersją. Dla ilorazu razy 100 jest to %, nie jednostka liczebności. Puste oznacza brak konwersji.",
    )

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, unit: str) -> str:
        if unit not in UNITS:
            raise ValueError("unsupported calculator unit")
        return unit


_CONVERSIONS = {
    ("cm", "m"): "/100",
    ("m", "cm"): "*100",
    ("ml", "l"): "/1000",
    ("l", "ml"): "*1000",
    ("g", "kg"): "/1000",
    ("kg", "g"): "*1000",
    ("min", "h"): "/60",
    ("h", "min"): "*60",
    ("m/s", "km/h"): "*18/5",
    ("km/h", "m/s"): "*5/18",
}


def _compile_calculation(item: Calculation) -> Calculation:
    """Apply conversion to the value of the entire expression."""
    if not item.input_unit or item.input_unit == item.unit:
        return item
    scale = _CONVERSIONS.get((item.input_unit, item.unit))
    if scale is None:
        raise EvidenceError("pilot_conversion_unsupported")
    return item.model_copy(
        update={"expression": f"({item.expression}){scale}", "input_unit": ""}
    )


_COUNT_WORDS = {
    "jeden": 1,
    "jedna": 1,
    "dwa": 2,
    "dwie": 2,
    "trzy": 3,
    "cztery": 4,
    "pięć": 5,
    "sześć": 6,
    "siedem": 7,
    "osiem": 8,
    "dziewięć": 9,
    "dziesięć": 10,
}
_HEADCOUNT = (
    rf"\b([0-9]{{1,4}}|{'|'.join(_COUNT_WORDS)})\s+os(?:ób|ob(?:a|y|om|ę|ach|ami))\b"
)
_ANY_HEADCOUNT = re.compile(_HEADCOUNT, re.IGNORECASE)
_JOINED = re.compile(
    rf"^\s*(?:dołącza(?:ją)?|dochodzi|dochodzą)\s+{_HEADCOUNT}", re.IGNORECASE
)
_GROUP_BASE = re.compile(
    rf"(?:^\s*|[.!?]\s*|\bczy\s+(?:według\s+(?:karty\s+)?[\w-]+\s+)?"
    rf"|\bgrupa liczy\s+|\bgrupa\s+|\bjest nas\s+|\bteraz są\s+){_HEADCOUNT}",
    re.IGNORECASE,
)
_BOOKING_QUESTION = re.compile(
    r"\bczy (?:zapis|rezerwacja) (?:jest )?(?:potrzebn[ay]|wymagan[ay]|obowiązkow[ay])\b",
    re.IGNORECASE,
)
_BOOKING_RESULT = re.compile(
    r"(?:(?:zapis|rezerwacja)(?: (?:jest )?(?:potrzebn[ay]|wymagan[ay]|obowiązkow[ay]))"
    r"|(?:potrzeba|obowiązek|konieczność) (?:zapisu|rezerwacji))"
)
_SPEED_CONVERSION = re.compile(
    r"\bprzelicz\b[^.!?\n]*\b(?:na|w)\s+(km/h|m/s)\b", re.IGNORECASE
)

_SPEED_REQUEST = re.compile(
    r"\b(?:oblicz|policz|wyznacz)\s+(?:\w+\s+){0,3}prędkość\s+w\s+(m/s|km/h)\b",
    re.IGNORECASE,
)
_PRIOR_RESULT = re.compile(
    r"\b(?:przelicz|użyj|weź)\s+(?:(?:ten|tego|poprzedni|wcześniejszy)\s+)?wynik(?:u)?\b",
    re.IGNORECASE,
)
_COMPUTE_REQUEST = re.compile(r"\b(?:oblicz|policz|przelicz|wyznacz)\b", re.IGNORECASE)
_REMAINDER_REQUEST = re.compile(
    r"\b(?:oblicz|policz|wyznacz)\s+(?:pozostałość|ile\s+(?:zostało|pozostało))\b",
    re.IGNORECASE,
)


_TOTAL_COST_OUTPUTS = {
    "całkowity koszt",
    "koszt całkowity",
    "łączny koszt",
    "koszt łączny",
    "pełny koszt",
    "pełen koszt",
    "suma kosztów",
    "całkowita kwota",
    "łączna kwota",
}
_TOTAL_COST_REQUEST = re.compile(
    r"\b(?:oblicz|policz|wyznacz|wylicz|podaj|ile wynosi|jaki jest)\b[^!?;\n]{0,100}"
    r"\b(?:(?:pełny|pełen|łączny|całkowity)\s+koszt|koszt\s+(?:łączny|całkowity)|sumę\s+kosztów)\b",
    re.IGNORECASE,
)


def _percentage_outputs(message: str) -> set[str]:
    outputs = {"procent", "wynik procentowy", "udział procentowy"}
    # Match the requested quantity, not every percentage mentioned in history.
    for match in re.finditer(r"\b(?:procent|udział)\s+([^.!?;\n]+)", message.lower()):
        subject = re.split(
            r"\s*(?:\bzaokrąglon\w*|\bpo (?:zmianie|korekcie)|\bdo (?:[0-9]+|jednego|dwóch|trzech|czterech|pięciu|sześciu) miejsc|\bi (?:podaj|oblicz|policz))\b",
            match[1],
            maxsplit=1,
        )[0].strip()
        if subject and len(subject) <= 120:
            outputs.update({f"procent {subject}", f"udział {subject}"})
    return outputs


def _calculation_outputs(message: str, speed_unit: str | None) -> set[str]:
    outputs = (
        {"wynik", "wynik obliczenia", "wynik rachunku"}
        if _COMPUTE_REQUEST.search(message) and not _PRIOR_RESULT.search(message)
        else set()
    )
    if speed_unit:
        outputs.update({f"prędkość {speed_unit}", f"prędkość w {speed_unit}"})
    if explicit_result_unit(message) == "%":
        outputs.update(_percentage_outputs(message))
    if _TOTAL_COST_REQUEST.search(message):
        outputs.update(_TOTAL_COST_OUTPUTS)
    if _REMAINDER_REQUEST.search(message):
        outputs.update({"pozostałość", "wynik pozostałości"})
    return outputs


_NUMBER = r"[+-]?[0-9]+(?:[.,][0-9]+)?"
_STATE_NUMBER = r"[+-]?[0-9]{1,9}(?:[.,][0-9]{1,6})?"
_MEAN_REQUEST = re.compile(
    rf"\s*(?:policz|oblicz|wyznacz)\s+średnią(?:\s+arytmetyczną)?\s+z\s+"
    rf"(?:(?:wyników|liczb|wartości)\s+)?"
    rf"(?P<numbers>{_NUMBER}(?:(?:,\s+|\s+i\s+){_NUMBER})+)"
    r"(?:\s+(?P<points>punktów|punkty|pkt\.?))?\s*[.!?]?\s*",
    re.IGNORECASE,
)
_PRICE_QUESTION = re.compile(
    r"\b(?:ile\s+(?:(?:złotych|zł)\s+)?kosztuje|jaka\s+jest\s+cena)\s+([^?!.]+)",
    re.IGNORECASE,
)
_PRICE_RESULT = re.compile(
    r"(?:cena|koszt|opłata|kwota|stawka|cennik)(?:\s+(.+))?", re.IGNORECASE
)


def _explicit_mean(message: str) -> Calculation | None:
    match = _MEAN_REQUEST.fullmatch(message)
    if match is None:
        return None
    operands = re.split(r",\s+|\s+i\s+", match["numbers"], flags=re.IGNORECASE)
    addends = "+".join(f"({item.replace(',', '.')})" for item in operands)
    expression = f"({addends})/{len(operands)}"
    if len(expression) > MAX_EXPRESSION_CHARS:
        return None
    return Calculation(
        calculation_id="arithmetic_mean",
        expression=expression,
        unit="punktów" if match["points"] else "",
    )


_LENGTH_INPUT = rf"(?P<value>{_NUMBER})\s*(?P<input>cm|m)\b"
_LENGTH_TARGET = r"(?P<target>centymetry|centymetrach|metry|metrach|cm|m)\b"
_LENGTH_COMMAND = re.compile(
    rf"\s*(?:przelicz|zamień)\s+{_LENGTH_INPUT}\s+na\s+{_LENGTH_TARGET}[.!?]?\s*",
    re.IGNORECASE,
)
_LENGTH_STATEMENT = re.compile(
    rf"\s*[^.?!\n]*?\bma\s+{_LENGTH_INPUT}\s*[.]\s*"
    rf"(?:przelicz|podaj|zamień)\s+(?:(?:jej|jego|tę|ten)\s+)?długość\s+"
    rf"(?:na|w)\s+{_LENGTH_TARGET}[.!?]?\s*",
    re.IGNORECASE,
)


def _explicit_length_conversion(message: str) -> Calculation | None:
    """Handle single, explicit lengths without asking a model to infer units."""
    match = _LENGTH_COMMAND.fullmatch(message) or _LENGTH_STATEMENT.fullmatch(message)
    if match is None or len(re.findall(_LENGTH_INPUT, message, re.IGNORECASE)) != 1:
        return None
    target = match["target"].casefold()
    output_unit = "cm" if target.startswith(("cm", "centymetr")) else "m"
    return _compile_calculation(
        Calculation(
            calculation_id="length_conversion",
            expression=match["value"].replace(",", "."),
            input_unit=match["input"].casefold(),
            unit=output_unit,
        )
    )


_SPEED_REFERENCE = re.compile(
    r"\b(?:przelicz\w*|przeliczenie)\b[^.!?]*\bpoprzedni(?:ego)?\s+wynik(?:u)?\b",
    re.IGNORECASE,
)
_SPEED_OUTPUT = re.compile(r"\b(?:w|na)\s+(km/h|m/s)\b", re.IGNORECASE)
_TRAVEL_DISTANCE = re.compile(
    rf"\b(?:cały\s+odcinek|długość\s+odcinka|cała\s+trasa|droga)\s+(?:ma|wynosi)\s+({_STATE_NUMBER})\s+m\b",
    re.IGNORECASE,
)
_TRAVEL_SECONDS = re.compile(
    rf"\b(?:zajęło(?:\s+to)?|trwało|czas\s+wynosi)\s+({_STATE_NUMBER})\s+(?:s|sekund(?:y|ę)?)\b",
    re.IGNORECASE,
)
_REMAINING_VOLUME = re.compile(
    rf"^\s*z\s+(?:naczynia|zbiornika|pojemnika)\s+z\s+({_STATE_NUMBER})\s*(ml|l)\s+"
    rf"(?:przelano|odlano|pobrano)\s+({_STATE_NUMBER})\s*(ml|l)\b",
    re.IGNORECASE,
)
_VOLUME_FOLLOWUP = re.compile(
    r"^\s*ile\s+(litrów|mililitrów)\s+wynosi\s+(?:ta\s+)?pozostałość\b", re.IGNORECASE
)
_MAP_SCALE = re.compile(
    rf"^\s*na\s+(?:planie|mapie)\s+(?:każdy\s+centymetr|1\s*cm)\s+"
    rf"(?:oznacza|odpowiada)\s+({_STATE_NUMBER})\s*(?:m|metr(?:y|ów|owi)?)\b",
    re.IGNORECASE,
)
_MAP_INITIAL = re.compile(
    rf"^[^.!?]*\bna\s+(?:planie|mapie)\s+ma\s+({_STATE_NUMBER})\s*cm\b", re.IGNORECASE
)
_MAP_CORRECTION = re.compile(
    rf"^\s*(?:jest\s+)?(?:nowy|poprawiony)\s+pomiar[:,]?\s+({_STATE_NUMBER})\s*cm\b",
    re.IGNORECASE,
)
_MAP_LENGTH_REQUEST = re.compile(
    r"\b(?:oblicz|policz|wyznacz)\b[^.!?]*\b(?:długość|odległość)\b",
    re.IGNORECASE,
)
_MAP_DIFFERENCE = re.compile(
    r"^\s*o\s+ile\s+zmienił\s+się\s+(?:wynik|pomiar|długość)\b[^.!?]*"
    r"\b(?:po\s+poprawieniu|po\s+korekcie)\s+pomiaru\b",
    re.IGNORECASE,
)


def _map_measurements(messages: tuple[str, ...]) -> tuple[str, tuple[str, ...]] | None:
    factor = ""
    lengths: list[str] = []
    for message in messages:
        if scale := _MAP_SCALE.match(message):
            factor = scale[1].replace(",", ".")
            lengths.clear()
            continue
        measurement = (
            _MAP_INITIAL.match(message)
            if not lengths
            else _MAP_CORRECTION.match(message)
        )
        if factor and measurement and _MAP_LENGTH_REQUEST.search(message):
            lengths.append(measurement[1].replace(",", "."))
        else:
            factor = ""
            lengths.clear()
    if not factor or not lengths or Decimal(factor) <= 0:
        return None
    if any(Decimal(length) < 0 for length in lengths):
        return None
    return factor, tuple(lengths)


def _context_calculation(message: str, previous: tuple[str, ...]) -> Calculation | None:
    if len(previous) >= 2 and _SPEED_REFERENCE.search(message):
        targets = {item.lower() for item in _SPEED_OUTPUT.findall(message)}
        distances = _TRAVEL_DISTANCE.findall(previous[-2])
        durations = _TRAVEL_SECONDS.findall(previous[-1])
        if len(targets) == len(distances) == len(
            durations
        ) == 1 and _SPEED_REQUEST.search(previous[-2]):
            path = distances[0].replace(",", ".")
            duration = durations[0].replace(",", ".")
            if Decimal(path) >= 0 and Decimal(duration) > 0:
                return _compile_calculation(
                    Calculation(
                        calculation_id="average_speed",
                        expression=f"{path}/{duration}",
                        input_unit="m/s",
                        unit=targets.pop(),
                    )
                )
    if previous and (unit := _VOLUME_FOLLOWUP.match(message)):
        remainder = _REMAINING_VOLUME.match(previous[-1])
        if remainder and _REMAINDER_REQUEST.search(previous[-1]):
            initial = _stock_number(remainder[1], remainder[2].lower(), "ml")
            removed = _stock_number(remainder[3], remainder[4].lower(), "ml")
            if Decimal(initial) >= Decimal(removed) >= 0:
                return _compile_calculation(
                    Calculation(
                        calculation_id="volume_remainder",
                        expression=f"{initial}-{removed}",
                        input_unit="ml",
                        unit="l" if unit[1].casefold() == "litrów" else "ml",
                    )
                )
    scale = _map_measurements((*previous, message))
    if scale:
        factor, lengths = scale
        return Calculation(
            calculation_id="scaled_length",
            expression=f"{lengths[-1]}*{factor}",
            unit="m",
        )
    return None


def _length_draft(calculation: CalculationEvidence) -> Draft:
    value = calculation.value.replace(".", ",")
    return Draft(
        prose=f"{value} {calculation.unit}.",
        sources=[],
        calculations=[
            ResultClaim(
                calculation_id=calculation.calculation_id,
                value=calculation.value,
                unit=calculation.unit,
            )
        ],
    )


def _mean_draft(calculation: CalculationEvidence) -> Draft:
    value = calculation.value.replace(".", ",")
    if calculation.unit == "punktów":
        if value.lstrip("-") == "1":
            unit = "punkt"
        elif "," in value:
            unit = "punktu"
        elif value[-1] in "234" and value[-2:] not in {"12", "13", "14"}:
            unit = "punkty"
        else:
            unit = "punktów"
        value = f"{value} {unit}"
    return Draft(
        prose=f"Średnia wynosi {value}.",
        sources=[],
        calculations=[
            ResultClaim(
                calculation_id=calculation.calculation_id,
                value=calculation.value,
                unit=calculation.unit,
            )
        ],
    )


def _price_subject(subject: str) -> tuple[str, ...]:
    # The question and the reported label often use different Polish cases.
    normalized = _normal(subject).removeprefix("za ")
    # Polish deverbal nouns use forms such as "przechowanie" and "przechowania".
    words = re.sub(r"ni[aeu]\b", "ni", normalized).split()
    return tuple(
        re.sub(r"(?:ami|ach|om|em|ej|ie|[aiouy])$", "", word)
        if len(word) >= 5
        else word
        for word in words
    )


def _price_result(label: str, subject: str) -> bool:
    match = _PRICE_RESULT.fullmatch(label)
    return bool(
        match
        and (match[1] is None or _price_subject(match[1]) == _price_subject(subject))
    )


_LOCATION_QUESTION = re.compile(
    r"\bgdzie\b[^.!?]*?\b(?:jest|będzie|odbywa\s+się)\s+([^.!?]+?)(?:\s+tego\s+dnia)?[.!?]?\s*$",
    re.IGNORECASE,
)
_LOCATION_RESULT = re.compile(r"(?:miejsce|lokalizacja|adres)\s+(.+)")


def _source_location_inputs(message: str, missing: list[str]) -> list[str]:
    """A place requested from a complete card is an output, as a price is."""
    question = _LOCATION_QUESTION.search(message)
    if question is None:
        return missing
    subject = _price_subject(question[1])
    return [
        item
        for item in missing
        if not (
            (label := _LOCATION_RESULT.fullmatch(_normal(item).rstrip(".?")))
            and _price_subject(label[1]) == subject
        )
    ]


def _headcount(value: str) -> int:
    return (
        int(value)
        if value.isascii() and value.isdecimal()
        else _COUNT_WORDS[value.lower()]
    )


_GROUP_LEAVE = re.compile(
    rf"^\s*(?:odchodzi|odchodzą|ubywa|ubywają)\s+{_HEADCOUNT}", re.IGNORECASE
)
_GROUP_UNDO = re.compile(
    r"^\s*cofnij\s+ostatnią\s+zmianę\s+(?:liczebności|liczby osób)\b",
    re.IGNORECASE,
)


def _group_previous(messages: tuple[str, ...]) -> int | None:
    """Replay explicit user updates. A retransmitted turn yields the same state."""
    states: list[int | None] = []
    for message in messages:
        counts = _ANY_HEADCOUNT.findall(message)
        if _GROUP_UNDO.match(message) and not counts:
            if len(states) > 1:
                states.pop()
            continue
        if not counts:
            continue
        base = _GROUP_BASE.search(message)
        joined = _JOINED.match(message)
        left = _GROUP_LEAVE.match(message)
        previous = states[-1] if states else None
        if len(counts) != 1:
            states.clear()
        elif joined and previous is not None:
            states.append(previous + _headcount(joined[1]))
        elif left and previous is not None:
            total = previous - _headcount(left[1])
            states.append(total if total >= 0 else None)
        elif base:
            states.append(_headcount(base[1]))
        else:
            states.clear()
    return states[-1] if states else None


def _group_change(message: str, history: tuple[str, ...]) -> dict[str, int] | None:
    joined = _JOINED.match(message)
    if not joined or len(_ANY_HEADCOUNT.findall(message)) != 1:
        return None
    before = _group_previous(history)
    if before is None:
        return None
    added = _headcount(joined[1])
    return {"previous": before, "joined": added, "total": before + added}


def _group_update(message: str, previous: str) -> dict[str, int] | None:
    """Resolve an explicit addition from the two-turn external reviewer contract."""
    return _group_change(message, (previous,))


_QUANTITY_UNITS = {"ml": "ml", "l": "ml", "g": "g", "kg": "g"}
_STOCK_VOLUME = re.compile(
    r"^(?:(?:zanotuj|zapisz|potwierdź)\s+[^:]+:\s*|"
    r"w\s+(?:rejestrze|spisie|magazynie)\s+[^:]+?\bzapisz\s*:?\s*)([0-9].*)$",
    re.IGNORECASE,
)
_VOLUME_ITEM = re.compile(
    rf"({_STATE_NUMBER})\s+(ml|l|g|kg)\s+w(?:e)?\s+(?:lokalizacji\s+)?([\w-]+)",
    re.IGNORECASE,
)
_CATEGORY_ANCHOR = re.compile(r"^.+?\bwpisz:\s*(.+)$", re.IGNORECASE)
_CATEGORY_ITEM = re.compile(r"kategoria\s+([\w-]+)\s+ma\s+([0-9]{1,6})", re.IGNORECASE)
_STOCK_COUNT = re.compile(
    r"^(?:w\s+[\w-]+\s+)?są\s+(\d{1,6})\s+(przesyłek|paczek|elementów|sztuk)\s+"
    r"([\w-]+)\s+i\s+(\d{1,6})\s+([\w-]+)$",
    re.IGNORECASE,
)
_VOLUME_SET = re.compile(
    r"^w(?:e)?\s+([\w-]+)\s+(?:jest|zostało|mamy)\s+(?:jednak\s+)?"
    rf"({_STATE_NUMBER})\s+(ml|l|g|kg)$",
    re.IGNORECASE,
)
_VOLUME_DELTA = re.compile(
    r"^z(?:e)?\s+([\w-]+)\s+(odlano|dolano|dodano|pobrano)\s+"
    rf"({_STATE_NUMBER})\s+(ml|l|g|kg)$",
    re.IGNORECASE,
)
_REGISTER_SET = re.compile(
    rf"^wpis\s+dla\s+([\w-]+)\s+zmieniam\s+na\s+({_STATE_NUMBER})\s+(ml|l|g|kg)$",
    re.IGNORECASE,
)
_CATEGORY_SET = re.compile(
    r"^(?:[^:]+:\s*)?skoryguj\s+(?:kategorię\s+)?([\w-]+)\s+na\s+([0-9]{1,6})$",
    re.IGNORECASE,
)
_CATEGORY_REMOVE = re.compile(
    r"^z\s+kategorii\s+([\w-]+)\s+(?:zdjęto|odjęto|wydano)\s+([0-9]{1,6})$",
    re.IGNORECASE,
)
_CATEGORY_ADD = re.compile(
    r"^(?:dopisz|dodaj)\s+do\s+kategorii\s+([\w-]+)\s+(?:jeszcze\s+)?([0-9]{1,6})$",
    re.IGNORECASE,
)
_COUNT_SET = re.compile(
    r"^([\w-]+)\s+(?:skorygowano|zmieniono)\s+na\s+(\d{1,6})$", re.IGNORECASE
)
_COUNT_DELTA = re.compile(
    rf"(?:wysłano|wydano|odjęto|dodano|przyjęto)\s+"
    rf"(\d{{1,6}}|{'|'.join(_COUNT_WORDS)})\s+z\s+([\w-]+)$",
    re.IGNORECASE,
)
_STOCK_UNDO = re.compile(r"cofnij ostatnią (?:zmianę|korektę)", re.IGNORECASE)
_STOCK_QUERY = re.compile(
    r"^(?:(?:oblicz|policz|podaj|potwierdź|napisz|zestaw|ile)\b|"
    r"chcę\s+(?:teraz\s+)?sumę\b|(?:w\s+wypisie|na\s+tablicę)\s+[^.?!]*\bpodaj\b)",
    re.IGNORECASE,
)
_STOCK_TOTAL = re.compile(
    r"\b(?:sum[ęay]|łącznie|łączn\w*|razem|zapas\s+po)\b", re.IGNORECASE
)
_STOCK_REMAIN = re.compile(
    r"\bile\s+(?:(?P<category>[\w-]+)\s+)?(?:zostało|pozostało)"
    r"(?:\s+w(?:e)?\s+(?:sam(?:ej|ym)\s+)?(?P<location>[\w-]+))?",
    re.IGNORECASE,
)

_STOCK_LIST = re.compile(
    r"\bpodaj\s+([\w-]+)\s+i\s+([\w-]+)\s+po\s+zmianie\b", re.IGNORECASE
)
_STOCK_RECAP = re.compile(
    r"\b(?:obydwu|obu)\s+rodzajów\b|\bpodaj\s+(?:osobno|aktualną\s+liczbę\s+dla)\b",
    re.IGNORECASE,
)
_NUMBER_ONLY = re.compile(
    r"(?:podaj|zwróć|napisz)\s+(?:(?:samą|tylko)\s+)?liczbę", re.IGNORECASE
)
_UPDATED_LOCATION = re.compile(
    r"\bw\s+tej\s+(?:jednej\s+)?lokalizacji\b", re.IGNORECASE
)
_UNITLESS_RESULT = re.compile(
    r"\bbez\s+jednost(?:ki|ek)\b|\b(?:podaj|zwróć|napisz)\s+(?:tylko\s+|samą\s+)liczbę\b",
    re.IGNORECASE,
)


def requests_unitless_result(message: str) -> bool:
    """Distinguish a presentation request from the type of the source quantity."""
    return bool(_UNITLESS_RESULT.search(message))


@dataclass(frozen=True)
class _StockValue:
    label: str
    value: Decimal
    expression: str


def _stock_key(label: str, unit: str) -> str:
    norm = _normal(label)
    if unit:
        # Polish locative/genitive forms of containers (szafce, szafki).
        return re.sub(r"(?:ce|ki)$", "k", norm)
    return re.sub(r"(?:ych|ich|e|y)$", "", norm)


def _stock_number(number: str, scale: str, unit: str) -> str:
    amount = Decimal(number.replace(",", "."))
    if (scale, unit) in {("l", "ml"), ("kg", "g")}:
        amount = amount.scaleb(3)
    return format(amount, "f")


def _stock_snapshot(
    message: str,
) -> tuple[str, str, dict[str, _StockValue]] | None:
    volume = _STOCK_VOLUME.fullmatch(message)
    count = _STOCK_COUNT.fullmatch(message)
    categories = _CATEGORY_ANCHOR.fullmatch(message)
    if volume:
        parts = re.split(r",\s+(?=[0-9])|\s+i\s+", volume[1])
        amounts = [_VOLUME_ITEM.fullmatch(part) for part in parts]
        if len(amounts) < 2 or not all(amounts):
            return None
        rows = [(m[1], m[2].lower(), m[3]) for m in amounts if m]
        units = {_QUANTITY_UNITS[scale] for _, scale, _ in rows}
        if len(units) != 1:
            return None
        unit, noun = units.pop(), ""
    elif count:
        rows = [(count[1], "", count[3]), (count[4], "", count[5])]
        unit, noun = "", count[2].lower()
    elif categories:
        parts = re.split(r"\s*,\s*|\s+i\s+", categories[1])
        counts = [_CATEGORY_ITEM.fullmatch(part) for part in parts]
        if len(counts) < 2 or not all(counts):
            return None
        rows = [(m[2], "", m[1]) for m in counts if m]
        unit = noun = ""
    else:
        return None
    values = {}
    for amount, scale, label in rows:
        number = _stock_number(amount, scale, unit)
        value = Decimal(number)
        if value < 0:
            return None
        values[_stock_key(label, unit)] = _StockValue(label, value, number)
    if len(values) != len(rows):
        return None
    return unit, noun, values


def _stock_update(message: str, unit: str) -> tuple[str, str, str] | None:
    if unit:
        assignment = _VOLUME_SET.fullmatch(message) or _REGISTER_SET.fullmatch(message)
        if assignment and _QUANTITY_UNITS[assignment[3].lower()] == unit:
            return (
                assignment[1],
                "set",
                _stock_number(assignment[2], assignment[3].lower(), unit),
            )
        delta = _VOLUME_DELTA.fullmatch(message)
        if delta and _QUANTITY_UNITS[delta[4].lower()] == unit:
            op = "+" if delta[2].lower() in {"dolano", "dodano"} else "-"
            return delta[1], op, _stock_number(delta[3], delta[4].lower(), unit)
    else:
        assignment = _COUNT_SET.fullmatch(message) or _CATEGORY_SET.fullmatch(message)
        if assignment:
            return assignment[1], "set", assignment[2]
        if addition := _CATEGORY_ADD.fullmatch(message):
            return addition[1], "+", addition[2]
        if removal := _CATEGORY_REMOVE.fullmatch(message):
            return removal[1], "-", removal[2]
        if match := _COUNT_DELTA.fullmatch(message):
            op = "+" if message.lower().startswith(("dodano", "przyjęto")) else "-"
            return match[2], op, str(_headcount(match[1]))
    return None


def _stock_calculation(
    messages: tuple[str, ...], *, allow_listing: bool = False
) -> tuple[Calculation, str, tuple[_StockValue, ...]] | None:
    unit = noun = ""
    snapshots: list[dict[str, _StockValue]] = []
    query = updated_key = ""
    for message in messages:
        query = updated_key = ""
        for clause in re.split(r"[.!?](?:\s+|$)|[;\n]+", message):
            clause = clause.strip()
            if not clause:
                continue
            if query and _NUMBER_ONLY.fullmatch(clause):
                query += f" {clause}"
                continue
            query = clause if _STOCK_QUERY.search(clause) else ""
            anchor = _stock_snapshot(clause)
            if anchor:
                unit, noun, initial = anchor
                snapshots = [initial]
                continue
            if not snapshots and not _STOCK_QUERY.search(clause):
                continue
            if len(snapshots) > 1 and _STOCK_UNDO.fullmatch(clause):
                snapshots.pop()
                continue
            update = _stock_update(clause, unit) if snapshots else None
            if update is None:
                # Unknown transitions are never carried into a later calculation.
                if clause and not _STOCK_QUERY.search(clause):
                    snapshots.clear()
                continue
            label, op, raw = update
            key = _stock_key(label, unit)
            last = snapshots[-1].get(key)
            if last is None:
                snapshots.clear()
                continue
            amount = Decimal(raw)
            if amount < 0:
                snapshots.clear()
                continue
            updated_key = key
            if op == "set":
                number, expression = amount, raw
            else:
                number = last.value + amount if op == "+" else last.value - amount
                expression = f"({last.expression}){op}{raw}"
            if number < 0 or len(expression) > MAX_EXPRESSION_CHARS:
                snapshots.clear()
                continue
            snapshots.append(
                snapshots[-1] | {key: _StockValue(last.label, number, expression)}
            )
    if not snapshots or not query:
        return None
    values = snapshots[-1]
    count = _STOCK_REMAIN.search(query)
    if count:
        if _UPDATED_LOCATION.search(query):
            item = values.get(updated_key)
        else:
            label = count["location"] or count["category"]
            item = values.get(_stock_key(label, unit)) if label else None
        if item is None:
            return None
        selected = (item,)
    elif _STOCK_TOTAL.search(query):
        selected = tuple(values.values())
    elif allow_listing and (listing := _STOCK_LIST.search(query)):
        labels = {_stock_key(label, unit) for label in listing.groups()}
        if labels != values.keys():
            return None
        selected = tuple(values.values())
    else:
        return None
    omit_unit = not unit and requests_unitless_result(query)
    target = (
        ""
        if omit_unit
        else explicit_result_unit(query) or (noun if noun and noun in UNITS else unit)
    )
    if omit_unit:
        noun = ""
    if unit and target != unit and (unit, target) not in _CONVERSIONS:
        return None
    if not unit and target not in {"", noun}:
        return None
    expression = "+".join(item.expression for item in selected)
    if len(expression) > MAX_EXPRESSION_CHARS - 8:
        return None
    calculation = Calculation(
        calculation_id="stock_result",
        expression=expression,
        input_unit=unit,
        unit=target,
    )
    return _compile_calculation(calculation), noun, selected


def _stock_draft(
    calculation: CalculationEvidence,
    noun: str,
    balances: tuple[_StockValue, ...],
    *,
    number_only: bool,
) -> Draft:
    amount = calculation.value.replace(".", ",")
    unit = calculation.unit or noun
    label = f"{balances[0].label}:" if len(balances) == 1 else "Łącznie:"
    prose = f"{label} {amount}{f' {unit}' if unit else ''}."
    return Draft(
        prose=amount if number_only and not unit else prose,
        sources=[],
        calculations=[
            ResultClaim(
                calculation_id=calculation.calculation_id,
                value=calculation.value,
                unit=calculation.unit,
            )
        ],
    )


def _missing_inputs(
    missing: list[str],
    *,
    booking: bool,
    calculation_outputs: set[str],
    price_subject: str,
) -> list[str]:
    """An explicitly requested output cannot itself be a prerequisite."""
    inputs = []
    for item in missing:
        label = " ".join(item.lower().replace("_", " ").split()).rstrip(".?")
        if booking and _BOOKING_RESULT.fullmatch(label):
            continue
        if price_subject and _price_result(label, price_subject):
            continue
        if label in calculation_outputs:
            continue
        inputs.append(item)
    return inputs


class ArithmeticPlan(StrictModel):
    calculations: list[Calculation] = Field(min_length=1, max_length=MAX_CALCULATIONS)


class Plan(StrictModel):
    mode: Literal["answer", "clarify"]
    missing: list[str]
    calculations: list[Calculation]


class Quote(StrictModel):
    source_id: StrictStr
    version: StrictStr
    quote: StrictStr = Field(min_length=1, max_length=3000)


class ResultClaim(StrictModel):
    calculation_id: StrictStr
    value: StrictStr
    unit: StrictStr

    def bound_value(self) -> str:
        """Normalize a decimal spelling, preserving a mismatched unit as invalid."""
        return (
            normalize_claim(self.value, self.unit) if self.unit in UNITS else self.value
        )


def _bind_result_claim(
    claim: ResultClaim, evidence: Evidence, unit: str | None, places: int | None
) -> CalculationClaim:
    value = claim.bound_value()
    calculated = next(
        (
            item
            for item in evidence.calculations
            if item.calculation_id == claim.calculation_id
        ),
        None,
    )
    if (
        places is not None
        and unit is not None
        and claim.unit == unit
        and calculated is not None
        and calculated.unit == unit
        and re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", value)
        and Decimal(value) == Decimal(rounded_value(calculated.value, places))
    ):
        # Certify against the exact executed evidence, retaining the model's
        # original rounded claim and policy in the semantic review packet.
        value = calculated.value
    return CalculationClaim(claim.calculation_id, value, claim.unit)


class Draft(StrictModel):
    prose: StrictStr = Field(min_length=1, max_length=4000)
    sources: list[Quote] = Field(max_length=8)
    calculations: list[ResultClaim] = Field(max_length=8)


@dataclass(frozen=True)
class SemanticVerdict:
    material_sha256: str
    qualification_id: str
    approved: bool
    reason: str


class SemanticReviewer(Protocol):
    """Trusted application dependency; never a property supplied by the model."""

    qualification_id: str

    def review(self, material: dict[str, Any]) -> SemanticVerdict: ...


ModelCall = Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]]


def material_hash(material: dict[str, Any]) -> str:
    return text_hash(json.dumps(material, ensure_ascii=False, sort_keys=True))


def _call(
    model: ModelCall, phase: str, data: dict[str, Any], schema: type[StrictModel]
) -> Any:
    if len(json.dumps(data, ensure_ascii=False).encode()) > MAX_MODEL_INPUT_BYTES:
        raise EvidenceError("pilot_context_limit")
    try:
        return schema.model_validate(model(phase, data, schema.model_json_schema()))
    except (ValidationError, ValueError, TypeError, OSError, TimeoutError) as exc:
        raise EvidenceError("pilot_model_invalid") from exc


def _current(backend: SourceBackend, sources: tuple[SourceDocument, ...]) -> None:
    for document in sources:
        try:
            ref = backend.current_ref(document.ref.source_id)
        except (OSError, TimeoutError, KeyError) as exc:
            raise EvidenceError("answer_source_unavailable") from exc
        if ref != document.ref:
            raise EvidenceError("answer_source_stale")


_WRAPPED_ID = re.compile(r"\(([A-Za-z0-9_:-][^()\n]{0,100})\)|\[([^\[\]\n]{1,100})\]")
_SOURCE_METADATA = re.compile(
    r"\(\s*id\s*:\s*([a-z0-9_-]+)\s*,\s*wersja\s*:\s*[a-z0-9_.-]+\s*\)", re.IGNORECASE
)
_LABELLED_ID = re.compile(
    r"(?i)\b(?:(?:evidence|calculation|qualification)[_ -]?id|"
    r"id(?: dowodu| obliczenia)?)\s*:\s*([a-z0-9_-]+)\b"
)


def _public_prose(
    prose: str, private_ids: set[str], source_versions: dict[str, str]
) -> str:
    """Remove adapter metadata before the semantic reviewer sees visible prose."""

    source_ids = set(source_versions)
    private_ids = private_ids - source_ids - UNITS

    def bare(match: re.Match[str]) -> str:
        return match[0] if match[1] in source_ids else ""

    def wrapped(match: re.Match[str]) -> str:
        content = (match[1] or match[2]).strip()
        label = _LABELLED_ID.fullmatch(content)
        if (content in private_ids and not content.isdecimal()) or (
            label and label[1] not in source_ids
        ):
            return ""
        if re.search(
            r"\b(?:przypisanie|obliczenie)\s*:", content, re.IGNORECASE
        ) and any(
            re.search(rf"(?<![\w-]){re.escape(ident)}(?![\w-])", content)
            for ident in private_ids
        ):
            return ""
        return match[0]

    def source_citation(match: re.Match[str]) -> str:
        ident = match[1]
        if ident not in source_ids:
            return match[0]
        surrounding = prose[: match.start()] + prose[match.end() :]
        return (
            ""
            if re.search(rf"(?<![\w-]){re.escape(ident)}(?![\w-])", surrounding)
            else f"[{ident}]"
        )

    cleaned = _SOURCE_METADATA.sub(source_citation, prose)
    for ident, version in sorted(source_versions.items()):
        name = re.escape(ident)
        suffix = "|".join(re.escape(part) for part in (version, *sorted(private_ids)))
        suffix = f"(?:{suffix})"
        cleaned = re.sub(
            rf"\(\s*{name}(?:\s*,\s*{suffix})?\s*\)"
            rf"|\[\s*{name}\s*,\s*{suffix}\s*\]",
            f"[{ident}]",
            cleaned,
        )
        # Metadata is stripped only where it is attached to a known public card.
        cleaned = re.sub(
            rf"(?<![\w-])({name})(?![\w-])"
            r"(?:\s*\(\s*(?:wersja|version)\s*:?\s*[a-z0-9_.-]+\s*\)"
            r"|,\s*(?:wersja|version)\s*:?\s*[a-z0-9_-]+(?:\.[a-z0-9_-]+)*\b)",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(rf"\[({name})@[a-zA-Z0-9_.-]+\]", r"[\1]", cleaned)
    cleaned = _LABELLED_ID.sub(bare, _WRAPPED_ID.sub(wrapped, cleaned))
    for ident in sorted(private_ids):
        # Bare short IDs can coincide with real words or values.
        if "_" not in ident and not re.fullmatch(r"[0-9a-f]{32,64}", ident):
            continue
        cleaned = re.sub(rf"(?<![\w-]){re.escape(ident)}(?![\w-])", "", cleaned)
    if cleaned == prose:
        return prose
    cleaned = re.sub(r"[ \t]+([.,!?])", r"\1", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def _cite_sources(prose: str, quotes: list[Quote]) -> str:
    quoted = {quote.source_id: quote.version for quote in quotes}
    missing = [
        f"[{ident}]"
        for ident, version in quoted.items()
        if not re.search(
            rf"(?<![\w-]){re.escape(ident)}(?:[-@]{re.escape(version)})?(?![\w-])",
            prose,
        )
    ]
    return f"{prose} {' '.join(missing)}" if missing else prose


_RECAP_REQUEST = re.compile(
    r"\b(?:podsumuj|przypomnij|powtórz)\b|"
    r"\b(?:sporządź|przygotuj|zrób|napisz)\b[^.!?]*\b(?:informację|notatkę|komunikat|podsumowanie)\b",
    re.IGNORECASE,
)
_DATE_EXCEPTION = re.compile(
    r"\b(?:pierwszą|ostatnią|najbliższą)\s+(?:sobotę|niedzielę|środę)|"
    r"\b(?:pierwszy|ostatni|najbliższy)\s+(?:poniedziałek|wtorek|czwartek|piątek)|"
    r"\bwyjątkowo\b",
    re.IGNORECASE,
)
_DATE_OVERRIDE = re.compile(
    r"\b(?:wróć\s+do\s+zwykł|zwykle|standardow|przekładam|przenosim|zmieniam\w*\s+termin)",
    re.IGNORECASE,
)
_BOOKING_RECAP = re.compile(
    r"\b(?:podaj|podsumuj|przekaż)\b[^.!?]*\bdzień\b[^.!?]*\b(?:liczbę|liczebność)\b"
    r"[^.!?]*\b(?:zapis\w*|rezerwacj\w*)\b",
    re.IGNORECASE,
)
_COMPARISON_RECAP = re.compile(
    r"\b(?:podaj|zestaw)\b[^.!?]*\bobie\b[^.!?]*(?:\bróżnicę\b|\bo ile\b)",
    re.IGNORECASE,
)
_OBSERVATION_REQUEST = re.compile(
    r"\bwykres\w*\b|\bpoziom\w*\s+(?:lini\w*|odcink\w*)\b", re.IGNORECASE
)
_ADDRESS_REPLACED = re.compile(
    r"\b(?:nowy|aktualny)\s+adres\s+(?:to|jest)\b", re.IGNORECASE
)
_ADDRESS_REVOKED = re.compile(
    r"\badres\b[^.!?;\n]{0,80}\b(?:odwołano|wycofano)\b|"
    r"\b(?:odwołujemy|wycofujemy)\s+adres\b",
    re.IGNORECASE,
)
_TENTATIVE_TIME = re.compile(
    r"\b(?:wstępnie|prowizorycznie)\b[^.!?;\n]{0,65}\b([0-2]?\d:[0-5]\d)\b",
    re.IGNORECASE,
)


_FINAL_REFORMULATION = re.compile(
    r"\b(?:przekaż|dopisz|streść|skróć|zapisz\s+tylko|gdyby|"
    r"do\s+(?:przeczytania|skopiowania)|aktualn\w*\s+stan\w*|"
    r"z\s+jego\s+perspektywy|które\s+liczby\s+wpisać)\b",
    re.IGNORECASE,
)
_ROUTE_REVERSAL = re.compile(
    r"\b(?:w\s+drugą\s+stronę|w\s+przeciwnym\s+kierunku)\b", re.IGNORECASE
)
_NEXT_ROUND = re.compile(r"\b(?:następnej|kolejnej)\s+rundzie\b", re.IGNORECASE)
_ROUND_ORDER = re.compile(
    r"\b(?:w\s+tej|w\s+następnej|w\s+kolejnej)\s+rundzie\b", re.IGNORECASE
)
_STATUS_RECAP = re.compile(
    r"\b(?:aktualn\w*\s+stan\w*|co\s+wiadomo|co\s+mogę\s+sprawdzić\s+później)\b",
    re.IGNORECASE,
)
_LOCATION_FALLBACK = re.compile(
    r"\b(?:gdy|jeśli)\b[^.!?]*\bnie\s+widać\b", re.IGNORECASE
)
_NOMINAL_RECAP = re.compile(r"\bnominaln\w*\s+długoś\w*", re.IGNORECASE)
_NOMINAL_LENGTH = re.compile(
    r"\b(?:odcink\w*\s+po|nominaln\w*\s+długoś\w*(?:\s+to)?)\s+"
    r"(\d+(?:[.,]\d+)?\s*(?:mm|cm|m))\b",
    re.IGNORECASE,
)


def plain_pilot_context(
    message: str, history: tuple[dict[str, str], ...]
) -> tuple[tuple[dict[str, str], ...], str]:
    """Focus an ordinary pilot turn on the selected exception or latest status."""
    recap = bool(_RECAP_REQUEST.search(message) or _BOOKING_RECAP.search(message))
    previous = [
        (i, item["content"]) for i, item in enumerate(history) if item["role"] == "user"
    ]
    guidance = []
    if previous and (
        _FINAL_REFORMULATION.search(message)
        or _NEXT_ROUND.search(message)
        or _LOCATION_FALLBACK.search(message)
    ):
        guidance.append(
            "Ułóż samodzielną odpowiedź z aktualnych ustaleń użytkownika. Ostatnia "
            "korekta zmienia tylko wskazane fakty. Zapisz potrzebne liczby wraz "
            "z etykietami i jednostkami, w tym wartość bazową wskazaną przez "
            "odesłanie do wcześniejszej tury. Zachowaj warunki, które pozostają w mocy. "
            "W pytaniu hipotetycznym osobno podaj skutek zmiany i porównaj go ze "
            "stanem bez tej zmiany, jeśli użytkownik o to pyta."
        )
        context = [prior for _, prior in previous[-3:]] + [message]
        if any(_ROUTE_REVERSAL.search(turn) for turn in context):
            guidance.append(
                "Prześledź trasę od nowego punktu startu. Przy odwróceniu kierunku "
                "pierwszy z dwóch punktów staje się drugim, a drugi pierwszym. "
                "Zachowaj położenie celu względem tego punktu. Jawnie nazwij punkt "
                "startu w gotowej odpowiedzi, używając zwrotu «licząc od ...»."
            )
            if any(_LOCATION_FALLBACK.search(turn) for turn in context):
                guidance.append(
                    "Podaj jednocześnie pełne położenie celu od nowego punktu startu "
                    "oraz instrukcję na wypadek, gdy wskazanego miejsca nie widać. "
                    "Przy prośbie o dwa zdania pierwsze przeznacz na pełną lokalizację, "
                    "a drugie na warunek i instrukcję awaryjną."
                )
        if any(_ROUND_ORDER.search(turn) for turn in context):
            guidance.append(
                "Wypisz osobno, kto zaczyna obecną rundę, i kto zaczyna następną. "
                "Zwrot «w tej dalej» utrzymuje osobę ustaloną dla obecnej rundy. "
                "Zachowaj reguły wspólne dla obu rund. Jeśli użytkownik chce określonej "
                "liczby punktów, zmieść obie role i wszystkie wspólne ograniczenia w "
                "tych punktach, bez osobnego dopisku. Obowiązuje ostatnia reguła "
                "kolejności uczestników. Jeśli gesty mają następować kolejno, pomiń "
                "pomysł jednoczesnych ruchów w każdym punkcie i w opisie zabawy. "
                "Gdy dla którejś rundy nie ustalono rozpoczynającego, nie dopisuj go."
            )
        if _NOMINAL_RECAP.search(message):
            for turn in reversed(context):
                nominal = _NOMINAL_LENGTH.search(turn)
                if nominal:
                    guidance.append(
                        f"W odpowiedzi wpisz podaną długość nominalną {nominal[1]} "
                        "przy odcinkach, których długość pozostała bez zmiany."
                    )
                    break
        if _STATUS_RECAP.search(message):
            guidance.append(
                "Oddziel potwierdzone zdarzenia od tego, co dopiero można sprawdzić. "
                "Jeżeli wiadomo tylko, że nadano numer zgłoszenia, napisz, że zgłoszenie "
                "przyjęto, używając sformułowania «sam numer nie potwierdza wyboru». "
                "Stan faktycznej decyzji jest nieznany. Unikaj twierdzeń «wybór nie "
                "został jeszcze potwierdzony», «oczekuje na weryfikację» lub "
                "«weryfikacja trwa». Wymień wskazany dokument i osobę kontaktową, "
                "gdy pytanie dotyczy późniejszego sprawdzenia."
            )
    if _BOOKING_RECAP.search(message):
        guidance.append(
            "Podaj dzień, liczebność i obowiązek zapisu. Weź dzień i liczbę z ostatniej "
            "zmiany użytkownika. Dla tej wizyty przenieś rozstrzygnięcie z najnowszego "
            "odczytu karty. Wcześniejszy limit dla innego dnia nie zastępuje późniejszego wyjątku."
        )
    if _COMPARISON_RECAP.search(message):
        guidance.append(
            "Podaj obie osobne wartości z poprzednich odpowiedzi, zachowaj ich etykiety "
            "i jednostki oraz podaj różnicę, jeśli obie wartości zostały potwierdzone."
        )
    if _OBSERVATION_REQUEST.search(message):
        guidance.append(
            "Podaj dokładny odczyt. Jeśli pytanie porównuje dwie podane wartości, "
            "wymień obie i wyjaśnij, co oznacza każda z nich. Gdy pytanie dotyczy tego, "
            "czy wykres czegoś dowodzi, odpowiedz wprost i wskaż granicę wniosku. "
            "Wykres jednej wielkości nie wykazuje przebiegu zjawisk, których nie mierzy."
        )
    if (recap or _ONE_SENTENCE_RECAP.search(message)) and any(
        _OBSERVATION_REQUEST.search(prior) for _, prior in previous[-2:]
    ):
        guidance.append(
            "Rozróżnij stałość mierzonej wielkości od tego, co działo się w grupie lub "
            "między pomiarami. W podsumowaniu zachowaj czynności, których dotyczył wniosek. "
            "Jeśli chodziło o wejścia i wyjścia, zachowaj oba zamiast zamieniać je na "
            "ogólny ruch wewnątrz obiektu."
        )
    if recap and not _DATE_OVERRIDE.search(message):
        for index, prior in reversed(previous[-2:]):
            if _DATE_OVERRIDE.search(prior):
                break
            if _DATE_EXCEPTION.search(prior):
                history = history[index:]
                guidance.append(
                    "Użytkownik wybrał wyjątek od zwykłego terminu. Podsumuj wyłącznie "
                    "ten wybrany termin i jego ustalenia. Godzinę przypisz do czynności "
                    "podanej w rozmowie lub karcie. Godzina otwarcia lub odjazdu nie oznacza "
                    "godziny zbiórki bez wyraźnego potwierdzenia."
                )
                break
    latest = previous[-1][1] if recap and previous else ""
    if _ADDRESS_REVOKED.search(message) or _TENTATIVE_TIME.search(message):
        latest = message
    revoked = _ADDRESS_REVOKED.search(latest)
    if revoked and not _ADDRESS_REPLACED.search(latest, revoked.end()):
        guidance.append(
            "Ostatni podany adres został wycofany. Wprost wskaż, że aktualny adres "
            "wymaga potwierdzenia. Nie podawaj wycofanego adresu jako miejsca spotkania."
        )
    tentative = _TENTATIVE_TIME.search(latest)
    if tentative:
        guidance.append(
            f"Godzina {tentative[1]} jest wstępna i wymaga potwierdzenia. "
            "Tak opisz ją w odpowiedzi, zachowując już ustalony dzień."
        )
    return history, " ".join(guidance)


_ONE_SENTENCE_RECAP = re.compile(
    r"\b(?:jednozdaniow\w*|w\s+jednym\s+zdaniu)\b", re.IGNORECASE
)
_GATHERING_DETAILS = re.compile(
    r"\b(?:godzinami|godziny)\b[^.!?]*\b(?:miejscem|miejsce)\s+zbiórki\b", re.IGNORECASE
)
_CLOCK_VALUE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b")
_GATHERING_PLACE = re.compile(
    r"zbiórka\s+(?:tego dnia\s+)?(?:odbywa się|jest|będzie)\s+(?:przy|w|we|na|obok|przed|za)\s+[^0-9.!?\n]+",
    re.IGNORECASE,
)
_PUBLIC_CARD_AT_END = re.compile(r"\s*(\[[A-Za-z][\w-]{0,63}\])\.?\s*$")


_DAYS = {
    "poniedziałek": "poniedziałek",
    "wtorek": "wtorek",
    "środę": "środa",
    "środa": "środa",
    "czwartek": "czwartek",
    "piątek": "piątek",
    "sobotę": "sobota",
    "sobota": "sobota",
    "niedzielę": "niedziela",
    "niedziela": "niedziela",
}
_GROUP_COUNTS = _COUNT_WORDS | {
    "jednej": 1,
    "dwóch": 2,
    "trzech": 3,
    "czterech": 4,
    "pięciu": 5,
    "sześciu": 6,
    "siedmiu": 7,
    "ośmiu": 8,
    "dziewięciu": 9,
    "dziesięciu": 10,
}
_WEEKDAY = re.compile(rf"\b(?:{'|'.join(_DAYS)})\b", re.IGNORECASE)
_GROUP_SIZE = re.compile(
    rf"\b([0-9]{{1,4}}|{'|'.join(_GROUP_COUNTS)})\s+os(?:ób|ob[ayę])\b", re.IGNORECASE
)
_BOOKING_REQUIRED = re.compile(
    r"\b(?:obowiązuje\s+zapis|musz(?:ą|ę)\s+się\s+zapisać|zapis\s+(?:jest\s+)?"
    r"(?:wymagany|potrzebny|obowiązkowy))\b",
    re.IGNORECASE,
)
_BOOKING_OPTIONAL = re.compile(
    r"\b(?:nie\s+(?:obowiązuje\s+zapis|musz(?:ą|ę)\s+się\s+zapisać|ma\s+obowiązku\s+zapisu)"
    r"|zapis\s+(?:nie\s+(?:obowiązuje|jest\s+(?:wymagany|potrzebny|obowiązkowy))|niewymagany|dobrowolny)"
    r"|bez\s+zapisu)\b",
    re.IGNORECASE,
)


def _plain_booking_recap(history: tuple[dict[str, str], ...]) -> str | None:
    if tuple(row["role"] for row in history[-2:]) != ("user", "assistant"):
        return None
    update, result = (row["content"] for row in history[-2:])
    days = {_DAYS[match.casefold()] for match in _WEEKDAY.findall(update)}
    sizes = {
        int(m) if m.isdecimal() else _GROUP_COUNTS[m.casefold()]
        for m in _GROUP_SIZE.findall(update)
    }
    if len(days) != 1 or len(sizes) != 1:
        return None
    day, size = next(iter(days)), next(iter(sizes))
    # A date may occur before or after the decision. Only attribute a clause
    # in both directions when it points to that one day.
    decisions = set()
    for clause in re.split(r"[.!?;]+\s*|,\s+(?:ale|natomiast)\s+", result):
        matches = list(_WEEKDAY.finditer(clause))
        clause_days = {_DAYS[match[0].casefold()] for match in matches}
        if clause_days == {day}:
            candidates = [clause]
        else:
            candidates = [
                _WEEKDAY.split(clause[match.end() :], maxsplit=1)[0]
                for match in matches
                if _DAYS[match[0].casefold()] == day
            ]
        for candidate in candidates:
            if _BOOKING_OPTIONAL.search(candidate):
                decisions.add(False)
            if _BOOKING_REQUIRED.search(_BOOKING_OPTIONAL.sub("", candidate)):
                decisions.add(True)
    if len(decisions) != 1:
        return None
    required = decisions.pop()
    noun = (
        "osoba"
        if size == 1
        else "osoby"
        if size % 10 in (2, 3, 4) and size % 100 not in (12, 13, 14)
        else "osób"
    )
    return f"{day.capitalize()}, {size} {noun}, zapis {'obowiązkowy' if required else 'niewymagany'}."


_ROOM = re.compile(r"(?i:\b(?:sala|sali|salę)\s+)([A-ZĄĆĘŁŃÓŚŹŻ][\w-]*)")
_HOST = re.compile(r"(?i:\b(?:prowadzi|zastąpi\s+(?:go|ją))\s+)([A-ZĄĆĘŁŃÓŚŹŻ][\w-]*)")
_SCHEDULE_EVENT = re.compile(
    r"\b(?:dopisz|zanotuj|zapisz|ustal)\b[^.!?:]*?\b(prób[ęa]|odpraw[ęa]|spotkanie)\s*:",
    re.IGNORECASE,
)
_SCHEDULE_EDIT = re.compile(
    r"\b(?:przenosimy|przekładamy|zmieniamy|zastąpi\s+(?:go|ją)|godzina bez zmian)\b",
    re.IGNORECASE,
)
_RELATIVE_OPENING = re.compile(
    r"\botwarcie\s+(?:sali\s+)?(?:będzie\s+)?(?:(kwadrans)|(\d{1,2})\s+minut(?:ę|y)?)\s+wcześniej\b",
    re.IGNORECASE,
)


def _plain_schedule_recap(
    message: str, history: tuple[dict[str, str], ...]
) -> str | None:
    if not _RECAP_REQUEST.search(message):
        return None
    facts: dict[str, str] = {}
    opening_offset: int | None = None
    for turn in (
        *[item["content"] for item in history if item["role"] == "user"],
        message,
    ):
        anchor = _SCHEDULE_EVENT.search(turn)
        opening = _RELATIVE_OPENING.search(turn)
        amendment = _SCHEDULE_EDIT.search(turn)
        if anchor:
            event = {"próbę": "próba", "odprawę": "odprawa"}.get(
                anchor[1].casefold(), anchor[1].casefold()
            )
            facts = {"event": event}
            opening_offset = None
        elif not facts:
            continue
        elif not (amendment or opening or _RECAP_REQUEST.search(turn)):
            # Do not infer what an unrecognized update meant.
            return None
        if opening:
            opening_offset = 15 if opening[1] else int(opening[2])
        if anchor or amendment or opening:
            fields = {
                "day": {_DAYS[day.casefold()] for day in _WEEKDAY.findall(turn)},
                "time": set(_CLOCK_VALUE.findall(turn)),
                "room": set(_ROOM.findall(turn)),
                "host": set(_HOST.findall(turn)),
            }
            if any(len(values) > 1 for values in fields.values()):
                return None
            for field, values in fields.items():
                if values:
                    facts[field] = values.pop()
    keys = {"event", "day", "time", "room", "host"}
    if opening_offset is None or set(facts) != keys:
        return None
    hours, minutes = (int(value) for value in facts["time"].split(":"))
    start = hours * 60 + minutes - opening_offset
    if start < 0:
        return None
    opening_time = f"{start // 60:02d}:{start % 60:02d}"
    return (
        f"{facts['day'].capitalize()}, sala {facts['room']}, otwarcie o {opening_time}, "
        f"{facts['event']} o {facts['time']}; prowadzi {facts['host']}."
    )


def _plain_stock_recap(message: str, history: tuple[dict[str, str], ...]) -> str | None:
    if not (_STOCK_RECAP.search(message) or _STOCK_LIST.search(message)):
        return None
    user_turns = tuple(turn["content"] for turn in history if turn["role"] == "user")
    if explicit_result_unit(message):
        return None
    stock = _stock_calculation((*user_turns, message), allow_listing=True)
    if stock is None or len(stock[2]) < 2:
        return None
    calculation, noun, balances = stock
    unit = f" {calculation.unit}" if not noun and calculation.unit else ""
    if noun:
        parts = ", ".join(f"{item.value:f} {item.label}" for item in balances)
    else:
        parts = ", ".join(f"{item.label}: {item.value:f}{unit}" for item in balances)
    parts = parts.replace(".", ",")
    if _STOCK_TOTAL.search(message):
        total = format(sum(item.value for item in balances), "f").replace(".", ",")
        parts += f", razem {total}{unit}"
    return f"{parts}."


_ORDER_INITIAL = re.compile(
    r"na\s+podstawie\s+(?P<card>[\w.-]{1,64})\s+oblicz\s+koszt\s+zamówienia\s+"
    r"„(?P<product>[^”\n]+)”:\s*(?P<quantity>[0-9]{1,6})\s+sztuk(?:i|ę)?\s+i\s+"
    r"opcj(?:a|ę)\s*„(?P<option>[^”\n]+)”[.]?",
    re.IGNORECASE,
)
_ORDER_SWITCH = re.compile(
    r"dla\s+zamówienia\s+„(?P<product>[^”\n]+)”\s+liczba\s+sztuk\s+zostaje[.]\s*"
    r"teraz\s+wybieram\s+„(?P<option>[^”\n]+)”[.]\s*oblicz\s+nową\s+kwotę\s+"
    r"z\s+(?P<card>[\w.-]{0,63}\w)[.]?",
    re.IGNORECASE,
)
_TARIFF_PRICE = re.compile(
    rf"cena\s+jednej\s+sztuki:\s+(.+?)\s+kosztuje\s+({_STATE_NUMBER})\s+zł[.]",
    re.IGNORECASE,
)
_TARIFF_DISCOUNT = re.compile(
    rf"przy\s+zakupie\s+od\s+([0-9]{{1,6}})\s+sztuk\s+rabat\s+to\s+"
    rf"({_STATE_NUMBER})\s+zł\s+za\s+każdą\s+sztukę[.]",
    re.IGNORECASE,
)
_TARIFF_OPTION = re.compile(
    rf"opcja\s+„([^”\n]+)”\s+(?:kosztuje\s+({_STATE_NUMBER})\s+zł\s+za\s+całe\s+zamówienie|"
    r"jest\s+darmowa)[.]",
    re.IGNORECASE,
)
_ORDER_COMPARE = re.compile(
    r"\bporównaj\b[^.!?\n]*\b(?:ceny|kwoty)\s+obu\s+wariantów\s+zamówienia\s+"
    r"„([^”\n]+)”[^.!?\n]*\bróżnic\w*\b",
    re.IGNORECASE,
)
_ORDER_ANSWER = re.compile(
    rf"Koszt zamówienia „([^”\n]+)” z opcją „([^”\n]+)” wynosi ({_STATE_NUMBER}) zł[.]"
    r"(?: Ta opcja jest bezpłatna[.])? \[([\w.-]{1,64})\]"
)


@dataclass(frozen=True)
class _OrderSelection:
    card: str
    product: str
    quantity: int
    option: str


@dataclass(frozen=True)
class _OrderCalculation:
    selection: _OrderSelection
    calculation: Calculation
    source: SourceDocument
    free: bool


def _order_selection(message: str, previous: tuple[str, ...]) -> _OrderSelection | None:
    selected = _ORDER_INITIAL.fullmatch(message.strip())
    if selected:
        quantity = int(selected["quantity"])
    else:
        selected = _ORDER_SWITCH.fullmatch(message.strip())
        initial = _ORDER_INITIAL.fullmatch(previous[-1].strip()) if previous else None
        if (
            not selected
            or not initial
            or any(
                _normal(selected[key]) != _normal(initial[key])
                for key in ("card", "product")
            )
        ):
            return None
        quantity = int(initial["quantity"])
    if not quantity:
        return None
    return _OrderSelection(
        selected["card"], selected["product"], quantity, selected["option"]
    )


def _order_calculation(
    message: str, previous: tuple[str, ...], documents: tuple[SourceDocument, ...]
) -> _OrderCalculation | None:
    selection = _order_selection(message, previous)
    if not selection or len(documents) != 1:
        return None
    source = documents[0]
    if (
        source.ref.source_id != selection.card
        or source.superseded
        or not source.complete
    ):
        return None
    unit_price: str | None = None
    discount: tuple[int, str] | None = None
    fees: dict[str, str] = {}
    for sentence in re.split(r"(?<=[.])\s+", source.text.strip()):
        if price := _TARIFF_PRICE.fullmatch(sentence):
            if unit_price is not None or _normal(price[1]) != _normal(
                selection.product
            ):
                return None
            unit_price = price[2].replace(",", ".")
        elif rebate := _TARIFF_DISCOUNT.fullmatch(sentence):
            if discount is not None:
                return None
            discount = int(rebate[1]), rebate[2].replace(",", ".")
        elif option := _TARIFF_OPTION.fullmatch(sentence):
            key = _normal(option[1])
            if key in fees:
                return None
            fees[key] = (option[2] or "0").replace(",", ".")
        else:
            return None
    fee = fees.get(_normal(selection.option))
    if unit_price is None or discount is None or fee is None:
        return None
    threshold, rebate_amount = discount
    if (
        threshold < 1
        or not Decimal(unit_price) >= Decimal(rebate_amount) >= 0
        or Decimal(fee) < 0
    ):
        return None
    applicable_rebate = rebate_amount if selection.quantity >= threshold else "0"
    expression = f"{selection.quantity}*({unit_price}-{applicable_rebate})+{fee}"
    calculation = Calculation(
        calculation_id="order_total", expression=expression, unit="zł"
    )
    return _OrderCalculation(selection, calculation, source, Decimal(fee) == 0)


def _order_draft(calculation: CalculationEvidence, order: _OrderCalculation) -> Draft:
    result = _length_draft(calculation)
    selection, card = order.selection, order.source
    amount = calculation.value.replace(".", ",")
    prose = f"Koszt zamówienia „{selection.product}” z opcją „{selection.option}” wynosi {amount} zł."
    if order.free:
        prose += " Ta opcja jest bezpłatna."
    return result.model_copy(
        update={
            "prose": f"{prose} [{card.ref.source_id}]",
            "sources": [
                Quote(
                    source_id=card.ref.source_id,
                    version=card.ref.version,
                    quote=card.text,
                )
            ],
        }
    )


def _plain_order_comparison(
    message: str, history: tuple[dict[str, str], ...]
) -> str | None:
    comparison = _ORDER_COMPARE.search(message)
    if not comparison or tuple(turn["role"] for turn in history[-4:]) != (
        "user",
        "assistant",
        "user",
        "assistant",
    ):
        return None
    requested, priced, changed, repriced = (
        turn["content"].strip() for turn in history[-4:]
    )
    initial = _order_selection(requested, ())
    second = _order_selection(changed, (requested,))
    if not initial or not second or _normal(initial.product) != _normal(comparison[1]):
        return None
    if initial.card != second.card or initial.option == second.option:
        return None
    amounts = []
    for selection, answer in ((initial, priced), (second, repriced)):
        result = _ORDER_ANSWER.fullmatch(answer)
        if not result or (result[1], result[2], result[4]) != (
            selection.product,
            selection.option,
            selection.card,
        ):
            return None
        value = result[3].replace(",", ".")
        if Decimal(value) < 0:
            return None
        amounts.append(value)
    first_amount, second_amount = amounts
    difference = abs(Decimal(calculate(f"{first_amount}-{second_amount}")))
    first_prose = first_amount.replace(".", ",")
    second_prose = second_amount.replace(".", ",")
    delta = format(difference, "f").replace(".", ",")
    return f"„{initial.option}” kosztuje {first_prose} zł, a „{second.option}” {second_prose} zł (różnica {delta} zł)."


def _plain_map_difference(
    message: str, history: tuple[dict[str, str], ...]
) -> str | None:
    if not _MAP_DIFFERENCE.match(message):
        return None
    state = _map_measurements(
        tuple(turn["content"] for turn in history if turn["role"] == "user")
    )
    if state is None or len(state[1]) < 2:
        return None
    factor, lengths = state
    try:
        difference = Decimal(calculate(f"({lengths[-1]}-{lengths[-2]})*{factor}"))
    except CalculationError:
        return None
    if not difference:
        return "Wynik się nie zmienił."
    change = "wzrósł" if difference > 0 else "spadł"
    amount = format(abs(difference), "f").replace(".", ",")
    return f"Wynik {change} o {amount} m."


_FOUR_GAME_POINTS = re.compile(
    r"\b(?:cztery|4)\s+(?:krótkie\s+)?punkty\b", re.IGNORECASE
)
_HAND_GAME_RULES = re.compile(
    r"\btylko dłonie, bez mówienia i bez wyłaniania zwycięzcy[.!]?$",
    re.IGNORECASE,
)
_PLAYER_POSITION = r"osoba (?:siedząca )?(pośrodku|z lewej|z prawej)"
_CURRENT_ROUND = re.compile(
    rf"w tej rundzie zaczyna ({_PLAYER_POSITION})[.!]\s*"
    r"pozostali nie mogą gestykulować równocześnie[.!]?",
    re.IGNORECASE,
)
_FOLLOWING_ROUND = re.compile(
    rf"w (?:następnej|kolejnej) rundzie zaczyna ({_PLAYER_POSITION})[.!]\s*"
    r"w tej dalej (środkowa|lewa|prawa)[.!]?",
    re.IGNORECASE,
)
_POSITION_SHORT = {"pośrodku": "środkowa", "z lewej": "lewa", "z prawej": "prawa"}


def _plain_round_recap(message: str, history: tuple[dict[str, str], ...]) -> str | None:
    """Render four points when all game rules and both start positions are explicit."""
    users = [turn["content"] for turn in history if turn["role"] == "user"]
    if (
        len(users) != 3
        or not _FOUR_GAME_POINTS.search(message)
        or not _HAND_GAME_RULES.search(users[0])
    ):
        return None
    current = _CURRENT_ROUND.fullmatch(users[1].strip())
    following = _FOLLOWING_ROUND.fullmatch(users[2].strip())
    if not current or not following:
        return None
    if _POSITION_SHORT[current[2].lower()] != following[3].lower():
        return None
    return (
        f"1. Obecną rundę zaczyna {current[1].lower()}.\n"
        f"2. Następną rundę zaczyna {following[1].lower()}.\n"
        "3. Pokazujcie gesty tylko dłońmi, po jednej osobie naraz.\n"
        "4. Grajcie bez mówienia i bez wyłaniania zwycięzcy."
    )


def plain_pilot_recap(message: str, focused: tuple[dict[str, str], ...]) -> str | None:
    """Retain verified decisions and event roles from the selected exception."""
    if _BOOKING_RECAP.search(message):
        return _plain_booking_recap(focused)
    contextual = (
        _plain_schedule_recap(message, focused)
        or _plain_stock_recap(message, focused)
        or _plain_map_difference(message, focused)
        or _plain_order_comparison(message, focused)
        or _plain_round_recap(message, focused)
    )
    if contextual:
        return contextual
    if not (_ONE_SENTENCE_RECAP.search(message) and _GATHERING_DETAILS.search(message)):
        return None
    if tuple(turn["role"] for turn in focused) != (
        "user",
        "assistant",
        "user",
        "assistant",
    ):
        return None
    if not _DATE_EXCEPTION.search(focused[0]["content"]):
        return None
    schedule, gathering = (focused[i]["content"].strip() for i in (1, 3))
    citation_matches = (
        _PUBLIC_CARD_AT_END.search(schedule),
        _PUBLIC_CARD_AT_END.search(gathering),
    )
    schedule = _PUBLIC_CARD_AT_END.sub("", schedule).rstrip(". ")
    gathering = _PUBLIC_CARD_AT_END.sub("", gathering).rstrip(". ")
    all_times = set(_CLOCK_VALUE.findall(schedule))
    # Keep an intact sentence covering all times. Later repetition of the same
    # times can be omitted. Additional hours make this rendering ambiguous.
    first_sentence = re.split(r"[.!?\n]", schedule, maxsplit=1)[0].strip()
    if (
        len(all_times) != 2
        or set(_CLOCK_VALUE.findall(first_sentence)) != all_times
        or not _GATHERING_PLACE.fullmatch(gathering)
    ):
        return None
    schedule = first_sentence
    citations = " ".join(dict.fromkeys(match[1] for match in citation_matches if match))
    result = f"{schedule}, a {gathering[0].lower()}{gathering[1:]}."
    return f"{result} {citations}" if citations else result


def run_pilot_turn(
    message: str,
    revision: str,
    backend: SourceBackend,
    model: ModelCall,
    reviewer: SemanticReviewer,
    *,
    history: tuple[dict[str, str], ...] = (),
    required: Requirements = Requirements(),
    trace: list[dict[str, Any]] | None = None,
) -> PublishedAnswer:
    """No gold labels, hidden formula or unreviewed prose enters this boundary.

    The trace is a private diagnostic sink, never a streaming user response.
    Only the caller selects tools for this turn. Source updates during planning/review
    invalidate the answer. A clarification also requires semantic approval.
    """
    audit = trace if trace is not None else []
    if not (required.sources or required.calculation):
        raise EvidenceError("pilot_tools_not_enabled")
    qualification = reviewer.qualification_id
    if not isinstance(qualification, str) or not qualification.strip():
        raise EvidenceError("pilot_reviewer_unqualified")
    if not message.strip() or not revision.strip():
        raise EvidenceError("turn_identity_required")
    if any(
        set(h) != {"role", "content"}
        or h["role"] not in {"user", "assistant"}
        or not isinstance(h["content"], str)
        for h in history
    ):
        raise EvidenceError("pilot_history_invalid")
    prior_users = tuple(h["content"] for h in history if h["role"] == "user")
    request = {"message": message, "revision": revision, "history": list(history)}
    query = ""
    gate = GroundedTurn(backend)
    documents: tuple[SourceDocument, ...] = ()
    unavailable: tuple[str, ...] = ()
    if required.sources:
        if requested_card_ids(message):
            query = message
        else:
            selection: SourceQuery = _call(model, "source_query", request, SourceQuery)
            query = selection.source_query.strip() or message
        audit.append({"phase": "source_query", "data": {"source_query": query}})
        documents, unavailable = gate.read_sources(query, message=message)
    audit.append(
        {
            "phase": "full_read",
            "documents": [asdict(d) for d in documents],
            "unavailable": list(unavailable),
        }
    )
    model_sources = [
        asdict(d) | {"ref": {"source_id": d.ref.source_id, "version": d.ref.version}}
        for d in documents
    ]
    planning = {
        "revision": revision,
        "history": [h for h in history if h["role"] == "user"],
        "requirements": asdict(required),
        "sources": model_sources,
        "unavailable": list(unavailable),
        "message": message,
    }
    group = (
        _group_change(message, prior_users)
        if required.sources and documents and prior_users
        else None
    )
    speed = (
        _SPEED_CONVERSION.search(message) or _SPEED_REQUEST.search(message)
        if required.calculation
        else None
    )
    speed_unit = speed[1].lower() if speed else None
    resolved: dict[str, Any] = {}
    if group is not None:
        resolved["group_size"] = group
    if speed_unit is not None:
        resolved["requested_speed_unit"] = speed_unit
    planning.update(resolved)
    stock = (
        _stock_calculation((*prior_users, message))
        if required.calculation and not required.sources
        else None
    )
    order = (
        _order_calculation(message, prior_users, documents)
        if required.calculation and required.sources
        else None
    )
    explicit = (
        order.calculation
        if order
        else (
            _explicit_mean(message)
            or _explicit_length_conversion(message)
            or (stock[0] if stock else None)
            or _context_calculation(message, prior_users)
            if required.calculation and not required.sources
            else None
        )
    )
    source_draft = None
    if required.sources and not required.calculation:
        if meeting := requested_meeting_place(message, documents):
            source_draft = Draft(
                prose=f"{meeting.quote} [{meeting.source_id}]",
                sources=[Quote(**asdict(meeting))],
                calculations=[],
            )
        elif pickups := requested_pickup_details(message, documents):
            source_draft = Draft(
                prose=" ".join(
                    f"„{entry.item}” — punkt {entry.point} do {entry.until}. [{entry.quote.source_id}]"
                    for entry in pickups
                ),
                sources=[Quote(**asdict(entry.quote)) for entry in pickups],
                calculations=[],
            )
    assessment: InputAssessment = (
        InputAssessment(
            current_state="Składniki pochodzą z jawnych danych i aktualizacji użytkownika.",
            missing=[],
        )
        if explicit is not None or source_draft is not None
        else _call(model, "assess", planning, InputAssessment)
    )
    audit.append({"phase": "assess", "data": assessment.model_dump()})
    planning["current_state"] = assessment.current_state
    price = (
        _PRICE_QUESTION.search(message)
        if documents and not required.calculation
        else None
    )
    missing = _missing_inputs(
        assessment.missing,
        booking=group is not None and _BOOKING_QUESTION.search(message) is not None,
        calculation_outputs=_calculation_outputs(message, speed_unit)
        if required.calculation
        else set(),
        price_subject=" ".join(price[1].lower().split()) if price else "",
    )
    if required.sources and not required.calculation and documents:
        missing = _source_location_inputs(message, missing)
    if missing and required.sources and not required.calculation and documents:
        # A complete card may resolve the question, including a fact it explicitly
        # leaves unspecified. Check which reported inputs can only come from the user.
        source_inputs: MissingInputs = _call(
            model,
            "source_inputs",
            {
                "reported_missing": missing,
                "prior_users": prior_users,
                "sources": model_sources,
                "request": message,
            },
            MissingInputs,
        )
        if not set(source_inputs.missing) <= set(missing):
            raise EvidenceError("pilot_source_input_unlisted")
        missing = source_inputs.missing
        audit.append({"phase": "source_inputs", "data": source_inputs.model_dump()})
    if resolved or missing != assessment.missing:
        audit.append(
            {"phase": "resolved_inputs", "data": resolved | {"missing": missing}}
        )
    result_unit = explicit_result_unit(message) if required.calculation else None
    if result_unit is None and explicit is not None:
        result_unit = explicit.unit or None
    try:
        places = requested_precision(message) if required.calculation else None
    except ValueError as exc:
        raise EvidenceError(str(exc)) from exc
    if places is not None:
        if result_unit is None:
            raise EvidenceError("answer_precision_unit_required")
        resolved["result_precision"] = {
            "decimal_places": places,
            "rounding": ROUNDING_MODE,
            "unit": result_unit,
        }
        planning.update(resolved)
    calculations = []
    if explicit is not None:
        calculations = [explicit]
        audit.append({"phase": "explicit_arithmetic", "data": explicit.model_dump()})
    elif required.calculation and not missing:
        planning["calculation_contract"] = {
            "input_unit": "Jednostka CAŁEGO wyrażenia przed konwersją; puste gdy nie ma konwersji.",
            "percentage": "Dla udziału użyj (część/całość)*100. Wyrażenie ma już jednostkę %: unit=% i input_unit=% albo puste. Nie przeliczaj punktów lub sztuk na procenty.",
        }
        arithmetic: ArithmeticPlan = _call(model, "plan", planning, ArithmeticPlan)
        audit.append({"phase": "arithmetic", "data": arithmetic.model_dump()})
        calculations = [_compile_calculation(c) for c in arithmetic.calculations]
        conversion = _SPEED_CONVERSION.search(message)
        if (
            conversion
            and len(calculations) == 1
            and result_unit == conversion[1].lower()
        ):
            original = calculations[0]
            if result_unit is not None and (original.unit, result_unit) in _CONVERSIONS:
                calculations[0] = _compile_calculation(
                    original.model_copy(
                        update={"input_unit": original.unit, "unit": result_unit}
                    )
                )
                audit.append(
                    {
                        "phase": "explicit_speed_conversion",
                        "data": calculations[0].model_dump(),
                    }
                )
    plan = Plan(
        mode="clarify" if missing else "answer",
        missing=missing,
        calculations=calculations,
    )
    plan_data = plan.model_dump()
    audit.append({"phase": "plan", "data": plan_data})
    compiled_explicit = None
    if plan.mode == "clarify":
        evidence_id = material_hash(planning | {"plan": plan_data})
        evidence_data: dict[str, Any] = {
            "evidence_id": evidence_id,
            "sources": [asdict(d) for d in documents],
            "calculations": [],
            "unavailable": list(unavailable),
        }
    else:
        final_plan = TurnPlan(
            message,
            revision,
            prior_users,
            query,
            tuple(
                CalculationPlan(c.calculation_id, c.expression, c.unit)
                for c in plan.calculations
            ),
            required,
        )
        evidence = gate.prepare(
            final_plan, infer_requirements=False, required_result_unit=result_unit
        )
        if evidence.sources != documents or evidence.unavailable != unavailable:
            raise EvidenceError("pilot_evidence_changed_during_plan")
        evidence_id = evidence.evidence_id
        evidence_data = asdict(evidence)
        if explicit is not None:
            compiled_explicit = evidence.calculations[0]
    audit.append({"phase": "evidence", "data": evidence_data})
    # The receipt key belongs to the adapter, not the generator or its answer.
    review_evidence = {k: v for k, v in evidence_data.items() if k != "evidence_id"}
    review_evidence["sources"] = model_sources
    draft_input = (
        request
        | resolved
        | {
            "history": planning["history"],
            "current_state": assessment.current_state,
            "plan": plan_data,
            "evidence": review_evidence,
        }
    )
    if source_draft is not None:
        draft = source_draft
    elif compiled_explicit is None:
        draft = _call(model, "draft", draft_input, Draft)
    elif order is not None:
        draft = _order_draft(compiled_explicit, order)
    elif compiled_explicit.calculation_id in {
        "length_conversion",
        "average_speed",
        "volume_remainder",
        "scaled_length",
    }:
        draft = _length_draft(compiled_explicit)
    elif stock is not None:
        draft = _stock_draft(
            compiled_explicit,
            stock[1],
            stock[2],
            number_only=requests_unitless_result(message),
        )
    else:
        draft = _mean_draft(compiled_explicit)
    prose = _public_prose(
        draft.prose,
        {evidence_id, revision, *(c.calculation_id for c in plan.calculations)},
        {doc.ref.source_id: doc.ref.version for doc in documents},
    )
    prose = strip_public_bookkeeping(
        prose, {doc.ref.source_id: doc.ref.version for doc in documents}
    )
    if prose != draft.prose:
        draft = draft.model_copy(update={"prose": prose})
        audit.append({"phase": "technical_ids_removed"})
    draft_audit = {"phase": "draft", "data": draft.model_dump()}
    audit.append(draft_audit)
    if not draft.prose.strip():
        raise EvidenceError("answer_empty")
    if plan.mode == "clarify":
        if draft.sources or draft.calculations:
            raise EvidenceError("pilot_clarification_claims")
    else:
        # Keep the original deterministic contract: arbitrary prose cannot bypass it.
        quotes = tuple(
            SourceQuote(q.source_id, q.version, q.quote) for q in draft.sources
        )
        bound_quotes = (
            bind_source_quotes(draft.prose, evidence, quotes)
            if required.sources
            else quotes
        )
        if bound_quotes != quotes:
            draft = draft.model_copy(
                update={"sources": [Quote(**asdict(quote)) for quote in bound_quotes]}
            )
            draft_audit["data"] = draft.model_dump()
        claims = bound_quotes + tuple(
            _bind_result_claim(c, evidence, result_unit, places)
            for c in draft.calculations
        )
        gate.publish(AnswerDraft(evidence_id, claims))
        if result_unit is not None:
            verify_result_prose(
                draft.prose, evidence, result_unit, decimal_places=places
            )
        cited = _cite_sources(draft.prose, draft.sources)
        if cited != draft.prose:
            draft = draft.model_copy(update={"prose": cited})
            audit.append({"phase": "public_citations_added"})
            draft_audit["data"] = draft.model_dump()
    _current(backend, documents)
    material = request | {
        "requirements": asdict(required),
        **(
            {"result_precision": resolved["result_precision"]}
            if places is not None
            else {}
        ),
        "plan": plan_data,
        "evidence": review_evidence,
        "draft": draft.model_dump(),
    }
    try:
        verdict = reviewer.review(material)
    except (ValueError, OSError, TimeoutError) as exc:
        raise EvidenceError("pilot_review_failed") from exc
    if not isinstance(verdict, SemanticVerdict):
        raise EvidenceError("pilot_review_binding_invalid")
    audit.append({"phase": "semantic_review", "data": asdict(verdict)})
    if (
        verdict.material_sha256 != material_hash(material)
        or verdict.qualification_id != qualification
        or reviewer.qualification_id != qualification
        or type(verdict.approved) is not bool
        or not isinstance(verdict.reason, str)
        or not verdict.reason.strip()
    ):
        raise EvidenceError("pilot_review_binding_invalid")
    if not verdict.approved:
        raise EvidenceError("pilot_semantic_rejected")
    _current(backend, documents)
    return PublishedAnswer(evidence_id, draft.prose)
