"""Schemas for queue API endpoints."""

from pydantic import BaseModel, ConfigDict


class QueueStatusResponse(BaseModel):
    """Queue status payload."""

    model_config = ConfigDict(extra="allow")

    paused: bool | None = None
    pending: int | None = None
    active: int | None = None
    limit: int | None = None


class QueueActionResponse(BaseModel):
    """Generic queue action payload (pause/resume/purge/emergency/abort)."""

    model_config = ConfigDict(extra="allow")

    success: bool | None = None
    message: str | None = None
