"""Schemas for strategy API endpoints."""

from pydantic import BaseModel


class RoadmapCreateRequest(BaseModel):
    """Request dla utworzenia roadmapy."""

    vision: str
