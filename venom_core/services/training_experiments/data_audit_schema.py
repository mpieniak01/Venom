"""Versioned survey of reviewed training groups and the Omni token mask."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scripts.academy.omni_pl_chat_audit import MAX_AUDIT_SKILLS

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Group = Literal["replay", "fresh"]
Skill = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
Count = Annotated[int, Field(ge=0, le=10**12)]


class _StrictAuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AuditFloor(_StrictAuditModel):
    min_records: Count = 0
    min_supervised_tokens: Count = 0


class AuditPolicy(_StrictAuditModel):
    groups: dict[Group, AuditFloor] = Field(default_factory=dict)
    skills: dict[Skill, dict[Group, AuditFloor]] = Field(
        default_factory=dict, max_length=MAX_AUDIT_SKILLS
    )


class AuditPin(_StrictAuditModel):
    report_sha256: Digest
    taxonomy_sha256: Digest
    policy: AuditPolicy


class AuditBucket(_StrictAuditModel):
    records: Count
    supervised_tokens: Count
    input_tokens: Count
    max_input_tokens: Count
    max_supervised_tokens: Count

    @model_validator(mode="after")
    def validate_counts(self) -> "AuditBucket":
        if (
            self.records > self.supervised_tokens
            or self.supervised_tokens > self.input_tokens
            or self.max_supervised_tokens > self.max_input_tokens
            or self.max_supervised_tokens > self.supervised_tokens
            or self.max_input_tokens > self.input_tokens
            or self.supervised_tokens > self.records * self.max_supervised_tokens
            or self.input_tokens > self.records * self.max_input_tokens
        ):
            raise ValueError("data_audit_bucket_invalid")
        return self


class AuditGroups(_StrictAuditModel):
    replay: AuditBucket
    fresh: AuditBucket


class AuditTokenizer(_StrictAuditModel):
    template_sha256: Digest
    tokenizer_sha256: Digest
    tokenizer_config_sha256: Digest
    model_config_sha256: Digest
    transformers: str = Field(min_length=1, max_length=128)
    tokenizers: str = Field(min_length=1, max_length=128)
    max_tokens: int = Field(ge=32, le=4096)


class AuditLeakage(_StrictAuditModel):
    normalization: Literal["nfkc_casefold_whitespace_v1"]
    supervised_prefix_matches: Count
    final_user_matches: Count
    duplicate_train_records: Count


class AuditReport(_StrictAuditModel):
    schema_version: Literal[1]
    model: str = Field(min_length=1, max_length=128)
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    snapshot_sha256: Digest
    train_sha256: Digest
    dev_sha256: Digest
    taxonomy_sha256: Digest
    tokenization: AuditTokenizer
    totals: AuditBucket
    groups: AuditGroups
    skills: dict[Skill, AuditGroups] = Field(min_length=1, max_length=MAX_AUDIT_SKILLS)
    leakage: AuditLeakage


class AuditTag(_StrictAuditModel):
    group: Group
    skill: Skill


class AuditTaxonomy(_StrictAuditModel):
    schema_version: Literal[1]
    records: dict[str, AuditTag] = Field(min_length=1)
