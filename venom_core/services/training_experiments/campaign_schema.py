"""Input contracts for finite Academy training campaigns."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from venom_core.services.training_experiments.quality_schema import (
    CaseId,
    Category,
    EvidenceId,
)

CampaignId = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$", max_length=40)
]
ProfileId = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", max_length=64)
]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$", min_length=64, max_length=64)]


class CampaignBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    max_trials: int = Field(ge=1, le=32)
    max_updates: int = Field(ge=1, le=100_000)
    max_tokens: int = Field(ge=1, le=1_000_000_000)
    max_seconds: int = Field(ge=1, le=604_800)
    trial_seconds: int = Field(ge=1, le=86_400)
    max_retries: int = Field(ge=0, le=3)
    max_artifact_bytes: int = Field(ge=1, le=2**40)
    min_free_bytes: int = Field(ge=0, le=2**40)

    @model_validator(mode="after")
    def validate_trial_duration(self) -> "CampaignBudget":
        if self.trial_seconds > self.max_seconds:
            raise ValueError("campaign_trial_duration_exceeds_budget")
        return self


class CampaignSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    min_usable_delta: float = Field(default=0.0, ge=-1, le=1)
    max_critical_delta: float = Field(default=0.0, ge=0, le=1)


SearchParameter = Literal["rank", "alpha", "learning_rate", "dropout"]


class SearchRange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    low: int | float
    high: int | float
    log: bool | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "SearchRange":
        if self.low >= self.high or (self.log and self.low <= 0):
            raise ValueError("campaign_search_range_invalid")
        return self


QualityDelta = Annotated[float, Field(ge=-1, le=1)]


class CampaignQualityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    reference_record_ids: list[EvidenceId] = Field(default_factory=list, max_length=8)
    protected_case_ids: list[CaseId] = Field(default_factory=list, max_length=2048)
    protect_reference_hits: bool = True
    protect_base_hits: bool = False
    min_category_usable_delta: dict[Category, QualityDelta] = Field(
        default_factory=dict, max_length=64
    )
    no_new_critical: bool = True
    source_record_id: EvidenceId | None = None
    hypothesis: str | None = Field(
        default=None, min_length=1, max_length=1000, pattern=r"\S"
    )

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "CampaignQualityPolicy":
        for values in (self.reference_record_ids, self.protected_case_ids):
            if len(set(values)) != len(values):
                raise ValueError("campaign_quality_duplicate_ids")
        return self


class CampaignSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    campaign_id: CampaignId
    profile_id: ProfileId
    variants: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    strategy: Literal["fixed", "optuna"] = "fixed"
    search_space: dict[SearchParameter, SearchRange] | None = None
    sampler_seed: int = Field(default=42, ge=0, le=2**32 - 1)
    budget: CampaignBudget
    selection: CampaignSelection = Field(default_factory=CampaignSelection)
    retention: Literal["keep_all", "discard_rejected"] = "keep_all"
    review_mode: Literal["manual", "automatic"] = "manual"
    quality_policy: CampaignQualityPolicy | None = None

    @model_validator(mode="after")
    def validate_variant_count(self) -> "CampaignSpec":
        if self.strategy == "fixed":
            if not self.variants or self.search_space is not None:
                raise ValueError("campaign_fixed_variants_required")
            if len(self.variants) > self.budget.max_trials:
                raise ValueError("campaign_trial_budget_exceeded")
        elif self.variants or not self.search_space:
            raise ValueError("campaign_optuna_space_required")
        return self


class CampaignPlanReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    plan_sha256: Digest
