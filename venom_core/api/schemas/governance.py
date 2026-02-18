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
