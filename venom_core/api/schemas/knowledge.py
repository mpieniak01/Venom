"""Schemas for knowledge API endpoints."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from venom_core.api.schemas.memory import LearningToggleRequest


class KnowledgeEntryScope(str, Enum):
    SESSION = "session"
    GLOBAL = "global"
    TASK = "task"


class KnowledgeSourceOrigin(str, Enum):
    SESSION = "session"
    LESSON = "lesson"
    VECTOR = "vector"
    GRAPH = "graph"
    TRAINING = "training"
    EXTERNAL = "external"


class KnowledgeSourceMeta(BaseModel):
    origin: KnowledgeSourceOrigin
    provenance: dict[str, Any] = Field(default_factory=dict)
    reason_code: str | None = None


class KnowledgeEntry(BaseModel):
    entry_id: str
    entry_type: str
    scope: KnowledgeEntryScope
    source: str
    content: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    session_id: str | None = None
    task_id: str | None = None
    request_id: str | None = None
    created_at: str
    updated_at: str | None = None
    ttl_at: str | None = None
    confidence: float | None = None
    quality_score: float | None = None
    version: str = "v1"
    source_meta: KnowledgeSourceMeta
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeEntriesResponse(BaseModel):
    status: str = "success"
    count: int
    entries: list[KnowledgeEntry] = Field(default_factory=list)


class KnowledgeMutationMeta(BaseModel):
    target: str
    action: str
    source: KnowledgeSourceOrigin
    affected_count: int = 0
    scope: KnowledgeEntryScope | None = None
    filter: dict[str, Any] = Field(default_factory=dict)


class KnowledgeMutationResponse(BaseModel):
    status: str = "success"
    message: str
    mutation: KnowledgeMutationMeta


__all__ = [
    "LearningToggleRequest",
    "KnowledgeEntry",
    "KnowledgeEntriesResponse",
    "KnowledgeEntryScope",
    "KnowledgeMutationMeta",
    "KnowledgeMutationResponse",
    "KnowledgeSourceMeta",
    "KnowledgeSourceOrigin",
]
