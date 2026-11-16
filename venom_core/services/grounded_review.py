"""Structured semantic verification for the explicit grounded-dialogue pilot."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import Field, StrictBool, StrictStr

from venom_core.services.grounded_pilot import (
    SemanticVerdict,
    StrictModel,
    material_hash,
)


class Finding(StrictModel):
    ok: StrictBool
    reason: StrictStr = Field(min_length=1, max_length=400)


class ContextFinding(Finding):
    latest_user_quote: StrictStr = Field(min_length=1, max_length=500)


class SourceFinding(Finding):
    answer_quote: StrictStr = Field(min_length=1, max_length=500)
    source_id: StrictStr
    source_quote: StrictStr = Field(max_length=500)
    answer_role: StrictStr = Field(min_length=1, max_length=160)
    source_role: StrictStr = Field(max_length=160)
    same_role: StrictBool


class CalculationFinding(Finding):
    calculation_id: StrictStr


class GroundedReviewForm(StrictModel):
    context: ContextFinding
    source_claims: list[SourceFinding] = Field(max_length=16)
    calculations: list[CalculationFinding] = Field(max_length=8)
    answer: Finding


def checked_findings(
    raw: dict[str, Any], material: dict[str, Any]
) -> GroundedReviewForm:
    """Check receipt shape, literal grounding and complete coverage of the plan."""
    audit = GroundedReviewForm.model_validate(raw)
    if (
        not audit.context.latest_user_quote.strip()
        or audit.context.latest_user_quote not in material["message"]
    ):
        raise ValueError("review_context_quote_invalid")

    draft = material["draft"]
    evidence = material["evidence"]
    plan = material["plan"]
    documents = {doc["ref"]["source_id"]: doc["text"] for doc in evidence["sources"]}
    ids = [c.calculation_id for c in audit.calculations]
    expected = sorted(c["calculation_id"] for c in plan["calculations"])
    if (
        sorted(ids) != expected
        or sorted(c["calculation_id"] for c in evidence["calculations"]) != expected
    ):
        raise ValueError("review_calculation_coverage_invalid")

    if (
        material["requirements"]["sources"]
        and plan["mode"] == "answer"
        and audit.answer.ok
        and not audit.source_claims
    ):
        raise ValueError("review_source_coverage_missing")
    for item in audit.source_claims:
        if not item.answer_quote.strip() or item.answer_quote not in draft["prose"]:
            raise ValueError("review_answer_quote_invalid")
        if not item.answer_role.strip() or item.answer_role not in item.answer_quote:
            raise ValueError("review_answer_role_invalid")
        if item.ok or item.source_id or item.source_quote or item.source_role:
            if (
                not item.source_quote.strip()
                or item.source_id not in documents
                or item.source_quote not in documents[item.source_id]
                or not item.source_role.strip()
                or item.source_role not in item.source_quote
            ):
                raise ValueError("review_source_quote_invalid")
    return audit


class GroundedChecklistReviewer:
    """Use a qualified remote review. Approval requires every recorded finding."""

    def __init__(
        self,
        qualification_id: str,
        review_call: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self.qualification_id = qualification_id
        self.review_call = review_call

    def review(self, material: dict[str, Any]) -> SemanticVerdict:
        material_id = material_hash(material)
        audit = checked_findings(self.review_call(material), material)
        checks = [
            audit.context,
            *audit.source_claims,
            *audit.calculations,
            audit.answer,
        ]
        failures = [c.reason for c in checks if not c.ok]
        if any(not claim.same_role for claim in audit.source_claims):
            failures.append("review_source_role_mismatch")
        return SemanticVerdict(
            material_id,
            self.qualification_id,
            not failures,
            " | ".join(failures) if failures else audit.answer.reason,
        )
