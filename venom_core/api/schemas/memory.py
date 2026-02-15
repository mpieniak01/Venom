"""API schemas for memory and knowledge management endpoints."""

from typing import Optional

from pydantic import BaseModel


class MemoryIngestRequest(BaseModel):
    """Model żądania ingestion do pamięci."""

    text: str
    category: str = "general"
    collection: str = "default"
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    pinned: Optional[bool] = None
    memory_type: Optional[str] = None
    scope: Optional[str] = None
    topic: Optional[str] = None
    timestamp: Optional[str] = None


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
    """Request to toggle learning mode."""

    enabled: bool
