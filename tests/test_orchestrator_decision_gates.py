"""Testy dla wzbogaconego logowania Decision Gates w Orchestrator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer


@pytest.fixture
def state_manager():
    """Fixture dla StateManager."""
    return StateManager(state_file_path=":memory:")


@pytest.fixture
def request_tracer():
    """Fixture dla RequestTracer."""
    return RequestTracer(watchdog_timeout_minutes=5)


@pytest.fixture
def orchestrator(state_manager, request_tracer):
    """Fixture dla Orchestrator z mockami."""
    # Mock intent manager
    intent_manager = MagicMock()
    intent_manager.classify_intent = AsyncMock()

    # Mock task dispatcher
    task_dispatcher = MagicMock()
    task_dispatcher.agent_map = {}
    task_dispatcher.goal_store = None
    task_dispatcher.dispatch = AsyncMock(return_value="Mocked result")

    orch = Orchestrator(
        state_manager=state_manager,
        intent_manager=intent_manager,
        task_dispatcher=task_dispatcher,
        request_tracer=request_tracer,
    )

    return orch


@pytest.mark.asyncio
async def test_orchestrator_logs_decision_gate_for_help_request(
    orchestrator, request_tracer
):
    """Test czy orchestrator loguje Decision Gate dla HELP_REQUEST."""
    # Setup
    task = orchestrator.state_manager.create_task("Pomóż mi")
    task_id = task.id

    # Mock classify_intent do zwrócenia HELP_REQUEST
    orchestrator.intent_manager.classify_intent.return_value = "HELP_REQUEST"

    # Mock _generate_help_response
    orchestrator._generate_help_response = AsyncMock(return_value="Help text")

    # Utwórz trace
    request_tracer.create_trace(task_id, "Pomóż mi")

    # Wykonaj _run_task
    from venom_core.core.models import TaskRequest

    await orchestrator._run_task(task_id, TaskRequest(content="Pomóż mi"))

    # Sprawdź czy Decision Gate został zalogowany
    trace = request_tracer.get_trace(task_id)
    decision_gate_steps = [
        step for step in trace.steps if step.component == "DecisionGate"
    ]

    assert len(decision_gate_steps) >= 1
    gate = decision_gate_steps[0]
    assert gate.action == "route_help"
    assert "Help System" in gate.details


@pytest.mark.asyncio
async def test_orchestrator_logs_decision_gate_for_code_generation(
    orchestrator, request_tracer
):
    """Test czy orchestrator loguje Decision Gate dla CODE_GENERATION."""
    # Setup
    task = orchestrator.state_manager.create_task("Napisz funkcję sortującą")
    task_id = task.id

    # Mock classify_intent do zwrócenia CODE_GENERATION
    orchestrator.intent_manager.classify_intent.return_value = "CODE_GENERATION"

    # Mock _code_generation_with_review
    orchestrator._code_generation_with_review = AsyncMock(return_value="Generated code")

    # Utwórz trace
    request_tracer.create_trace(task_id, "Napisz funkcję sortującą")

    # Wykonaj _run_task
    from venom_core.core.models import TaskRequest

    await orchestrator._run_task(
        task_id, TaskRequest(content="Napisz funkcję sortującą")
    )

    # Sprawdź czy Decision Gate został zalogowany
    trace = request_tracer.get_trace(task_id)
    decision_gate_steps = [
        step for step in trace.steps if step.component == "DecisionGate"
    ]

    assert len(decision_gate_steps) >= 1
    gate = decision_gate_steps[0]
    assert gate.action == "select_code_review_loop"
    assert "Coder-Critic" in gate.details


@pytest.mark.asyncio
async def test_orchestrator_logs_decision_gate_for_council_mode(
    orchestrator, request_tracer
):
    """Test czy orchestrator loguje Decision Gate dla Council mode."""
    # Setup
    task = orchestrator.state_manager.create_task("Złożone zadanie")
    task_id = task.id

    # Mock classify_intent
    orchestrator.intent_manager.classify_intent.return_value = "COMPLEX_PLANNING"

    # Mock _should_use_council do zwrócenia True
    orchestrator._should_use_council = MagicMock(return_value=True)

    # Mock run_council
    orchestrator.run_council = AsyncMock(return_value="Council result")

    # Utwórz trace
    request_tracer.create_trace(task_id, "Złożone zadanie")

    # Wykonaj _run_task
    from venom_core.core.models import TaskRequest

    await orchestrator._run_task(task_id, TaskRequest(content="Złożone zadanie"))

    # Sprawdź czy Decision Gate został zalogowany
    trace = request_tracer.get_trace(task_id)
    decision_gate_steps = [
        step for step in trace.steps if step.component == "DecisionGate"
    ]

    assert len(decision_gate_steps) >= 1

    # Znajdź Decision Gate dla Council
    council_gates = [g for g in decision_gate_steps if "Council" in g.details]
    assert len(council_gates) == 1
    gate = council_gates[0]
    assert gate.action == "select_council_mode"


@pytest.mark.asyncio
async def test_orchestrator_logs_decision_gate_for_architect_routing(
    orchestrator, request_tracer
):
    """Test czy orchestrator loguje Decision Gate dla routingu do Architekta."""
    # Setup
    task = orchestrator.state_manager.create_task("Zaprojektuj system")
    task_id = task.id

    # Mock classify_intent
    orchestrator.intent_manager.classify_intent.return_value = "COMPLEX_PLANNING"

    # Mock _should_use_council do zwrócenia False (nie Council)
    orchestrator._should_use_council = MagicMock(return_value=False)

    # Utwórz trace
    request_tracer.create_trace(task_id, "Zaprojektuj system")

    # Wykonaj _run_task
    from venom_core.core.models import TaskRequest

    await orchestrator._run_task(task_id, TaskRequest(content="Zaprojektuj system"))

    # Sprawdź czy Decision Gate został zalogowany
    trace = request_tracer.get_trace(task_id)
    decision_gate_steps = [
        step for step in trace.steps if step.component == "DecisionGate"
    ]

    assert len(decision_gate_steps) >= 1

    # Znajdź Decision Gate dla Architect
    architect_gates = [g for g in decision_gate_steps if "Architect" in g.details]
    assert len(architect_gates) == 1
    gate = architect_gates[0]
    assert gate.action == "route_to_architect"


@pytest.mark.asyncio
async def test_orchestrator_logs_decision_gate_for_standard_agent_routing(
    orchestrator, request_tracer
):
    """Test czy orchestrator loguje Decision Gate dla standardowego routingu do agenta."""
    # Setup
    task = orchestrator.state_manager.create_task("Znajdź informacje")
    task_id = task.id

    # Mock classify_intent
    orchestrator.intent_manager.classify_intent.return_value = "RESEARCH"

    # Mock agent w agent_map
    mock_agent = MagicMock()
    mock_agent.__class__.__name__ = "ResearcherAgent"
    orchestrator.task_dispatcher.agent_map["RESEARCH"] = mock_agent

    # Utwórz trace
    request_tracer.create_trace(task_id, "Znajdź informacje")

    # Wykonaj _run_task
    from venom_core.core.models import TaskRequest

    await orchestrator._run_task(task_id, TaskRequest(content="Znajdź informacje"))

    # Sprawdź czy Decision Gate został zalogowany
    trace = request_tracer.get_trace(task_id)
    decision_gate_steps = [
        step for step in trace.steps if step.component == "DecisionGate"
    ]

    assert len(decision_gate_steps) >= 1

    # Znajdź Decision Gate dla standard routing
    routing_gates = [g for g in decision_gate_steps if "Routing to" in g.details]
    assert len(routing_gates) == 1
    gate = routing_gates[0]
    assert gate.action == "route_to_agent"
    assert "ResearcherAgent" in gate.details


@pytest.mark.asyncio
async def test_orchestrator_logs_classify_intent_step(orchestrator, request_tracer):
    """Test czy orchestrator zawsze loguje krok classify_intent."""
    # Setup
    task = orchestrator.state_manager.create_task("Test task")
    task_id = task.id

    # Mock classify_intent
    orchestrator.intent_manager.classify_intent.return_value = "GENERAL_CHAT"

    # Mock agent
    mock_agent = MagicMock()
    mock_agent.__class__.__name__ = "AssistantAgent"
    orchestrator.task_dispatcher.agent_map["GENERAL_CHAT"] = mock_agent

    # Utwórz trace
    request_tracer.create_trace(task_id, "Test task")

    # Wykonaj _run_task
    from venom_core.core.models import TaskRequest

    await orchestrator._run_task(task_id, TaskRequest(content="Test task"))

    # Sprawdź czy krok classify_intent został zalogowany
    trace = request_tracer.get_trace(task_id)
    classify_steps = [step for step in trace.steps if step.action == "classify_intent"]

    assert len(classify_steps) == 1
    step = classify_steps[0]
    assert step.component == "Orchestrator"
    assert "Intent: GENERAL_CHAT" in step.details
