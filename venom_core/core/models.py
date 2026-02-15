"""Modele domenowe systemu zadań Venom."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from venom_core.utils.helpers import get_utc_now


class TaskStatus(str, Enum):
    """Status zadania w systemie."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ContextUsed(BaseModel):
    """Informacje o użytym kontekście w zadaniu."""

    lessons: List[str] = Field(default_factory=list)  # Lista ID użytych lekcji
    memory_entries: List[str] = Field(
        default_factory=list
    )  # Lista ID użytych wpisów pamięci


class VenomTask(BaseModel):
    """Wewnętrzne przedstawienie zadania w systemie."""

    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    content: str
    created_at: datetime = Field(default_factory=get_utc_now)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    logs: List[str] = Field(default_factory=list)
    context_history: Dict[str, Any] = Field(
        default_factory=dict
    )  # Słownik kontekstu dla przekazywania danych między krokami wykonania
    context_used: Optional[ContextUsed] = Field(
        default=None, description="Metadane użytego kontekstu (lekcje, pamięć)"
    )

    @field_validator("created_at", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class Intent(BaseModel):
    """Reprezentacja sparsowanej intencji użytkownika."""

    action: str  # Główna akcja (np. "edit", "create", "delete")
    targets: List[str] = Field(default_factory=list)  # Pliki/ścieżki będące celem akcji
    params: Dict[str, Any] = Field(
        default_factory=dict
    )  # Dodatkowe parametry wyciągnięte z tekstu


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
    current_step: int = Field(
        default=0, description="Indeks aktualnie wykonywanego kroku"
    )
