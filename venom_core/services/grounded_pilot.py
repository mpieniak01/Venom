"""Opt-in model pilot; full evidence and qualified semantic review before release."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
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

from venom_core.services.grounded_calculator import MAX_EXPRESSION_CHARS
from venom_core.services.grounded_dialogue import (
    MAX_CALCULATIONS,
    UNITS,
    AnswerDraft,
    CalculationClaim,
    CalculationEvidence,
    CalculationPlan,
    EvidenceError,
    GroundedTurn,
    PublishedAnswer,
    Requirements,
    SourceBackend,
    SourceDocument,
    SourceQuote,
    TurnPlan,
    _normal,
    text_hash,
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
    input_unit: StrictStr = ""

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, unit: str) -> str:
        if unit not in UNITS:
            raise ValueError("unsupported calculator unit")
        return unit


_CONVERSIONS = {
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
    rf"(?:^\s*|[.!?]\s*|\bczy\s+|\bgrupa liczy\s+|\bgrupa\s+|\bjest nas\s+){_HEADCOUNT}",
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


def _calculation_outputs(message: str, speed_unit: str | None) -> set[str]:
    outputs = (
        {"wynik", "wynik obliczenia", "wynik rachunku"}
        if _COMPUTE_REQUEST.search(message) and not _PRIOR_RESULT.search(message)
        else set()
    )
    if speed_unit:
        outputs.update({f"prędkość {speed_unit}", f"prędkość w {speed_unit}"})
    if _REMAINDER_REQUEST.search(message):
        outputs.update({"pozostałość", "wynik pozostałości"})
    return outputs


_NUMBER = r"[+-]?[0-9]+(?:[.,][0-9]+)?"
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


def _headcount(value: str) -> int:
    return (
        int(value)
        if value.isascii() and value.isdecimal()
        else _COUNT_WORDS[value.lower()]
    )


def _group_update(message: str, previous: str) -> dict[str, int] | None:
    """Resolve an explicit addition to a single headcount in the preceding user turn."""
    joined = _JOINED.match(message)
    base = _GROUP_BASE.search(previous)
    if not joined or not base:
        return None
    if _ANY_HEADCOUNT.search(
        message[joined.end() :]
        + " "
        + previous[: base.start(1)]
        + " "
        + previous[base.end() :]
    ):
        return None
    before, added = _headcount(base[1]), _headcount(joined[1])
    return {"previous": before, "joined": added, "total": before + added}


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


def _public_prose(prose: str, private_ids: set[str], source_ids: set[str]) -> str:
    """Remove adapter metadata before the semantic reviewer sees visible prose."""

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


def plain_pilot_context(
    message: str, history: tuple[dict[str, str], ...]
) -> tuple[tuple[dict[str, str], ...], str]:
    """Focus an ordinary pilot turn on the selected exception or latest status."""
    recap = bool(_RECAP_REQUEST.search(message))
    previous = [
        (i, item["content"]) for i, item in enumerate(history) if item["role"] == "user"
    ]
    guidance = []
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
    r"zbiórka\s+(?:odbywa się|jest|będzie)\s+(?:przy|w|we|na|obok|przed|za)\s+[^0-9.!?\n]+",
    re.IGNORECASE,
)
_PUBLIC_CARD_AT_END = re.compile(r"\s*(\[[A-Za-z][\w-]{0,63}\])\.?\s*$")


def plain_pilot_recap(message: str, focused: tuple[dict[str, str], ...]) -> str | None:
    """Keep event roles by joining complete statements from the selected exception."""
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
    if (
        not re.fullmatch(r"[^.!?\n]+", schedule)
        or len(set(_CLOCK_VALUE.findall(schedule))) != 2
        or not _GATHERING_PLACE.fullmatch(gathering)
    ):
        return None
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
        selection: SourceQuery = _call(model, "source_query", request, SourceQuery)
        query = selection.source_query.strip() or message
        audit.append({"phase": "source_query", "data": {"source_query": query}})
        documents, unavailable = gate.read_sources(query)
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
        _group_update(message, prior_users[-1])
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
    mean = (
        _explicit_mean(message)
        if required.calculation and not required.sources
        else None
    )
    assessment: InputAssessment = (
        InputAssessment(
            current_state="Wszystkie składniki podano w bieżącej prośbie.", missing=[]
        )
        if mean is not None
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
    calculations = []
    compiled_mean: CalculationEvidence | None = None
    if mean is not None:
        calculations = [mean]
        audit.append({"phase": "explicit_arithmetic", "data": mean.model_dump()})
    elif required.calculation and not missing:
        arithmetic: ArithmeticPlan = _call(model, "plan", planning, ArithmeticPlan)
        audit.append({"phase": "arithmetic", "data": arithmetic.model_dump()})
        calculations = [_compile_calculation(c) for c in arithmetic.calculations]
    plan = Plan(
        mode="clarify" if missing else "answer",
        missing=missing,
        calculations=calculations,
    )
    plan_data = plan.model_dump()
    audit.append({"phase": "plan", "data": plan_data})
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
        evidence = gate.prepare(final_plan, infer_requirements=False)
        if evidence.sources != documents or evidence.unavailable != unavailable:
            raise EvidenceError("pilot_evidence_changed_during_plan")
        evidence_id = evidence.evidence_id
        evidence_data = asdict(evidence)
        if mean is not None:
            compiled_mean = evidence.calculations[0]
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
    draft: Draft = (
        _mean_draft(compiled_mean)
        if compiled_mean is not None
        else _call(model, "draft", draft_input, Draft)
    )
    prose = _public_prose(
        draft.prose,
        {evidence_id, *(c.calculation_id for c in plan.calculations)},
        {doc.ref.source_id for doc in documents},
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
        claims = tuple(
            SourceQuote(q.source_id, q.version, q.quote) for q in draft.sources
        ) + tuple(
            CalculationClaim(c.calculation_id, c.value, c.unit)
            for c in draft.calculations
        )
        gate.publish(AnswerDraft(evidence_id, claims))
        cited = _cite_sources(draft.prose, draft.sources)
        if cited != draft.prose:
            draft = draft.model_copy(update={"prose": cited})
            audit.append({"phase": "public_citations_added"})
            draft_audit["data"] = draft.model_dump()
    _current(backend, documents)
    material = request | {
        "requirements": asdict(required),
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
