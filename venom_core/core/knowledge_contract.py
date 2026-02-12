"""Knowledge Contract v1: shared schema for session/lesson/memory records."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class KnowledgeKind(str, Enum):
    SESSION_MESSAGE = "session_message"
    SESSION_SUMMARY = "session_summary"
    LESSON = "lesson"
    MEMORY_ENTRY = "memory_entry"
    RETRIEVAL_CONTEXT = "retrieval_context"


class KnowledgeSource(str, Enum):
    SESSION_STORE = "session_store"
    STATE_MANAGER = "state_manager"
    LESSONS_STORE = "lessons_store"
    VECTOR_STORE = "vector_store"
    ORCHESTRATOR = "orchestrator"


class ProvenanceV1(BaseModel):
    source: KnowledgeSource
    origin_id: Optional[str] = None
    request_id: Optional[str] = None
    intent: Optional[str] = None
    agent: Optional[str] = None
    pipeline_stage: Optional[str] = None


class RetentionV1(BaseModel):
    ttl_days: Optional[int] = None
    expires_at: Optional[str] = None
    pinned: bool = False
    scope: Literal["session", "global", "task"] = "global"


class KnowledgeRecordV1(BaseModel):
    record_id: str
    kind: KnowledgeKind
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    user_id: Optional[str] = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceV1
    retention: RetentionV1
    created_at: str


class KnowledgeLinkV1(BaseModel):
    relation: Literal["session->lesson", "session->memory_entry", "task->lesson"]
    source_id: str
    target_id: str


class KnowledgeContextMapV1(BaseModel):
    session_id: str
    records: list[KnowledgeRecordV1] = Field(default_factory=list)
    links: list[KnowledgeLinkV1] = Field(default_factory=list)
