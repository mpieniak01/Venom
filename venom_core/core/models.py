"""Modele danych dla systemu zadań Venom."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
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
    context_history: Dict[str, Any] = Field(
        default_factory=dict
    )  # Historia kontekstu dla przepływu między krokami


class TaskRequest(BaseModel):
    """DTO dla żądania utworzenia zadania."""

    content: str
    images: Optional[List[str]] = None  # Lista base64 lub URL obrazów


class TaskResponse(BaseModel):
    """DTO dla odpowiedzi po utworzeniu zadania."""

    model_config = ConfigDict(use_enum_values=True)

    task_id: UUID
    status: TaskStatus


class ExecutionStep(BaseModel):
    """Pojedynczy krok w planie wykonania."""

    step_number: int = Field(description="Numer kroku w sekwencji")
    agent_type: str = Field(
        description="Typ agenta do wykonania (RESEARCHER, CODER, LIBRARIAN)"
    )
    instruction: str = Field(description="Instrukcja dla agenta")
    depends_on: Optional[int] = Field(
        default=None, description="Numer kroku od którego zależy ten krok"
    )
    result: Optional[str] = Field(default=None, description="Wynik wykonania kroku")


class ExecutionPlan(BaseModel):
    """Plan wykonania złożonego zadania."""

    goal: str = Field(description="Główny cel użytkownika")
    steps: List[ExecutionStep] = Field(
        default_factory=list, description="Lista kroków do wykonania"
    )
    current_step: int = Field(default=0, description="Indeks aktualnie wykonywanego kroku")
