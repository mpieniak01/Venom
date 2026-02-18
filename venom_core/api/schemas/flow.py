"""Schemas for flow API endpoints."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FlowStep(BaseModel):
    """Pojedynczy krok w przepływie decyzyjnym."""

    component: str
    action: str
    timestamp: str
    status: str
    details: Optional[str] = None
    is_decision_gate: bool = False  # Czy to krok decyzyjny


class FlowTraceResponse(BaseModel):
    """Odpowiedź zawierająca pełny ślad przepływu dla Flow Inspector."""

    request_id: UUID
    prompt: str
    status: str
    created_at: str
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    steps: list[FlowStep]
    mermaid_diagram: str  # Gotowy diagram Mermaid.js
