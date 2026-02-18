"""API schemas for memory and knowledge management endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class MemoryIngestRequest(BaseModel):
    """Model żądania ingestion do pamięci."""

    text: str
    category: str = "general"
    collection: str = "default"
    session_id: str | None = None
    user_id: str | None = None
    pinned: bool | None = None
    memory_type: str | None = None
    scope: str | None = None
    topic: str | None = None
    timestamp: str | None = None


class MemoryIngestResponse(BaseModel):
    """Model odpowiedzi po ingestion."""

    status: str
    message: str
    chunks_count: int = 0


class MemorySearchRequest(BaseModel):
    """Model żądania wyszukiwania w pamięci."""

    query: str
    limit: int = 3
    collection: str = "default"


class MemorySearchResponse(BaseModel):
    status: str
    query: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class SessionMemoryResponse(BaseModel):
    status: str
    session_id: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None
    count: int = 0


class SessionMemoryClearResponse(BaseModel):
    status: str
    session_id: str
    deleted_vectors: int = 0
    cleared_tasks: int = 0
    message: str


class GlobalMemoryClearResponse(BaseModel):
    status: str
    deleted_vectors: int = 0
    message: str


class MemoryGraphElements(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class MemoryGraphStats(BaseModel):
    nodes: int = 0
    edges: int = 0


class MemoryGraphResponse(BaseModel):
    status: str
    elements: MemoryGraphElements
    stats: MemoryGraphStats


class MemoryEntryMutationResponse(BaseModel):
    status: str
    entry_id: str
    pinned: bool | None = None
    deleted: int | None = None


class CacheFlushResponse(BaseModel):
    status: str
    message: str
    deleted: int = 0


class LearningToggleRequest(BaseModel):
    """Request do przełączenia trybu uczenia."""

    enabled: bool


class LessonsMutationResponse(BaseModel):
    status: str
    message: str | None = None
    deleted: int | None = None
    removed: int | None = None
    days: int | None = None
    start: str | None = None
    end: str | None = None
    tag: str | None = None


class LearningStatusResponse(BaseModel):
    status: str
    enabled: bool
