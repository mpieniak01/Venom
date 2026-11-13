"""Versioned portable quality evidence for a single evaluation split."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from scripts.academy.omni_pl_chat_data import MAX_DEV_TASK_LENGTH
from venom_core.services.training_experiments.profiles import SHA256_PATTERN

MAX_QUALITY_CASES = 4096

Digest = Annotated[str, Field(pattern=SHA256_PATTERN)]
RecordId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
EvidenceId = Annotated[
    str,
    Field(
        pattern=r"^(?:(?:history:)?[A-Za-z0-9][A-Za-z0-9_-]{0,63}|checkpoint:[A-Za-z0-9][A-Za-z0-9_-]{0,63}:[1-9][0-9]{0,4})$"
    ),
]
Category = Annotated[
    str, Field(min_length=1, max_length=MAX_DEV_TASK_LENGTH, pattern=r"\S")
]
CaseId = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^\S+$")]
EvidenceLabel = Annotated[str, Field(min_length=1, max_length=512, pattern=r"\S")]
QualityDecision = Literal["GO", "REVISE", "STOP", "INCOMPLETE"]


class _QualityModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class QualityIdentity(_QualityModel):
    model: EvidenceLabel
    base_sha256: Digest | None = None
    dataset_sha256: Digest | None = None
    protocol_sha256: Digest | None = None


class QualitySource(_QualityModel):
    identity: EvidenceLabel
    sha256: Digest
    kind: Literal["historical", "academy"] | None = None


class QualityOutcome(_QualityModel):
    usable: bool
    critical: bool | None


class QualityCase(_QualityModel):
    category: Category
    base: QualityOutcome
    candidate: QualityOutcome


class ReviewedRun(_QualityModel):
    run_id: RecordId
    checkpoint_sha256: Digest
    generation_manifest_sha256: Digest


class QualityRecord(_QualityModel):
    schema_version: Literal[1] = 1
    record_id: RecordId
    split: Literal["dev", "holdout"]
    identity: QualityIdentity
    source: QualitySource
    cases: dict[CaseId, QualityCase] = Field(min_length=1, max_length=MAX_QUALITY_CASES)
    train_sha256: Digest | None = None
    recipe: dict[str, JsonValue] | None = None
    runtime: dict[str, JsonValue] | None = None
    evidence_gaps: list[EvidenceLabel] = Field(default_factory=list, max_length=64)
    protected_case_ids: list[CaseId] = Field(
        default_factory=list, max_length=MAX_QUALITY_CASES
    )
    outcome: QualityDecision | None = None
    reviewed_run: ReviewedRun | None = None
    cohorts: dict[Category, list[CaseId]] | None = None

    @model_validator(mode="after")
    def validate_cases(self) -> QualityRecord:
        if any(case.category == "total" for case in self.cases.values()):
            raise ValueError("quality_reserved_category")
        if len(set(self.protected_case_ids)) != len(self.protected_case_ids):
            raise ValueError("quality_duplicate_protected_cases")
        if self.reviewed_run is not None and (
            self.source.kind != "historical"
            or self.split != "dev"
            or self.outcome not in ("GO", "REVISE", "STOP")
        ):
            raise ValueError("quality_external_review_invalid")
        if self.cohorts is not None:
            if not self.cohorts or len(self.cohorts) > 64 or "total" in self.cohorts:
                raise ValueError("quality_cohorts_invalid")
            for ids in self.cohorts.values():
                unique = set(ids)
                if not ids or len(ids) != len(unique) or unique - self.cases.keys():
                    raise ValueError("quality_cohort_cases_invalid")
        return self


class QualityBundle(_QualityModel):
    schema_version: Literal[1] = 1
    records: list[QualityRecord] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_records(self) -> QualityBundle:
        if len({record.record_id for record in self.records}) != len(self.records):
            raise ValueError("quality_duplicate_records")
        return self
