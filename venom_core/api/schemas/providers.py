"""API schemas for provider management endpoints."""

from pydantic import BaseModel, Field


class ProviderCapability(BaseModel):
    """Provider capabilities."""

    install: bool = Field(default=False, description="Supports model installation")
    search: bool = Field(default=False, description="Supports model search")
    activate: bool = Field(default=False, description="Supports runtime activation")
    inference: bool = Field(default=False, description="Supports inference")
    trainable: bool = Field(default=False, description="Supports model training")


class ProviderStatus(BaseModel):
    """Provider connection status."""

    status: str = Field(
        ...,
        description="Connection status: connected, degraded, offline, unknown",
    )
    reason_code: str | None = Field(
        default=None, description="Reason code for non-connected status"
    )
    message: str | None = Field(
        default=None, description="Human-readable status message"
    )
    latency_ms: float | None = Field(
        default=None, description="Connection latency in milliseconds"
    )


class ProviderInfo(BaseModel):
    """Provider information."""

    name: str = Field(..., description="Provider name")
    display_name: str = Field(..., description="Display name")
    provider_type: str = Field(
        ..., description="Type: cloud_provider, catalog_integrator, local_runtime"
    )
    runtime: str = Field(..., description="Runtime identifier")
    capabilities: ProviderCapability
    connection_status: ProviderStatus
    is_active: bool = Field(default=False, description="Is currently active")
    endpoint: str | None = Field(default=None, description="Provider endpoint")


class ProviderActivateRequest(BaseModel):
    """Request to activate a provider."""

    runtime: str | None = Field(
        default=None, description="Optional runtime override"
    )
    model: str | None = Field(default=None, description="Optional model name")
