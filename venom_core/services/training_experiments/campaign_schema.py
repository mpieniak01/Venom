"""Input contracts for finite Academy training campaigns."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class CampaignSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    campaign_id: CampaignId
    profile_id: ProfileId
    variants: list[dict[str, Any]] = Field(min_length=1, max_length=32)
    budget: CampaignBudget
    selection: CampaignSelection = Field(default_factory=CampaignSelection)
    retention: Literal["keep_all", "discard_rejected"] = "keep_all"
    review_mode: Literal["manual", "automatic"] = "manual"

    @model_validator(mode="after")
    def validate_variant_count(self) -> "CampaignSpec":
        if len(self.variants) > self.budget.max_trials:
            raise ValueError("campaign_trial_budget_exceeded")
        return self


class CampaignPlanReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    plan_sha256: Digest
