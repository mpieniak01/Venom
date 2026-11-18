"""Choose a campaign parent without discarding wider, sealed regression evidence."""

from __future__ import annotations

import re
from typing import Annotated, Any, cast

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from .profiles import stable_hash


class _AuditVerdict(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    usable: Annotated[int, Field(ge=0, le=1)] | None
    passed: Annotated[int, Field(ge=0, le=1)] | None

    @model_validator(mode="after")
    def _consistent(self) -> _AuditVerdict:
        if self.passed == 1 and self.usable != 1:
            raise ValueError("experiment_parent_broad_audit_invalid")
        return self


class _BroadPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    factual_final_used: StrictBool
    model_identities: dict[str, dict[str, Any]]
    verdicts: dict[str, dict[str, _AuditVerdict]]
    critical_by_case: dict[str, dict[str, StrictBool | None]]

    @model_validator(mode="after")
    def _unopened_final(self) -> _BroadPayload:
        if self.factual_final_used is not False:
            raise ValueError("experiment_parent_broad_audit_invalid")
        return self


class ShortComparison(BaseModel):
    """Qualified S/K comparison, still insufficient to qualify general chat."""

    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False)
    usable_delta: float = Field(ge=-1, le=1)
    passed_delta: float = Field(ge=-1, le=1)
    full_retention: StrictBool
    new_critical_case_ids: list[str]


_DIGEST = re.compile(r"[0-9a-f]{64}")
_GROUPS = frozenset({"W", "K", "S", "R"})


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("experiment_parent_broad_audit_invalid")


def _metric_losses(
    reference: dict, candidate: dict
) -> tuple[dict[str, list[str]], set[str]]:
    lost: dict[str, list[str]] = {"usable": [], "passed": []}
    unresolved: set[str] = set()
    for ident in sorted(reference):
        for metric in lost:
            before, after = (
                getattr(reference[ident], metric),
                getattr(candidate[ident], metric),
            )
            if before is None or after is None:
                unresolved.add(ident)
            elif before == 1 and after == 0:
                lost[metric].append(ident)
    return lost, unresolved


def _critical_changes(critical: dict, reference: dict) -> tuple[list[str], set[str]]:
    new_critical: list[str] = []
    unresolved: set[str] = set()
    for ident in sorted(reference):
        before, after = critical["P13"][ident], critical["P25"][ident]
        _require(
            (before is None or type(before) is bool)
            and (after is None or type(after) is bool)
        )
        if before is None or after is None:
            unresolved.add(ident)
        elif after and not before:
            new_critical.append(ident)
    return new_critical, unresolved


def _broad_gate(
    report: dict,
    expected: str,
    reference_weight: str,
    candidate_weight: str,
) -> dict:
    payload = report.get("payload")
    _require(isinstance(payload, dict))
    payload = cast(dict, payload)
    _require(
        bool(_DIGEST.fullmatch(expected))
        and report.get("sha256") == expected == stable_hash(payload)
    )
    try:
        validated = _BroadPayload.model_validate(payload)
    except ValueError as exc:
        raise ValueError("experiment_parent_broad_audit_invalid") from exc
    identities = validated.model_identities
    _require(
        identities.get("checkpoint-145", {}).get("adapter_model.safetensors")
        == reference_weight
        and identities.get("checkpoint-25", {}).get("adapter_model.safetensors")
        == candidate_weight
    )
    verdicts, critical = validated.verdicts, validated.critical_by_case
    reference, candidate = verdicts.get("P13", {}), verdicts.get("P25", {})
    _require(
        len(reference) == len(candidate) == 144
        and reference.keys() == candidate.keys()
        and critical.get("P13", {}).keys() == reference.keys()
        and critical.get("P25", {}).keys() == reference.keys()
    )
    groups: dict[str, int] = {}
    for ident in sorted(reference):
        match = re.fullmatch(r"inc17-dialogue-([WKSR])-[1-6]-t[1-6]", ident)
        _require(match is not None)
        group = cast(re.Match[str], match)[1]
        groups[group] = groups.get(group, 0) + 1
    lost, unresolved = _metric_losses(reference, candidate)
    new_critical, critical_unknown = _critical_changes(critical, reference)
    unresolved.update(critical_unknown)
    _require(set(groups) == _GROUPS and set(groups.values()) == {36})
    blockers = []
    if any(lost.values()):
        blockers.append("broad_retention_lost")
    if new_critical:
        blockers.append("broad_new_critical")
    if unresolved:
        blockers.append("broad_unresolved")
    return {
        "source_report_sha256": expected,
        "expected_pairs": 144,
        "lost_reference_case_ids": lost,
        "new_critical_case_ids": new_critical,
        "unresolved_pair_case_ids": sorted(unresolved),
        "blockers": blockers,
        "passed": not blockers,
    }


def select_campaign_parent(
    sk_comparison: dict,
    *,
    broad_report: dict | None,
    expected_report_sha256: str | None,
    reference_weight_sha256: str,
    candidate_weight_sha256: str,
) -> dict:
    """Return S/K recommendation separately; wider uncertainty retains P13.

    The caller must verify S/K qualification/receipts before supplying comparison.
    The expected wider payload hash must come from the frozen evidence contract.
    No result here promotes weights or rewrites the lineage of existing trials.
    """
    short = ShortComparison.model_validate(sk_comparison)
    for checksum in (reference_weight_sha256, candidate_weight_sha256):
        _require(bool(_DIGEST.fullmatch(checksum)))
    _require(reference_weight_sha256 != candidate_weight_sha256)
    recommendation = (
        "P25"
        if short.usable_delta > 0
        and short.passed_delta > 0
        and short.full_retention
        and not short.new_critical_case_ids
        else "P13"
    )
    broad = (
        {"passed": False, "blockers": ["broad_audit_missing"]}
        if broad_report is None
        else _broad_gate(
            broad_report,
            expected_report_sha256 or "",
            reference_weight_sha256,
            candidate_weight_sha256,
        )
    )
    selected = "P25" if recommendation == "P25" and broad["passed"] else "P13"
    return {
        "sk_recommendation": recommendation,
        "selected_parent": selected,
        "reason": "retained_progress_across_scopes"
        if selected == "P25"
        else "reference_retained",
        "broad_gate": broad,
        "qualified_candidate": None,
    }
