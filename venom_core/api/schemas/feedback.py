"""Schemas for feedback API endpoints."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    """Request model for submitting user feedback."""

    task_id: UUID
    rating: str = Field(description="up/down")
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""

    status: str
    feedback_saved: bool
    follow_up_task_id: Optional[str] = None


class FeedbackLogsResponse(BaseModel):
    """Response model for feedback logs."""

    count: int
    items: list[dict]
