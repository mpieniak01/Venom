"""Moduł: routes/flow - Endpointy API dla Flow Inspector (wizualizacja procesów decyzyjnych)."""

import unicodedata
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException

from venom_core.api.routes import system_deps
from venom_core.api.schemas.flow import FlowStep, FlowTraceResponse
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["flow"])

# Stałe konfiguracyjne
MAX_MESSAGE_LENGTH = 40  # Maksymalna długość wiadomości w diagramie Mermaid
MAX_PROMPT_LENGTH = 50  # Maksymalna długość promptu w diagramie


def _get_request_tracer():
    return system_deps.get_request_tracer()


def _build_flow_steps(trace) -> list[FlowStep]:
    flow_steps = []
    for step in trace.steps:
        flow_steps.append(
            FlowStep(
                component=step.component,
                action=step.action,
                timestamp=step.timestamp.isoformat(),
                status=step.status,
                details=step.details,
                is_decision_gate=step.component == "DecisionGate",
            )
        )
    return flow_steps


def _build_duration_seconds(trace) -> Optional[float]:
    if not trace.finished_at:
        return None
    return (trace.finished_at - trace.created_at).total_seconds()


@router.get(
    "/flow/{task_id}",
    response_model=FlowTraceResponse,
    responses={
        404: {"description": "Zadanie nie istnieje w historii"},
        503: {"description": "RequestTracer nie jest dostępny"},
    },
)
def get_flow_trace(task_id: UUID):
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
    request_tracer = _get_request_tracer()
    if request_tracer is None:
        raise HTTPException(status_code=503, detail="RequestTracer nie jest dostępny")

    trace = request_tracer.get_trace(task_id)
    if trace is None:
        raise HTTPException(
            status_code=404, detail=f"Zadanie {task_id} nie istnieje w historii"
        )

    duration = _build_duration_seconds(trace)
    flow_steps = _build_flow_steps(trace)

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


def _sanitize_mermaid_text(text: str) -> str:
    cleaned = text.replace("\n", " ").replace("\r", " ")
    cleaned = "".join(
        char for char in cleaned if not unicodedata.category(char).startswith("So")
    )
    safe = []
    for char in cleaned:
        if char.isalnum() or char in " .,:/_-":
            safe.append(char)
        else:
            safe.append(" ")
    return "".join(safe)


def _trim_details(details: str) -> str:
    if len(details) <= MAX_MESSAGE_LENGTH:
        return details
    return details[:MAX_MESSAGE_LENGTH] + "..."


def _build_error_message(trace, component: str, lines: list[str]) -> str:
    error_details = trace.error_details or {}
    if trace.error_code != "execution_contract_violation":
        if trace.error_code == "routing_mismatch":
            expected_hash = error_details.get("expected_hash") or ""
            actual_hash = error_details.get("actual_hash") or ""
            return _sanitize_mermaid_text(
                f"routing.mismatch expected={expected_hash} actual={actual_hash}"
            )
        return _sanitize_mermaid_text(f"execution.failed: {trace.error_code}")

    missing = error_details.get("missing") or []
    missing_label = ""
    if isinstance(missing, list) and missing:
        missing_label = f" missing={missing[0]}"
    lines.append(
        f"    Note over {component}: "
        f"{_sanitize_mermaid_text('Decision: execution_ready=false')}"
    )
    return _sanitize_mermaid_text(f"execution.precheck.failed{missing_label}")


def _build_decision_gate_note(step: FlowStep) -> str:
    details = _sanitize_mermaid_text(step.details or "")
    detail_text = _trim_details(details)
    message = _sanitize_mermaid_text(f"Decision: {step.action}: {detail_text}")
    return f"    Note over {step.component}: {message}"


def _build_step_message(step: FlowStep) -> str:
    details = _sanitize_mermaid_text(step.details or "")
    message = _sanitize_mermaid_text(step.action)
    if details:
        message += f": {_trim_details(details)}"
    return message


def _build_completion_line(trace, last_component: str) -> str:
    if trace.status == "COMPLETED":
        return f"    {last_component}->>User: Task completed"
    if trace.status == "FAILED":
        return f"    {last_component}--xUser: Task failed"
    if trace.status == "PROCESSING":
        return f"    Note over {last_component}: Processing..."
    return ""


def _build_prompt_line(prompt: str) -> str:
    prompt_text = prompt[:MAX_PROMPT_LENGTH]
    if len(prompt) > MAX_PROMPT_LENGTH:
        prompt_text += "..."
    return f"    User->>Orchestrator: {_sanitize_mermaid_text(prompt_text)}"


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
    participants = {"User"}

    for step in flow_steps:
        participants.add(step.component)

    # Definicje uczestników (jawne, żeby uniknąć błędów renderingu)
    for participant in sorted(participants):
        lines.append(f"    participant {participant}")

    # Dodaj interakcje
    lines.append("")
    lines.append(_build_prompt_line(trace.prompt))

    last_component = "Orchestrator"

    for step in flow_steps:
        if step.is_decision_gate:
            lines.append(_build_decision_gate_note(step))
            continue

        component = step.component
        arrow = "->>" if step.status == "ok" else "--x"
        message = _build_step_message(step)

        if component != last_component:
            if step.action == "error" and trace.error_code:
                message = _build_error_message(trace, component, lines)
            lines.append(f"    {last_component}{arrow}{component}: {message}")
            last_component = component
            continue

        lines.append(f"    Note right of {component}: {message}")

    # Dodaj zwrot do użytkownika
    completion_line = _build_completion_line(trace, last_component)
    if completion_line:
        lines.append(completion_line)

    return "\n".join(lines)
