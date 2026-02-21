"""Schemas for metrics API endpoints."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetricsTaskSection(BaseModel):
    """Task-related metrics section."""

    created: int | None = None
    success_rate: float | None = None


class MetricsRoutingSection(BaseModel):
    """Routing-related metrics section."""

    llm_only: int | None = None
    tool_required: int | None = None
    learning_logged: int | None = None


class MetricsFeedbackSection(BaseModel):
    """Feedback-related metrics section."""

    up: int | None = None
    down: int | None = None


class MetricsPolicySection(BaseModel):
    """Policy-related metrics section."""

    blocked_count: int | None = None
    block_rate: float | None = None


class MetricsNetworkSection(BaseModel):
    """Network-related metrics section."""

    total_bytes: int | None = None


class MetricsResponse(BaseModel):
    """Primary metrics payload returned by /api/v1/metrics and /api/v1/metrics/system."""

    model_config = ConfigDict(extra="allow")

    tasks: MetricsTaskSection | None = None
    routing: MetricsRoutingSection | None = None
    feedback: MetricsFeedbackSection | None = None
    policy: MetricsPolicySection | None = None
    uptime_seconds: int | None = None
    network: MetricsNetworkSection | None = None


class TokenMetricsResponse(BaseModel):
    """Token/cost metrics payload returned by /api/v1/metrics/tokens."""

    model_config = ConfigDict(extra="allow")

    total_tokens: int | None = None
    session_total_tokens: int | None = None
    session_cost_usd: float | None = None
    models_breakdown: dict[str, dict[str, Any]] = Field(default_factory=dict)
    note: str | None = None
