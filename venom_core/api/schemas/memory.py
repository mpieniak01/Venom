"""API schemas for memory and knowledge management endpoints."""

from pydantic import BaseModel


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


class LearningToggleRequest(BaseModel):
    """Request do przełączenia trybu uczenia."""

    enabled: bool
