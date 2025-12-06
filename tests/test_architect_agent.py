"""Testy jednostkowe dla ArchitectAgent."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from semantic_kernel import Kernel

from venom_core.agents.architect import ArchitectAgent
from venom_core.core.models import ExecutionPlan, ExecutionStep


@pytest.fixture
def mock_kernel():
    """Fixture dla mockowego Kernel."""
    kernel = MagicMock(spec=Kernel)
    return kernel


@pytest.fixture
def mock_chat_service():
    """Fixture dla mockowego serwisu chat."""
    service = MagicMock()
    service.get_chat_message_content = AsyncMock()
    return service


@pytest.fixture
def mock_dispatcher():
    """Fixture dla mockowego TaskDispatcher."""
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock()
    return dispatcher


@pytest.fixture
def architect_agent(mock_kernel, mock_chat_service):
    """Fixture dla ArchitectAgent."""
    mock_kernel.get_service.return_value = mock_chat_service
    agent = ArchitectAgent(mock_kernel)
    return agent


class TestArchitectAgent:
    """Testy dla ArchitectAgent."""

    def test_initialization(self, mock_kernel):
        """Test inicjalizacji ArchitectAgent."""
        agent = ArchitectAgent(mock_kernel)

        assert agent.kernel == mock_kernel
        assert agent.task_dispatcher is None

    def test_set_dispatcher(self, architect_agent, mock_dispatcher):
        """Test ustawiania dispatchera."""
        architect_agent.set_dispatcher(mock_dispatcher)

        assert architect_agent.task_dispatcher == mock_dispatcher

    @pytest.mark.asyncio
    async def test_create_plan_success(self, architect_agent, mock_chat_service):
        """Test udanego tworzenia planu."""
        # Mock odpowiedzi LLM z planem JSON
        plan_json = {
            "steps": [
                {
                    "step_number": 1,
                    "agent_type": "RESEARCHER",
                    "instruction": "Znajdź dokumentację PyGame",
                    "depends_on": None,
                },
                {
                    "step_number": 2,
                    "agent_type": "CODER",
                    "instruction": "Stwórz plik game.py",
                    "depends_on": 1,
                },
            ]
        }

        mock_response = MagicMock()
        mock_response.__str__ = lambda x: json.dumps(plan_json)
        mock_chat_service.get_chat_message_content.return_value = mock_response

        plan = await architect_agent.create_plan("Stwórz grę Snake")

        assert isinstance(plan, ExecutionPlan)
        assert len(plan.steps) == 2
        assert plan.steps[0].agent_type == "RESEARCHER"
        assert plan.steps[1].agent_type == "CODER"
        assert plan.steps[1].depends_on == 1

    @pytest.mark.asyncio
    async def test_create_plan_with_markdown_json(
        self, architect_agent, mock_chat_service
    ):
        """Test parsowania planu z znacznikami markdown."""
        plan_json = {
            "steps": [
                {
                    "step_number": 1,
                    "agent_type": "CODER",
                    "instruction": "Create HTML file",
                    "depends_on": None,
                }
            ]
        }

        # LLM zwraca JSON w bloku markdown
        mock_response = MagicMock()
        mock_response.__str__ = lambda x: f"```json\n{json.dumps(plan_json)}\n```"
        mock_chat_service.get_chat_message_content.return_value = mock_response

        plan = await architect_agent.create_plan("Create webpage")

        assert isinstance(plan, ExecutionPlan)
        assert len(plan.steps) == 1

    @pytest.mark.asyncio
    async def test_create_plan_invalid_json_fallback(
        self, architect_agent, mock_chat_service
    ):
        """Test fallbacku przy błędnym JSON."""
        mock_response = MagicMock()
        mock_response.__str__ = lambda x: "This is not valid JSON"
        mock_chat_service.get_chat_message_content.return_value = mock_response

        plan = await architect_agent.create_plan("Test task")

        # Powinien zwrócić fallback plan z jednym krokiem CODER
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.steps) == 1
        assert plan.steps[0].agent_type == "CODER"

    @pytest.mark.asyncio
    async def test_execute_plan_without_dispatcher(self, architect_agent):
        """Test wykonywania planu bez ustawionego dispatchera."""
        plan = ExecutionPlan(
            goal="Test",
            steps=[
                ExecutionStep(
                    step_number=1,
                    agent_type="CODER",
                    instruction="Test instruction",
                )
            ],
        )

        result = await architect_agent.execute_plan(plan)

        assert "Błąd" in result
        assert "Brak dispatchera" in result

    @pytest.mark.asyncio
    async def test_execute_plan_success(
        self, architect_agent, mock_dispatcher
    ):
        """Test udanego wykonania planu."""
        architect_agent.set_dispatcher(mock_dispatcher)

        # Mock dispatchera
        mock_dispatcher.dispatch.return_value = "Step completed successfully"

        plan = ExecutionPlan(
            goal="Create project",
            steps=[
                ExecutionStep(
                    step_number=1,
                    agent_type="RESEARCHER",
                    instruction="Find documentation",
                ),
                ExecutionStep(
                    step_number=2,
                    agent_type="CODER",
                    instruction="Write code",
                    depends_on=1,
                ),
            ],
        )

        result = await architect_agent.execute_plan(plan)

        assert "WYKONANIE PLANU" in result
        assert "Create project" in result
        assert "Krok 1" in result
        assert "Krok 2" in result
        assert mock_dispatcher.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_plan_with_context_passing(
        self, architect_agent, mock_dispatcher
    ):
        """Test przekazywania kontekstu między krokami."""
        architect_agent.set_dispatcher(mock_dispatcher)

        # Mock różnych odpowiedzi dla różnych kroków
        mock_dispatcher.dispatch.side_effect = [
            "Result from step 1",
            "Result from step 2",
        ]

        plan = ExecutionPlan(
            goal="Test",
            steps=[
                ExecutionStep(
                    step_number=1,
                    agent_type="RESEARCHER",
                    instruction="Research",
                ),
                ExecutionStep(
                    step_number=2,
                    agent_type="CODER",
                    instruction="Code",
                    depends_on=1,
                ),
            ],
        )

        await architect_agent.execute_plan(plan)

        # Sprawdź czy drugi krok otrzymał kontekst z pierwszego
        second_call_args = mock_dispatcher.dispatch.call_args_list[1]
        context = second_call_args[0][1]  # drugi argument to content

        assert "KONTEKST Z POPRZEDNIEGO KROKU" in context
        assert "Result from step 1" in context

    @pytest.mark.asyncio
    async def test_execute_plan_handles_step_error(
        self, architect_agent, mock_dispatcher
    ):
        """Test obsługi błędu w kroku."""
        architect_agent.set_dispatcher(mock_dispatcher)

        # Pierwszy krok się powiedzie, drugi rzuci błąd
        mock_dispatcher.dispatch.side_effect = [
            "Step 1 success",
            Exception("Step 2 failed"),
        ]

        plan = ExecutionPlan(
            goal="Test",
            steps=[
                ExecutionStep(step_number=1, agent_type="CODER", instruction="Step 1"),
                ExecutionStep(step_number=2, agent_type="CODER", instruction="Step 2"),
            ],
        )

        result = await architect_agent.execute_plan(plan)

        # Plan powinien kontynuować mimo błędu
        assert "BŁĄD" in result
        assert "Step 2 failed" in result
        assert "PLAN ZAKOŃCZONY" in result

    @pytest.mark.asyncio
    async def test_process_creates_and_executes_plan(
        self, architect_agent, mock_dispatcher, mock_chat_service
    ):
        """Test że process() tworzy i wykonuje plan."""
        architect_agent.set_dispatcher(mock_dispatcher)

        # Mock tworzenia planu
        plan_json = {
            "steps": [
                {
                    "step_number": 1,
                    "agent_type": "CODER",
                    "instruction": "Create file",
                    "depends_on": None,
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.__str__ = lambda x: json.dumps(plan_json)
        mock_chat_service.get_chat_message_content.return_value = mock_response

        # Mock wykonania
        mock_dispatcher.dispatch.return_value = "File created"

        result = await architect_agent.process("Create a project")

        assert "WYKONANIE PLANU" in result
        assert "Create a project" in result
        assert mock_dispatcher.dispatch.called
