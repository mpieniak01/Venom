"""Opt-in model pilot; full evidence and qualified semantic review before release."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Annotated, Any, Literal, Protocol

from pydantic import (
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
    CalculationPlan,
    EvidenceError,
    GroundedTurn,
    PublishedAnswer,
    Requirements,
    SourceBackend,
    SourceDocument,
    SourceQuote,
    TurnPlan,
    text_hash,
)

MAX_MODEL_INPUT_BYTES = 6000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceQuery(StrictModel):
    source_query: StrictStr = Field(max_length=500)


class InputAssessment(StrictModel):
    missing: list[Annotated[StrictStr, Field(min_length=1, max_length=160)]] = Field(
        max_length=8
    )

    @field_validator("missing")
    @classmethod
    def validate_missing(cls, missing: list[str]) -> list[str]:
        if any(not item.strip() for item in missing):
            raise ValueError("missing input must be named")
        return missing


class Calculation(StrictModel):
    calculation_id: StrictStr = Field(min_length=1, max_length=80)
    expression: StrictStr = Field(
        min_length=1, max_length=MAX_EXPRESSION_CHARS, pattern=r"^[0-9.+*/() -]+$"
    )
    unit: StrictStr = Field(json_schema_extra={"enum": [*sorted(UNITS)]})

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, unit: str) -> str:
        if unit not in UNITS:
            raise ValueError("unsupported calculator unit")
        return unit


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

    cleaned = _LABELLED_ID.sub(bare, _WRAPPED_ID.sub(wrapped, prose))
    for ident in sorted(private_ids):
        # Bare short IDs can coincide with real words or values.
        if "_" not in ident and not re.fullmatch(r"[0-9a-f]{32,64}", ident):
            continue
        cleaned = re.sub(rf"(?<![\w-]){re.escape(ident)}(?![\w-])", "", cleaned)
    if cleaned == prose:
        return prose
    cleaned = re.sub(r"[ \t]+([.,!?])", r"\1", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


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
    planning = request | {
        "requirements": asdict(required),
        "sources": model_sources,
        "unavailable": list(unavailable),
    }
    assessment: InputAssessment = _call(model, "assess", planning, InputAssessment)
    audit.append({"phase": "assess", "data": assessment.model_dump()})
    calculations = []
    if required.calculation and not assessment.missing:
        arithmetic: ArithmeticPlan = _call(model, "plan", planning, ArithmeticPlan)
        calculations = arithmetic.calculations
    plan = Plan(
        mode="clarify" if assessment.missing else "answer",
        missing=assessment.missing,
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
    audit.append({"phase": "evidence", "data": evidence_data})
    # The receipt key belongs to the adapter, not the generator or its answer.
    review_evidence = {k: v for k, v in evidence_data.items() if k != "evidence_id"}
    review_evidence["sources"] = model_sources
    draft_input = request | {"plan": plan_data, "evidence": review_evidence}
    draft: Draft = _call(model, "draft", draft_input, Draft)
    prose = _public_prose(
        draft.prose,
        {evidence_id, *(c.calculation_id for c in plan.calculations)},
        {doc.ref.source_id for doc in documents},
    )
    if prose != draft.prose:
        draft = draft.model_copy(update={"prose": prose})
        audit.append({"phase": "technical_ids_removed"})
    audit.append({"phase": "draft", "data": draft.model_dump()})
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
