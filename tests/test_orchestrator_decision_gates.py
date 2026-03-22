"""Testy dla wzbogaconego logowania Decision Gates w Orchestrator."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tests.helpers.url_fixtures import MOCK_HTTP, local_runtime_id
from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.orchestrator import orchestrator_flows as flows
from venom_core.core.orchestrator.orchestrator_dispatch import (
    _prepare_intent_and_context,
)
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer
from venom_core.utils.llm_runtime import LLMRuntimeInfo


@pytest.fixture
def mock_runtime_info():
    """Mock dla get_active_llm_runtime."""
    return LLMRuntimeInfo(
        provider="local",
        model_name="mock-model",
        endpoint=MOCK_HTTP,
        service_type="local",
        mode="LOCAL",
        config_hash="abc123456789",
        runtime_id=local_runtime_id(MOCK_HTTP),
    )


@pytest.fixture(autouse=True)
def patch_runtime(mock_runtime_info):
    """Automatycznie patchuje runtime dla wszystkich testów."""
    with (
        patch(
            "venom_core.utils.llm_runtime.get_active_llm_runtime",
            return_value=mock_runtime_info,
        ),
    ):
        with (
            patch("venom_core.config.SETTINGS") as mock_settings,
            patch(
                "venom_core.core.orchestrator.orchestrator_dispatch.SETTINGS",
                new=mock_settings,
            ),
        ):
            mock_settings.LLM_CONFIG_HASH = "abc123456789"
            yield


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
    intent_manager.requires_tool = MagicMock(return_value=False)

    # Mock task dispatcher
    task_dispatcher = MagicMock()
    task_dispatcher.agent_map = {}
    task_dispatcher.goal_store = None
    task_dispatcher.dispatch = AsyncMock(return_value="Mocked result")
    task_dispatcher.kernel = object()

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
    gate = next(step for step in decision_gate_steps if step.action == "route_help")
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
    gate = next(
        step for step in decision_gate_steps if step.action == "select_code_review_loop"
    )
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
    task_after = orchestrator.state_manager.get_task(task_id)
    assert task_after is not None
    assert task_after.context_history.get("execution_mode") == "browser_automation"
    assert task_after.context_history.get("browser_profile") == "functional"
    browser_contract = task_after.context_history.get("browser_execution_contract")
    assert browser_contract is not None
    assert browser_contract.get("timeout_seconds") == 60
    assert browser_contract.get("retry_policy", {}).get("max_retries") == 2


@pytest.mark.asyncio
async def test_orchestrator_sets_gui_fallback_metadata_for_desktop_automation_intent(
    orchestrator, request_tracer
):
    task = orchestrator.state_manager.create_task("Kliknij przycisk")
    task_id = task.id

    orchestrator.intent_manager.classify_intent.return_value = "DESKTOP_AUTOMATION"
    mock_agent = MagicMock()
    mock_agent.__class__.__name__ = "AssistantAgent"
    orchestrator.task_dispatcher.agent_map["DESKTOP_AUTOMATION"] = mock_agent

    request_tracer.create_trace(task_id, "Kliknij przycisk")

    from venom_core.core.models import TaskRequest

    await orchestrator._run_task(
        task_id,
        TaskRequest(content="Kliknij przycisk"),
    )

    task_after = orchestrator.state_manager.get_task(task_id)
    assert task_after is not None
    assert task_after.context_history.get("execution_mode") == "gui_fallback"
    assert (
        task_after.context_history.get("fallback_reason") == "intent_requires_gui_path"
    )
    assert (
        task_after.context_history.get("execution_mode_reason_code")
        == "EXECUTION_MODE_GUI_FALLBACK_INTENT"
    )
    gui_contract = task_after.context_history.get("gui_fallback_contract")
    assert gui_contract is not None
    assert gui_contract.get("autonomy", {}).get("required_level") == "elevated"
    assert gui_contract.get("safety", {}).get("critical_steps_fail_closed") is True
    assert gui_contract.get("safety", {}).get("terminal_blocks_retryable") is False


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


@pytest.mark.asyncio
async def test_prepare_intent_and_context_batches_context_updates(
    orchestrator, request_tracer
):
    task = orchestrator.state_manager.create_task("find docs quickly")
    task_id = task.id

    request_tracer.create_trace(task_id, "find docs quickly")
    orchestrator.intent_manager.classify_intent.return_value = "RESEARCH"
    orchestrator.intent_manager.last_intent_debug = {"source": "heuristic"}
    orchestrator.intent_manager.requires_tool.return_value = False
    orchestrator.context_builder.build_context = AsyncMock(return_value="ctx")

    original_update_context = orchestrator.state_manager.update_context
    orchestrator.state_manager.update_context = MagicMock(wraps=original_update_context)

    request = TaskRequest(
        content="find docs quickly",
        generation_params={"temperature": 0.1},
    )

    intent, context, tool_required, intent_debug = await _prepare_intent_and_context(
        orchestrator,
        task_id,
        request,
        request.content,
        fast_path=False,
    )

    assert intent == "RESEARCH"
    assert context == "ctx"
    assert tool_required is False
    assert intent_debug == {"source": "heuristic"}

    orchestrator.state_manager.update_context.assert_called_once()
    _, update_payload = orchestrator.state_manager.update_context.call_args.args
    assert update_payload["intent_debug"] == {"source": "heuristic"}
    assert update_payload["generation_params"] == {"temperature": 0.1}
    assert update_payload["execution_mode"] == "browser_automation"
    assert update_payload["browser_profile"] == "functional"
    assert update_payload["tool_requirement"] == {
        "required": False,
        "intent": "RESEARCH",
    }


@pytest.mark.asyncio
async def test_run_council_uses_fallback_llm_config_when_local_builder_fails():
    captured_llm_config: dict[str, object] = {}

    class _FakeCouncilConfig:
        def __init__(
            self,
            coder_agent,
            critic_agent,
            architect_agent,
            guardian_agent,
            llm_config,
        ):
            del coder_agent, critic_agent, architect_agent, guardian_agent
            captured_llm_config.update(llm_config)

        @staticmethod
        def create_council():
            group_chat = SimpleNamespace(agents=[SimpleNamespace(name="coder")])
            return ("user_proxy", group_chat, "manager")

    session = SimpleNamespace(
        run=AsyncMock(return_value="ok"),
        get_message_count=lambda: 1,
        get_speakers=lambda: ["coder"],
    )
    orch = SimpleNamespace(
        _council_config=None,
        task_dispatcher=SimpleNamespace(
            coder_agent=object(),
            critic_agent=object(),
            architect_agent=object(),
            kernel=object(),
        ),
        _normalize_council_tuple=lambda value: value,
        _broadcast_event=AsyncMock(),
        state_manager=SimpleNamespace(add_log=MagicMock()),
    )

    with (
        patch(
            "venom_core.core.council.create_local_llm_config",
            side_effect=RuntimeError("missing-local-endpoint"),
        ),
        patch(
            "venom_core.agents.guardian.GuardianAgent",
            return_value=SimpleNamespace(),
        ),
        patch("venom_core.core.council.CouncilConfig", _FakeCouncilConfig),
        patch("venom_core.core.council.CouncilSession", return_value=session),
    ):
        result = await flows.run_council(orch, task_id=uuid4(), context="ctx")

    assert result == "ok"
    assert captured_llm_config["config_list"][0]["model"] == "council-fallback"
