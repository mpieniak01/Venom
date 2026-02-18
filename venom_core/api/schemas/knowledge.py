"""Schemas for knowledge API endpoints."""

from pydantic import BaseModel


class LearningToggleRequest(BaseModel):
    """Request for toggling learning on/off."""

    enabled: bool
