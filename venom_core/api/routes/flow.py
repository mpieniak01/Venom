"""Moduł: routes/flow - Endpointy API dla Flow Inspector (wizualizacja procesów decyzyjnych)."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["flow"])


# Modele dla Flow Inspector
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


# Dependency - będzie ustawione w main.py
_request_tracer = None


def set_dependencies(request_tracer):
    """Ustaw zależności dla routera."""
    global _request_tracer
    _request_tracer = request_tracer


@router.get("/flow/{task_id}", response_model=FlowTraceResponse)
async def get_flow_trace(task_id: UUID):
    """
    Pobiera szczegółowy ślad przepływu zadania dla Flow Inspector.

    Zwraca dane w formacie gotowym do wizualizacji z Mermaid.js,
    ze szczególnym uwzględnieniem "Decision Gates" (bramek decyzyjnych).

    Args:
        task_id: UUID zadania

    Returns:
        Szczegółowe informacje o przepływie z diagramem Mermaid

    Raises:
        HTTPException: 404 jeśli zadanie nie istnieje
        HTTPException: 503 jeśli RequestTracer nie jest dostępny
    """
    if _request_tracer is None:
        raise HTTPException(status_code=503, detail="RequestTracer nie jest dostępny")

    trace = _request_tracer.get_trace(task_id)
    if trace is None:
        raise HTTPException(
            status_code=404, detail=f"Zadanie {task_id} nie istnieje w historii"
        )

    duration = None
    if trace.finished_at:
        duration = (trace.finished_at - trace.created_at).total_seconds()

    # Konwertuj steps do FlowStep z oznaczeniem Decision Gates
    flow_steps = []
    for step in trace.steps:
        is_decision_gate = step.component == "DecisionGate"
        flow_steps.append(
            FlowStep(
                component=step.component,
                action=step.action,
                timestamp=step.timestamp.isoformat(),
                status=step.status,
                details=step.details,
                is_decision_gate=is_decision_gate,
            )
        )

    # Generuj diagram Mermaid.js
    mermaid_diagram = _generate_mermaid_diagram(trace, flow_steps)

    return FlowTraceResponse(
        request_id=trace.request_id,
        prompt=trace.prompt,
        status=trace.status,
        created_at=trace.created_at.isoformat(),
        finished_at=trace.finished_at.isoformat() if trace.finished_at else None,
        duration_seconds=duration,
        steps=flow_steps,
        mermaid_diagram=mermaid_diagram,
    )


def _generate_mermaid_diagram(trace, flow_steps: list[FlowStep]) -> str:
    """
    Generuje diagram Mermaid.js Sequence Diagram z przepływu zadania.

    Args:
        trace: Obiekt RequestTrace
        flow_steps: Lista kroków przepływu

    Returns:
        String z kodem Mermaid.js
    """
    lines = ["sequenceDiagram"]
    lines.append("    autonumber")

    # Dodaj uczestników
    participants = set()
    participants.add("User")

    for step in flow_steps:
        participants.add(step.component)

    # Definicje uczestników (opcjonalne, Mermaid sam je wykryje)
    for participant in sorted(participants):
        if participant != "User":
            lines.append(f"    participant {participant}")

    # Dodaj interakcje
    lines.append("")
    lines.append(f'    User->>Orchestrator: {trace.prompt[:50]}...')

    last_component = "Orchestrator"

    for step in flow_steps:
        component = step.component
        action = step.action
        details = step.details or ""

        # Formatuj wiadomość
        if step.is_decision_gate:
            # Decision Gate - specjalne podświetlenie
            message = f"🔀 {action}: {details[:40]}"
            lines.append(f"    Note over {component}: {message}")
        else:
            # Standardowa interakcja
            arrow = "->>" if step.status == "ok" else "--x"
            message = f"{action}"
            if details:
                message += f": {details[:40]}"

            # Rysuj strzałkę od ostatniego komponentu
            if component != last_component:
                lines.append(f"    {last_component}{arrow}{component}: {message}")
                last_component = component
            else:
                # Ten sam komponent - użyj notatki
                lines.append(f"    Note right of {component}: {message}")

    # Dodaj zwrot do użytkownika
    if trace.status == "COMPLETED":
        lines.append(f"    {last_component}->>User: ✅ Task completed")
    elif trace.status == "FAILED":
        lines.append(f"    {last_component}--xUser: ❌ Task failed")
    elif trace.status == "PROCESSING":
        lines.append(f"    Note over {last_component}: ⏳ Processing...")

    return "\n".join(lines)
