"""Structured semantic verification for the explicit grounded-dialogue pilot."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import Field, StrictBool, StrictInt, StrictStr

from venom_core.services.grounded_pilot import (
    SemanticVerdict,
    StrictModel,
    material_hash,
    requests_unitless_result,
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


class CompactFindings(StrictModel):
    state: StrictStr = Field(min_length=1, max_length=220)
    context_ok: StrictBool
    source_ok: StrictBool
    source_refs: list[StrictInt] = Field(max_length=8)
    calc_ok: list[StrictBool] = Field(max_length=8)
    answer_ok: StrictBool
    reason: StrictStr = Field(min_length=1, max_length=300)


def compact_packet(material: dict[str, Any]) -> dict[str, Any]:
    """Keep complete source text and ordered computations without duplicating claims."""
    plan = material["plan"]
    evidence = material["evidence"]
    output = evidence["calculations"]
    planned = [
        (c["calculation_id"], c["expression"], c["unit"]) for c in plan["calculations"]
    ]
    if planned != [(c["calculation_id"], c["expression"], c["unit"]) for c in output]:
        raise ValueError("review_plan_evidence_mismatch")
    cards = [
        {"n": i, "id": doc["ref"]["source_id"], "text": doc["text"]}
        for i, doc in enumerate(evidence["sources"], 1)
    ]
    cited = {claim["source_id"] for claim in material["draft"].get("sources", [])}
    packet = {
        "request": material["message"],
        "prior_users": [
            turn["content"] for turn in material["history"] if turn["role"] == "user"
        ],
        "needs": material["requirements"],
        "mode": plan["mode"],
        "missing": plan["missing"],
        "sources": cards,
        "calculations": [
            {
                "n": i,
                "expression": c["expression"],
                "value": c["value"],
                "unit": c["unit"],
            }
            for i, c in enumerate(output, 1)
        ],
        "answer": material["draft"]["prose"],
    }
    if "result_precision" in material:
        packet["result_precision"] = material["result_precision"]
    if output and requests_unitless_result(material["message"]):
        packet["result_presentation"] = "number_without_unit"
    if cited:
        packet["cited_source_refs"] = [
            card["n"] for card in cards if card["id"] in cited
        ]
    return packet


def compact_approved(raw: dict[str, Any], packet: dict[str, Any]) -> bool:
    findings = CompactFindings.model_validate(raw)
    if len(findings.calc_ok) != len(packet["calculations"]):
        raise ValueError("review_calculation_coverage_invalid")
    refs = findings.source_refs
    if len(set(refs)) != len(refs) or not set(refs) <= {
        doc["n"] for doc in packet["sources"]
    }:
        raise ValueError("review_source_reference_invalid")
    if (
        packet["needs"]["sources"]
        and packet["mode"] == "answer"
        and findings.source_ok
        and findings.answer_ok
        and (not refs or not set(packet.get("cited_source_refs", ())) <= set(refs))
    ):
        raise ValueError("review_source_coverage_missing")
    return (
        findings.context_ok
        and findings.source_ok
        and findings.answer_ok
        and all(findings.calc_ok)
    )


class CompactContextFinding(StrictModel):
    ok: StrictBool
    reason: StrictStr = Field(min_length=1)
    state: StrictStr = Field(min_length=1)


def context_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Give the reviewer the executed expressions used by an answer."""
    context = {key: packet[key] for key in ("request", "prior_users", "answer")}
    if packet["calculations"]:
        context["calculations"] = packet["calculations"]
    return context


class ArithmeticFinding(Finding):
    n: StrictInt


class ArithmeticReview(StrictModel):
    complete: Finding
    steps: list[ArithmeticFinding] = Field(max_length=8)


def arithmetic_approved(raw: dict[str, Any], packet: dict[str, Any]) -> bool:
    """Require a substantive verdict for each step and for the whole plan."""
    audit = ArithmeticReview.model_validate(raw)
    expected = [item["n"] for item in packet["calculations"]]
    if not expected or [step.n for step in audit.steps] != expected:
        raise ValueError("review_arithmetic_coverage_invalid")
    if not audit.complete.reason.strip() or any(
        not step.reason.strip() for step in audit.steps
    ):
        raise ValueError("review_arithmetic_reason_missing")
    return audit.complete.ok and all(step.ok for step in audit.steps)


class CompactGroundedReviewer:
    """Bind the transport response to the original material and verify its coverage."""

    def __init__(
        self,
        qualification_id: str,
        review_call: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        arithmetic_call: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        context_call: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.qualification_id = qualification_id
        self.review_call = review_call
        self.arithmetic_call = arithmetic_call
        self.context_call = context_call

    def review(self, material: dict[str, Any]) -> SemanticVerdict:
        packet = compact_packet(material)
        reply = self.review_call(packet)
        approved = compact_approved(reply, packet)
        reason = reply["reason"]
        if packet["prior_users"] and self.context_call is not None:
            context = CompactContextFinding.model_validate(
                self.context_call(context_packet(packet))
            )
            if not context.state.strip() or not context.reason.strip():
                raise ValueError("review_context_finding_missing")
            if not context.ok:
                approved = False
                reason = context.reason
        if approved and packet["calculations"] and self.arithmetic_call is not None:
            arithmetic = self.arithmetic_call(packet)
            approved = arithmetic_approved(arithmetic, packet)
            if not approved:
                audit = ArithmeticReview.model_validate(arithmetic)
                findings = [audit.complete, *audit.steps]
                reason = " | ".join(item.reason for item in findings if not item.ok)
        return SemanticVerdict(
            material_hash(material), self.qualification_id, approved, reason
        )
