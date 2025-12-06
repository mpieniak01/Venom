"""Modele danych dla systemu zadań Venom."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    """Status zadania w systemie."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VenomTask(BaseModel):
    """Wewnętrzne przedstawienie zadania w systemie."""

    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    logs: List[str] = Field(default_factory=list)


class TaskRequest(BaseModel):
    """DTO dla żądania utworzenia zadania."""

    content: str


class TaskResponse(BaseModel):
    """DTO dla odpowiedzi po utworzeniu zadania."""

    model_config = ConfigDict(use_enum_values=True)

    task_id: UUID
    status: TaskStatus
