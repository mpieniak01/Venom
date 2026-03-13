"""API schemas for provider governance endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class GovernanceStatusResponse(BaseModel):
    """Response dla statusu governance."""

    status: str = "success"
    cost_limits: dict[str, dict[str, Any]]
    rate_limits: dict[str, dict[str, Any]]
    recent_fallbacks: list[dict[str, Any]]
    fallback_policy: dict[str, Any]


class LimitsConfigResponse(BaseModel):
    """Response dla konfiguracji limitów."""

    status: str = "success"
    cost_limits: dict[str, dict[str, float]]
    rate_limits: dict[str, dict[str, int]]


class ProviderCredentialStatusResponse(BaseModel):
    """Response dla statusu credentiali providera."""

    provider: str
    credential_status: str
    message: str


class UpdateLimitRequest(BaseModel):
    """Request do aktualizacji limitu."""

    limit_type: str = Field(..., description="Typ limitu: 'cost' lub 'rate'")
    scope: str = Field(..., description="Zakres: 'global', nazwa providera lub modelu")
    soft_limit_usd: float | None = Field(
        None, description="Soft limit w USD (dla cost)", gt=0
    )
    hard_limit_usd: float | None = Field(
        None, description="Hard limit w USD (dla cost)", gt=0
    )
    max_requests_per_minute: int | None = Field(
        None, description="Max requestów na minutę (dla rate)", gt=0
    )
    max_tokens_per_minute: int | None = Field(
        None, description="Max tokenów na minutę (dla rate)", gt=0
    )


class CostModeRequest(BaseModel):
    """Request do zmiany trybu kosztowego."""

    enable: bool


class CostModeResponse(BaseModel):
    """Response z informacją o trybie kosztowym."""

    enabled: bool
    provider: str


class CostModeSetResponse(BaseModel):
    """Response for setting cost mode."""

    status: str
    message: str
    enabled: bool


class AutonomyLevelRequest(BaseModel):
    """Request do zmiany poziomu autonomii."""

    level: int


class AutonomyLevelResponse(BaseModel):
    """Response z informacją o poziomie autonomii."""

    current_level: int
    current_level_name: str
    color: str
    color_name: str
    description: str
    permissions: dict
    risk_level: str


class AutonomyLevelSetResponse(BaseModel):
    """Response for setting autonomy level."""

    status: str
    message: str
    level: int
    level_name: str
    color: str
    permissions: dict


class AutonomyLevelsResponse(BaseModel):
    """Response for all autonomy levels."""

    status: str
    levels: list[dict[str, Any]]
    count: int


class PolicyReasonStat(BaseModel):
    """Single reason code statistic for policy/autonomy blocks."""

    reason_code: str
    count: int
    share_rate: float


class PolicyFalsePositiveTriage(BaseModel):
    """Triage snapshot for potential false-positive policy blocks."""

    candidate_count: int = 0
    candidate_rate: float = 0.0
    top_candidate_reasons: list[PolicyReasonStat] = Field(default_factory=list)


class AutonomyObservabilityPayload(BaseModel):
    """Operational policy/autonomy observability payload."""

    blocked_count: int = 0
    deny_rate: float = 0.0
    top_reason_codes: list[PolicyReasonStat] = Field(default_factory=list)
    false_positive_triage: PolicyFalsePositiveTriage = Field(
        default_factory=PolicyFalsePositiveTriage
    )


class AutonomyObservabilityResponse(BaseModel):
    """Response for dedicated policy/autonomy observability endpoint."""

    status: str = "success"
    source: str = "runtime_policy_gate"
    policy: AutonomyObservabilityPayload


class AutonomyRolloutStatusResponse(BaseModel):
    """Response for runtime-only policy gate rollout readiness."""

    status: str = "success"
    source: str = "runtime_policy_gate"
    readiness: str
    runtime_only_architecture: bool
    policy_gate_enabled: bool
    global_checkpoint_phase: str = "global_pre_execution"
    legacy_submit_stage_removed: bool
    observability_endpoint_available: bool
    required_next_actions: list[str] = Field(default_factory=list)
