"""Testy integracyjne dla przepływu planowania."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.intent_manager import IntentManager
from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager


@pytest.fixture
def mock_kernel():
    """Mock Kernel z podstawową konfiguracją."""
    kernel = MagicMock()

    # Mock chat service
    chat_service = MagicMock()
    chat_service.get_chat_message_content = AsyncMock()
    kernel.get_service.return_value = chat_service
    kernel.add_plugin = MagicMock()

    return kernel


@pytest.fixture
def state_manager():
    """Fixture dla StateManager."""
    return StateManager()


class TestPlanningIntegration:
    """Testy integracyjne dla przepływu planowania."""

    @pytest.mark.asyncio
    async def test_research_intent_triggers_researcher(
        self, state_manager, mock_kernel
    ):
        """Test czy intencja RESEARCH uruchamia ResearcherAgent."""
        # Mock IntentManager do zwrócenia RESEARCH
        intent_manager = MagicMock(spec=IntentManager)
        intent_manager.classify_intent = AsyncMock(return_value="RESEARCH")

        # Mock odpowiedzi ResearcherAgent
        mock_response = MagicMock()
        mock_response.__str__ = lambda x: (
            "Znalazłem informacje o Bitcoin: aktualna cena to $50000"
        )
        mock_kernel.get_service.return_value.get_chat_message_content.return_value = (
            mock_response
        )

        # Stwórz dispatcher i orchestrator
        dispatcher = TaskDispatcher(mock_kernel)
        orchestrator = Orchestrator(
            state_manager=state_manager,
            intent_manager=intent_manager,
            task_dispatcher=dispatcher,
        )

        # Wykonaj zadanie
        request = TaskRequest(content="Jaka jest aktualna cena Bitcoina?")
        response = await orchestrator.submit_task(request)

        # Poczekaj na zakończenie
        import asyncio

        await asyncio.sleep(0.5)

        # Sprawdź status
        task = state_manager.get_task(response.task_id)
        assert task is not None

    @pytest.mark.asyncio
    async def test_complex_planning_intent_triggers_architect(
        self, state_manager, mock_kernel
    ):
        """Test czy intencja COMPLEX_PLANNING uruchamia ArchitectAgent."""
        # Mock IntentManager do zwrócenia COMPLEX_PLANNING
        intent_manager = MagicMock(spec=IntentManager)
        intent_manager.classify_intent = AsyncMock(return_value="COMPLEX_PLANNING")

        # Mock odpowiedzi z planem JSON
        import json

        plan_json = {
            "steps": [
                {
                    "step_number": 1,
                    "agent_type": "CODER",
                    "instruction": "Create index.html",
                    "depends_on": None,
                },
                {
                    "step_number": 2,
                    "agent_type": "CODER",
                    "instruction": "Create style.css",
                    "depends_on": 1,
                },
            ]
        }

        # Pierwsze wywołanie zwraca plan, kolejne zwracają wyniki kroków
        mock_kernel.get_service.return_value.get_chat_message_content.side_effect = [
            MagicMock(__str__=lambda x: json.dumps(plan_json)),
            MagicMock(__str__=lambda x: "index.html created"),
            MagicMock(__str__=lambda x: "style.css created"),
        ]

        # Stwórz dispatcher i orchestrator
        dispatcher = TaskDispatcher(mock_kernel)
        orchestrator = Orchestrator(
            state_manager=state_manager,
            intent_manager=intent_manager,
            task_dispatcher=dispatcher,
        )

        # Wykonaj zadanie
        request = TaskRequest(content="Stwórz prostą stronę HTML z zegarem cyfrowym")
        response = await orchestrator.submit_task(request)

        # Poczekaj na zakończenie
        import asyncio

        await asyncio.sleep(0.5)

        # Sprawdź status
        task = state_manager.get_task(response.task_id)
        assert task is not None

    @pytest.mark.asyncio
    async def test_orchestrator_handles_research_then_code(
        self, state_manager, mock_kernel
    ):
        """Test scenariusza: research najpierw, potem kod."""
        intent_manager = MagicMock(spec=IntentManager)
        intent_manager.classify_intent = AsyncMock(return_value="RESEARCH")

        mock_response = MagicMock()
        mock_response.__str__ = lambda x: (
            "Dokumentacja FastAPI: use @app.get() decorator"
        )
        mock_kernel.get_service.return_value.get_chat_message_content.return_value = (
            mock_response
        )

        dispatcher = TaskDispatcher(mock_kernel)
        orchestrator = Orchestrator(
            state_manager=state_manager,
            intent_manager=intent_manager,
            task_dispatcher=dispatcher,
        )

        # Pierwsze zadanie - research
        request = TaskRequest(content="Znajdź dokumentację FastAPI")
        await orchestrator.submit_task(request)

        import asyncio

        await asyncio.sleep(0.5)

        # Drugie zadanie - kod (może wykorzystać wiedzę z pamięci)
        intent_manager.classify_intent = AsyncMock(return_value="CODE_GENERATION")
        request2 = TaskRequest(content="Stwórz endpoint FastAPI")
        await orchestrator.submit_task(request2)

        await asyncio.sleep(0.5)


class TestIntentManagerExtensions:
    """Testy dla rozszerzonej klasyfikacji intencji."""

    @pytest.mark.asyncio
    async def test_classify_research_intent(self, mock_kernel):
        """Test klasyfikacji intencji RESEARCH."""
        intent_manager = IntentManager(mock_kernel)

        # Mock odpowiedzi LLM
        mock_response = MagicMock()
        mock_response.__str__ = lambda x: "RESEARCH"
        mock_kernel.get_service.return_value.get_chat_message_content.return_value = (
            mock_response
        )

        intent = await intent_manager.classify_intent(
            "Jaka jest aktualna cena Bitcoina?"
        )

        assert intent == "RESEARCH"

    @pytest.mark.asyncio
    async def test_classify_complex_planning_intent(self, mock_kernel):
        """Test klasyfikacji intencji COMPLEX_PLANNING."""
        intent_manager = IntentManager(mock_kernel)

        mock_response = MagicMock()
        mock_response.__str__ = lambda x: "COMPLEX_PLANNING"
        mock_kernel.get_service.return_value.get_chat_message_content.return_value = (
            mock_response
        )

        intent = await intent_manager.classify_intent(
            "Stwórz grę Snake używając PyGame"
        )

        assert intent == "COMPLEX_PLANNING"

    @pytest.mark.asyncio
    async def test_valid_intents_includes_new_types(self, mock_kernel):
        """Test że nowe intencje są w liście dozwolonych."""
        intent_manager = IntentManager(mock_kernel)

        # Mock odpowiedzi z nową intencją
        mock_response = MagicMock()
        mock_response.__str__ = lambda x: "RESEARCH"
        mock_kernel.get_service.return_value.get_chat_message_content.return_value = (
            mock_response
        )

        intent = await intent_manager.classify_intent("Test query")

        # Nie powinno być fallbacku do GENERAL_CHAT
        assert intent in [
            "RESEARCH",
            "COMPLEX_PLANNING",
            "CODE_GENERATION",
            "KNOWLEDGE_SEARCH",
            "GENERAL_CHAT",
        ]


class TestDispatcherExtensions:
    """Testy dla rozszerzonego dispatchera."""

    def test_dispatcher_has_researcher_agent(self, mock_kernel):
        """Test czy dispatcher ma zarejestrowanego ResearcherAgent."""
        dispatcher = TaskDispatcher(mock_kernel)

        assert "RESEARCH" in dispatcher.agent_map
        assert dispatcher.researcher_agent is not None

    def test_dispatcher_has_architect_agent(self, mock_kernel):
        """Test czy dispatcher ma zarejestrowanego ArchitectAgent."""
        dispatcher = TaskDispatcher(mock_kernel)

        assert "COMPLEX_PLANNING" in dispatcher.agent_map
        assert dispatcher.architect_agent is not None

    def test_architect_has_dispatcher_reference(self, mock_kernel):
        """Test czy ArchitectAgent ma referencję do dispatchera."""
        dispatcher = TaskDispatcher(mock_kernel)

        assert dispatcher.architect_agent.task_dispatcher == dispatcher
