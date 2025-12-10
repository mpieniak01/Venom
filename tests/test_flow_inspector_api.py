"""Testy jednostkowe dla Flow Inspector API endpoint."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from venom_core.core.tracer import RequestTracer, TraceStatus
from venom_core.main import app


@pytest.fixture
def tracer():
    """Fixture dla RequestTracer."""
    return RequestTracer(watchdog_timeout_minutes=5)


@pytest.fixture
def client(tracer):
    """Fixture dla FastAPI TestClient z skonfigurowanym tracerem."""
    # Import i ustaw zależności
    from venom_core.api.routes import flow as flow_routes

    flow_routes.set_dependencies(tracer)

    return TestClient(app)


@pytest.fixture
def sample_task_with_flow(tracer):
    """Fixture tworzący przykładowe zadanie z przepływem decyzyjnym."""
    task_id = uuid4()

    # Utwórz trace
    tracer.create_trace(task_id, "Wygeneruj kod funkcji sortującej")

    # Dodaj kroki symulujące przepływ decyzyjny
    tracer.add_step(
        task_id, "User", "submit_request", status="ok", details="Request received"
    )
    tracer.add_step(task_id, "Orchestrator", "start_processing", status="ok")
    tracer.add_step(
        task_id,
        "Orchestrator",
        "classify_intent",
        status="ok",
        details="Intent: CODE_GENERATION",
    )
    # Decision Gate
    tracer.add_step(
        task_id,
        "DecisionGate",
        "select_code_review_loop",
        status="ok",
        details="💻 Routing to Coder-Critic Review Loop",
    )
    tracer.add_step(
        task_id,
        "CoderAgent",
        "process_task",
        status="ok",
        details="Task processed successfully",
    )
    tracer.add_step(task_id, "System", "complete", status="ok", details="Response sent")

    # Zaktualizuj status
    tracer.update_status(task_id, TraceStatus.COMPLETED)

    return task_id


def test_get_flow_trace_success(client, sample_task_with_flow):
    """Test pobierania danych przepływu dla istniejącego zadania."""
    response = client.get(f"/api/v1/flow/{sample_task_with_flow}")

    assert response.status_code == 200
    data = response.json()

    # Sprawdź podstawowe pola
    assert data["request_id"] == str(sample_task_with_flow)
    assert data["status"] == "COMPLETED"
    assert data["prompt"] == "Wygeneruj kod funkcji sortującej"
    assert data["duration_seconds"] is not None

    # Sprawdź kroki
    assert len(data["steps"]) == 6
    assert any(step["is_decision_gate"] for step in data["steps"])

    # Sprawdź diagram Mermaid
    assert "sequenceDiagram" in data["mermaid_diagram"]
    assert "DecisionGate" in data["mermaid_diagram"]


def test_get_flow_trace_identifies_decision_gates(client, sample_task_with_flow):
    """Test czy Decision Gates są prawidłowo oznaczane."""
    response = client.get(f"/api/v1/flow/{sample_task_with_flow}")

    assert response.status_code == 200
    data = response.json()

    # Znajdź Decision Gate step
    decision_gates = [step for step in data["steps"] if step["is_decision_gate"]]
    assert len(decision_gates) == 1

    gate = decision_gates[0]
    assert gate["component"] == "DecisionGate"
    assert gate["action"] == "select_code_review_loop"
    assert "Routing to Coder-Critic" in gate["details"]


def test_get_flow_trace_mermaid_diagram_structure(client, sample_task_with_flow):
    """Test struktury wygenerowanego diagramu Mermaid."""
    response = client.get(f"/api/v1/flow/{sample_task_with_flow}")

    assert response.status_code == 200
    data = response.json()

    diagram = data["mermaid_diagram"]

    # Sprawdź podstawowe elementy diagramu
    assert "sequenceDiagram" in diagram
    assert "autonumber" in diagram
    assert "User->>Orchestrator" in diagram
    assert "Note over DecisionGate" in diagram  # Decision Gates jako notatki
    assert "✅ Task completed" in diagram  # Status completion


def test_get_flow_trace_nonexistent_task(client, tracer):
    """Test pobierania danych dla nieistniejącego zadania."""
    nonexistent_id = uuid4()
    response = client.get(f"/api/v1/flow/{nonexistent_id}")

    assert response.status_code == 404
    assert "nie istnieje w historii" in response.json()["detail"]


def test_get_flow_trace_processing_task(client, tracer):
    """Test pobierania danych dla zadania w trakcie przetwarzania."""
    task_id = uuid4()

    # Utwórz trace w stanie PROCESSING
    tracer.create_trace(task_id, "Test task in progress")
    tracer.update_status(task_id, TraceStatus.PROCESSING)
    tracer.add_step(task_id, "Orchestrator", "start_processing", status="ok")

    response = client.get(f"/api/v1/flow/{task_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "PROCESSING"
    assert data["finished_at"] is None
    assert data["duration_seconds"] is None
    assert "⏳ Processing..." in data["mermaid_diagram"]


def test_get_flow_trace_failed_task(client, tracer):
    """Test pobierania danych dla zadania zakończonego błędem."""
    task_id = uuid4()

    # Utwórz trace w stanie FAILED
    tracer.create_trace(task_id, "Test failed task")
    tracer.add_step(task_id, "Orchestrator", "start_processing", status="ok")
    tracer.add_step(
        task_id, "System", "error", status="error", details="Connection timeout"
    )
    tracer.update_status(task_id, TraceStatus.FAILED)

    response = client.get(f"/api/v1/flow/{task_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "FAILED"
    assert data["finished_at"] is not None
    assert "❌ Task failed" in data["mermaid_diagram"]

    # Sprawdź czy krok błędu jest oznaczony
    error_steps = [step for step in data["steps"] if step["status"] == "error"]
    assert len(error_steps) == 1
    assert error_steps[0]["details"] == "Connection timeout"


def test_get_flow_trace_with_council_decision(client, tracer):
    """Test przepływu z decyzją Council mode."""
    task_id = uuid4()

    # Utwórz trace z decyzją Council
    tracer.create_trace(task_id, "Złożone zadanie wymagające współpracy")
    tracer.add_step(task_id, "Orchestrator", "start_processing", status="ok")
    tracer.add_step(
        task_id,
        "Orchestrator",
        "classify_intent",
        status="ok",
        details="Intent: COMPLEX_PLANNING",
    )
    # Decision Gate: Council mode
    tracer.add_step(
        task_id,
        "DecisionGate",
        "select_council_mode",
        status="ok",
        details="🏛️ Complex task detected -> Council Mode",
    )
    tracer.add_step(
        task_id,
        "CouncilFlow",
        "run_discussion",
        status="ok",
        details="Council consensus reached",
    )
    tracer.update_status(task_id, TraceStatus.COMPLETED)

    response = client.get(f"/api/v1/flow/{task_id}")

    assert response.status_code == 200
    data = response.json()

    # Sprawdź czy Decision Gate dla Council jest obecny
    decision_gates = [step for step in data["steps"] if step["is_decision_gate"]]
    assert len(decision_gates) == 1
    assert "Council Mode" in decision_gates[0]["details"]

    # Sprawdź diagram
    assert "DecisionGate" in data["mermaid_diagram"]
    assert "CouncilFlow" in data["mermaid_diagram"]


def test_flow_endpoint_without_tracer(client):
    """Test endpointu gdy RequestTracer nie jest dostępny."""
    # Import i wyczyść zależności
    from venom_core.api.routes import flow as flow_routes

    flow_routes.set_dependencies(None)

    task_id = uuid4()
    response = client.get(f"/api/v1/flow/{task_id}")

    assert response.status_code == 503
    assert "RequestTracer nie jest dostępny" in response.json()["detail"]
