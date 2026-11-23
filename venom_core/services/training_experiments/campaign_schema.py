"""Input contracts for finite Academy training campaigns."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from venom_core.services.training_experiments.quality_schema import (
    MAX_QUALITY_CASES,
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
    protect_parent_full_pass: bool = False


class CampaignExtension(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    initial_trials: int = Field(ge=1, le=31)
    min_usable_delta: float = Field(gt=0, le=1)
    repeat_best_recipe: bool = False


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
    parent_reference_record_id: EvidenceId | None = None
    protect_parent_full_pass: bool = False
    protected_case_ids: list[CaseId] = Field(
        default_factory=list, max_length=MAX_QUALITY_CASES
    )
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
        if self.protect_parent_full_pass and self.parent_reference_record_id is None:
            raise ValueError("campaign_quality_parent_reference_missing")
        for values in (self.reference_record_ids, self.protected_case_ids):
            if len(set(values)) != len(values):
                raise ValueError("campaign_quality_duplicate_ids")
        if (
            self.parent_reference_record_id is not None
            and self.parent_reference_record_id not in self.reference_record_ids
        ):
            raise ValueError("campaign_quality_parent_reference_missing")
        return self


class CampaignConversationReview(BaseModel):
    """Opt-in 0A development conversation receipt gate for each checkpoint."""

    model_config = ConfigDict(extra="forbid", strict=True)

    panel_sha256: Digest
    final_mode: Literal["local", "remote"] = "local"
    receipt_id_prefix: str = Field(
        min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
    )


class CampaignFinalQualification(BaseModel):
    """Select an operator-registered private holdout and reserve its session budget."""

    model_config = ConfigDict(extra="forbid", strict=True)

    inputs_id: CampaignId
    reserve_seconds: int = Field(ge=30, le=86400)
    conversation_review_required: bool = False
    conversation_review_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
    )

    @model_validator(mode="after")
    def validate_conversation_review(self) -> "CampaignFinalQualification":
        if self.conversation_review_required and self.conversation_review_id is None:
            raise ValueError("campaign_conversation_review_id_required")
        return self


CheckpointStep = Annotated[int, Field(ge=1, le=10000)]


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
    conversation_review: CampaignConversationReview | None = None
    extension: CampaignExtension | None = None
    final_qualification: CampaignFinalQualification | None = None
    checkpoint_steps: list[CheckpointStep] | None = Field(
        default=None, min_length=1, max_length=4
    )

    @model_validator(mode="after")
    def validate_variant_count(self) -> "CampaignSpec":
        if self.strategy == "fixed":
            if not self.variants or self.search_space is not None:
                raise ValueError("campaign_fixed_variants_required")
            trials = (
                self.extension.initial_trials + 1
                if self.extension is not None and self.extension.repeat_best_recipe
                else len(self.variants)
            )
            if trials > self.budget.max_trials:
                raise ValueError("campaign_trial_budget_exceeded")
        elif self.variants or not self.search_space:
            raise ValueError("campaign_optuna_space_required")
        if self.checkpoint_steps is not None and (
            self.strategy != "fixed"
            or self.checkpoint_steps != sorted(set(self.checkpoint_steps))
        ):
            raise ValueError("campaign_checkpoint_steps_invalid")
        self._validate_final_qualification()
        self._validate_conversation_review()
        self._validate_extension()
        self._validate_repeat_recipe()
        self._validate_parent_protection()
        return self

    def _validate_extension(self) -> None:
        if self.extension is not None and (
            self.strategy != "fixed"
            or self.review_mode != "automatic"
            or self.extension.initial_trials >= len(self.variants)
            or self.extension.min_usable_delta < self.selection.min_usable_delta
        ):
            raise ValueError("campaign_extension_invalid")

    def _validate_parent_protection(self) -> None:
        if self.selection.protect_parent_full_pass and (
            self.quality_policy is None
            or self.quality_policy.parent_reference_record_id is None
            or not self.quality_policy.protect_parent_full_pass
        ):
            raise ValueError("campaign_quality_parent_full_pass_policy_required")

    def _validate_final_qualification(self) -> None:
        if self.final_qualification is not None and (
            self.strategy != "fixed"
            or self.review_mode != "automatic"
            or self.checkpoint_steps is None
            or self.final_qualification.reserve_seconds >= self.budget.max_seconds
            or self.budget.trial_seconds
            > self.budget.max_seconds - self.final_qualification.reserve_seconds
        ):
            raise ValueError("campaign_final_qualification_invalid")

    def _validate_conversation_review(self) -> None:
        if self.conversation_review is None:
            return
        if (
            self.strategy != "fixed"
            or self.review_mode != "automatic"
            or self.checkpoint_steps is None
            or self.quality_policy is None
            or self.quality_policy.parent_reference_record_id is None
            or self.quality_policy.protect_parent_full_pass is not True
            or self.retention != "keep_all"
            or (self.conversation_review.final_mode == "local")
            != (self.final_qualification is not None)
        ):
            raise ValueError("campaign_conversation_review_invalid")

    def _validate_repeat_recipe(self) -> None:
        if (
            self.extension is not None
            and self.extension.repeat_best_recipe
            and (
                len(self.variants) != 2 * self.extension.initial_trials
                or self.quality_policy is None
                or self.quality_policy.parent_reference_record_id is None
            )
        ):
            raise ValueError("campaign_repeat_recipe_invalid")


class CampaignPlanReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    plan_sha256: Digest
