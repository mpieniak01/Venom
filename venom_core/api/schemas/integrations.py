"""Read-only integration inventory; connectivity never grants actuator consent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from venom_core.api.schemas.connection_status import ConnectionStatus


class IntegrationResource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["robot", "worker", "instance", "runtime", "device"]
    state: Literal["connected", "offline", "stale", "unverified"] = "unverified"
    observed_at: str | None = None
    configuration: Literal["configured", "unconfigured", "unknown"] = "unknown"
    selected: bool = False
    mode: Literal["demo", "device"] | None = None
    source: Literal["configuration", "device_cache"] = "configuration"
    reason_code: str = "not_observed"
    supported_capabilities: list[str] = Field(default_factory=list, max_length=32)
    reported_capabilities: list[str] | None = Field(default=None, max_length=32)
    available_capabilities: list[str] | None = Field(default=None, max_length=32)


class IntegrationObservation(BaseModel):
    """Optional module hook result. Only complete observations establish totals."""

    model_config = ConfigDict(extra="forbid")
    resources: list[IntegrationResource] = Field(default_factory=list, max_length=64)
    resources_complete: bool = False
    connectivity: ConnectionStatus = ConnectionStatus.UNKNOWN
    observed_at: str | None = None
    configuration: Literal["configured", "unconfigured", "unknown"] | None = None
    reason_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,79}$")


class IntegrationEntry(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")
    id: str
    label: str
    scope: Literal["internal", "external"]
    location: Literal["local", "lan", "cloud", "unknown"] = "unknown"
    kind: Literal[
        "api", "module", "runtime", "infrastructure", "catalog", "notifications"
    ] = "api"
    state: str = "unverified"
    configuration: Literal["configured", "unconfigured", "not_required", "unknown"] = (
        "unknown"
    )
    activation: Literal["enabled", "disabled", "unavailable", "unknown"] = "unknown"
    connectivity: ConnectionStatus = ConnectionStatus.UNKNOWN
    source: str = "configuration"
    observed_at: str | None = None
    reason_code: str = "not_probed"
    capabilities: list[str] = Field(default_factory=list)
    configuration_keys: list[str] = Field(default_factory=list)
    access: list[Literal["panel", "cli", "api"]] = Field(default_factory=list)
    panel_path: str | None = None
    documentation_url: str | None = None
    resource_support: Literal["supported", "not_applicable", "unknown"] = "unknown"
    can_probe: bool = False
    resources: list[IntegrationResource] = Field(default_factory=list)
    resource_count: int | None = None
    active_resource_count: int | None = None
    resources_complete: bool = False
