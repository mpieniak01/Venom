"""Testy jednostkowe dla generowania diagramu Mermaid w Flow Inspector."""

from uuid import uuid4

import pytest

from venom_core.api.routes.flow import FlowStep, _generate_mermaid_diagram
from venom_core.core.tracer import RequestTracer, TraceStatus


@pytest.fixture
def tracer():
    """Fixture dla RequestTracer."""
    return RequestTracer(watchdog_timeout_minutes=5)


def test_generate_mermaid_diagram_basic_flow(tracer):
    """Test generowania podstawowego diagramu Mermaid."""
    task_id = uuid4()
    tracer.create_trace(task_id, "Test request")
    tracer.add_step(task_id, "User", "submit_request", status="ok")
    tracer.add_step(task_id, "Orchestrator", "start_processing", status="ok")
    tracer.add_step(task_id, "CoderAgent", "process_task", status="ok")
    tracer.update_status(task_id, TraceStatus.COMPLETED)

    trace = tracer.get_trace(task_id)

    # Konwertuj steps do FlowStep
    flow_steps = [
        FlowStep(
            component=step.component,
            action=step.action,
            timestamp=step.timestamp.isoformat(),
            status=step.status,
            details=step.details,
            is_decision_gate=False,
        )
        for step in trace.steps
    ]

    diagram = _generate_mermaid_diagram(trace, flow_steps)

    # Sprawdź podstawowe elementy
    assert "sequenceDiagram" in diagram
    assert "autonumber" in diagram
    assert "User->>Orchestrator" in diagram
    assert "✅ Task completed" in diagram


def test_generate_mermaid_diagram_with_decision_gate(tracer):
    """Test generowania diagramu z Decision Gate."""
    task_id = uuid4()
    tracer.create_trace(task_id, "Test with decision gate")
    tracer.add_step(
        task_id,
        "Orchestrator",
        "classify_intent",
        status="ok",
        details="Intent: CODE_GENERATION",
    )
    tracer.add_step(
        task_id,
        "DecisionGate",
        "select_code_review_loop",
        status="ok",
        details="🔀 Routing to Coder-Critic",
    )
    tracer.add_step(task_id, "CoderAgent", "process_task", status="ok")
    tracer.update_status(task_id, TraceStatus.COMPLETED)

    trace = tracer.get_trace(task_id)

    # Konwertuj steps do FlowStep z oznaczeniem Decision Gate
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

    diagram = _generate_mermaid_diagram(trace, flow_steps)

    # Sprawdź czy Decision Gate jest jako notatka
    assert "Note over DecisionGate" in diagram
    assert "🔀" in diagram


def test_generate_mermaid_diagram_failed_task(tracer):
    """Test generowania diagramu dla zadania zakończonego błędem."""
    task_id = uuid4()
    tracer.create_trace(task_id, "Failed task")
    tracer.add_step(task_id, "Orchestrator", "start_processing", status="ok")
    tracer.add_step(
        task_id, "System", "error", status="error", details="Connection timeout"
    )
    tracer.update_status(task_id, TraceStatus.FAILED)

    trace = tracer.get_trace(task_id)

    flow_steps = [
        FlowStep(
            component=step.component,
            action=step.action,
            timestamp=step.timestamp.isoformat(),
            status=step.status,
            details=step.details,
            is_decision_gate=False,
        )
        for step in trace.steps
    ]

    diagram = _generate_mermaid_diagram(trace, flow_steps)

    # Sprawdź czy jest oznaczenie błędu
    assert "❌ Task failed" in diagram
    assert "--x" in diagram  # Linia przerywana dla błędu


def test_generate_mermaid_diagram_processing_task(tracer):
    """Test generowania diagramu dla zadania w trakcie przetwarzania."""
    task_id = uuid4()
    tracer.create_trace(task_id, "Processing task")
    tracer.add_step(task_id, "Orchestrator", "start_processing", status="ok")
    tracer.update_status(task_id, TraceStatus.PROCESSING)

    trace = tracer.get_trace(task_id)

    flow_steps = [
        FlowStep(
            component=step.component,
            action=step.action,
            timestamp=step.timestamp.isoformat(),
            status=step.status,
            details=step.details,
            is_decision_gate=False,
        )
        for step in trace.steps
    ]

    diagram = _generate_mermaid_diagram(trace, flow_steps)

    # Sprawdź czy jest oznaczenie przetwarzania
    assert "⏳ Processing..." in diagram


def test_generate_mermaid_diagram_multiple_decision_gates(tracer):
    """Test generowania diagramu z wieloma Decision Gates."""
    task_id = uuid4()
    trace = tracer.create_trace(task_id, "Complex flow")
    tracer.add_step(task_id, "Orchestrator", "classify_intent", status="ok")
    tracer.add_step(
        task_id,
        "DecisionGate",
        "check_permissions",
        status="ok",
        details="🔐 Permission check passed",
    )
    tracer.add_step(
        task_id,
        "DecisionGate",
        "select_council_mode",
        status="ok",
        details="🏛️ Council Mode selected",
    )
    tracer.add_step(task_id, "CouncilFlow", "run_discussion", status="ok")
    tracer.update_status(task_id, TraceStatus.COMPLETED)

    trace = tracer.get_trace(task_id)

    flow_steps = [
        FlowStep(
            component=step.component,
            action=step.action,
            timestamp=step.timestamp.isoformat(),
            status=step.status,
            details=step.details,
            is_decision_gate=(step.component == "DecisionGate"),
        )
        for step in trace.steps
    ]

    diagram = _generate_mermaid_diagram(trace, flow_steps)

    # Sprawdź czy wszystkie Decision Gates są w diagramie
    assert diagram.count("Note over DecisionGate") == 2
    assert "🔐" in diagram
    assert "🏛️" in diagram


def test_generate_mermaid_diagram_truncates_long_details(tracer):
    """Test czy długie szczegóły są obcinane w diagramie."""
    task_id = uuid4()
    tracer.create_trace(task_id, "Task with long details")

    long_details = "A" * 100  # Bardzo długi string
    tracer.add_step(task_id, "Agent", "process", status="ok", details=long_details)
    tracer.update_status(task_id, TraceStatus.COMPLETED)

    trace = tracer.get_trace(task_id)

    flow_steps = [
        FlowStep(
            component=step.component,
            action=step.action,
            timestamp=step.timestamp.isoformat(),
            status=step.status,
            details=step.details,
            is_decision_gate=False,
        )
        for step in trace.steps
    ]

    diagram = _generate_mermaid_diagram(trace, flow_steps)

    # Szczegóły powinny być obcięte do 40 znaków
    assert "A" * 40 in diagram
    assert "A" * 50 not in diagram
