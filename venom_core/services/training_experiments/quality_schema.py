"""Versioned portable quality evidence for a single evaluation split."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .profiles import SHA256_PATTERN

Digest = Annotated[str, Field(pattern=SHA256_PATTERN)]
RecordId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
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
    category: Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
    base: QualityOutcome
    candidate: QualityOutcome


class QualityRecord(_QualityModel):
    schema_version: Literal[1] = 1
    record_id: RecordId
    split: Literal["dev", "holdout"]
    identity: QualityIdentity
    source: QualitySource
    cases: dict[CaseId, QualityCase] = Field(min_length=1, max_length=4096)
    train_sha256: Digest | None = None
    recipe: dict[str, JsonValue] | None = None
    runtime: dict[str, JsonValue] | None = None
    evidence_gaps: list[EvidenceLabel] = Field(default_factory=list, max_length=64)
    protected_case_ids: list[CaseId] = Field(default_factory=list, max_length=4096)
    outcome: QualityDecision | None = None

    @model_validator(mode="after")
    def validate_cases(self) -> QualityRecord:
        if any(case.category == "total" for case in self.cases.values()):
            raise ValueError("quality_reserved_category")
        if len(set(self.protected_case_ids)) != len(self.protected_case_ids):
            raise ValueError("quality_duplicate_protected_cases")
        return self


class QualityBundle(_QualityModel):
    schema_version: Literal[1] = 1
    records: list[QualityRecord] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_records(self) -> QualityBundle:
        if len({record.record_id for record in self.records}) != len(self.records):
            raise ValueError("quality_duplicate_records")
        return self
