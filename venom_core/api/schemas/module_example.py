"""Schemas for Module Example modular API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ContentCandidate(BaseModel):
    id: str = Field(..., description="Unique candidate identifier")
    title: str = Field(..., description="Candidate title")
    source: str = Field(..., description="Source name")
    url: str | None = Field(default=None, description="Source URL")
    topic: str | None = Field(default=None, description="Normalized topic label")
    score: float = Field(default=0.0, description="Ranking score")
    freshness_hours: int = Field(default=0, description="Age in hours")


class DraftVariant(BaseModel):
    id: str = Field(..., description="Variant identifier")
    channel: str = Field(..., description="Target channel")
    language: str = Field(..., description="Language code")
    content: str = Field(..., description="Generated draft content")
    tone: str | None = Field(default=None, description="Tone label")


class DraftBundle(BaseModel):
    id: str = Field(..., description="Draft bundle identifier")
    candidate_id: str = Field(..., description="Source candidate ID")
    variants: list[DraftVariant] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PublishQueueItem(BaseModel):
    id: str = Field(..., description="Queue item ID")
    draft_id: str = Field(..., description="Draft bundle ID")
    target_channel: str = Field(..., description="Selected channel")
    status: Literal["draft", "ready", "queued", "published", "failed", "cancelled"] = (
        Field(..., description="Publication status of the item.")
    )
    target_repo: str | None = Field(default=None)
    target_path: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    failure_reason: str | None = Field(default=None)


class PublishResult(BaseModel):
    item_id: str = Field(..., description="Queue item ID")
    status: str = Field(..., description="Publish status")
    message: str = Field(..., description="Human-readable result")
    published_at: datetime | None = Field(default=None)


class ModuleExampleAuditEntry(BaseModel):
    id: str = Field(..., description="Audit entry ID")
    action: str = Field(..., description="Action type")
    actor: str = Field(..., description="Actor identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    entity_id: str | None = Field(default=None)
    details: str | None = Field(default=None)


class CandidatesResponse(BaseModel):
    items: list[ContentCandidate] = Field(default_factory=list)


class QueueResponse(BaseModel):
    items: list[PublishQueueItem] = Field(default_factory=list)


class AuditResponse(BaseModel):
    items: list[ModuleExampleAuditEntry] = Field(default_factory=list)


class GenerateDraftsRequest(BaseModel):
    candidate_id: str
    channels: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    tone: str | None = None


class QueueDraftRequest(BaseModel):
    target_channel: str
    target_repo: str | None = None
    target_path: str | None = None


class PublishQueueRequest(BaseModel):
    confirm_publish: bool = False
