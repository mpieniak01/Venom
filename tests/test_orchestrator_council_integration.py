"""Testy integracyjne dla metody run_council() w Orchestratorze."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from venom_core.core.orchestrator import Orchestrator


@pytest.mark.asyncio
class TestOrchestratorRunCouncilIntegration:
    """Testy integracyjne dla run_council()."""

    def setup_method(self):
        """Setup przed każdym testem."""
        self.state_manager = MagicMock()
        self.event_broadcaster = AsyncMock()
        self.orchestrator = Orchestrator(
            state_manager=self.state_manager, event_broadcaster=self.event_broadcaster
        )

    async def test_run_council_lazy_initialization(self):
        """Test: Council config jest inicjalizowany lazy przy pierwszym wywołaniu."""
        task_id = uuid4()
        context = "Test task"

        # Mock CouncilSession
        with patch("venom_core.core.council.CouncilConfig") as mock_config_class:
            with patch("venom_core.core.council.CouncilSession") as mock_session_class:
                # Setup mocks
                mock_config = MagicMock()
                mock_config_class.return_value = mock_config
                mock_config.create_council.return_value = (
                    MagicMock(),
                    MagicMock(),
                    MagicMock(),
                )

                mock_session = MagicMock()
                mock_session.run = AsyncMock(return_value="Test result")
                mock_session.get_message_count.return_value = 5
                mock_session.get_speakers.return_value = ["User", "Coder"]
                mock_session_class.return_value = mock_session

                # Pierwszym wywołanie - powinno inicjalizować config
                assert self.orchestrator._council_config is None

                result = await self.orchestrator.run_council(task_id, context)

                # Sprawdź że config został zainicjalizowany
                assert self.orchestrator._council_config is not None
                assert result == "Test result"

    async def test_run_council_broadcasts_started_event(self):
        """Test: run_council broadcastuje COUNCIL_STARTED event."""
        task_id = uuid4()
        context = "Test task"

        with patch("venom_core.core.council.CouncilConfig") as config_class:
            config_class.return_value.create_council.return_value = (
                MagicMock(),
                SimpleNamespace(agents=[SimpleNamespace(name="Coder")]),
                MagicMock(),
            )
            with patch("venom_core.core.council.CouncilSession") as mock_session_class:
                mock_session = MagicMock()
                mock_session.run = AsyncMock(return_value="Result")
                mock_session.get_message_count.return_value = 3
                mock_session.get_speakers.return_value = ["User"]
                mock_session_class.return_value = mock_session

                await self.orchestrator.run_council(task_id, context)

                # Sprawdź że broadcast został wywołany z COUNCIL_STARTED
                calls = self.event_broadcaster.broadcast_event.call_args_list
                started_call = [
                    c for c in calls if c[1]["event_type"] == "COUNCIL_STARTED"
                ]
                assert len(started_call) > 0

    async def test_run_council_broadcasts_members_event(self):
        """Test: run_council broadcastuje COUNCIL_MEMBERS event."""
        task_id = uuid4()
        context = "Test task"

        with patch("venom_core.core.council.CouncilConfig") as config_class:
            config_class.return_value.create_council.return_value = (
                MagicMock(),
                SimpleNamespace(agents=[SimpleNamespace(name="Coder")]),
                MagicMock(),
            )
            with patch("venom_core.core.council.CouncilSession") as mock_session_class:
                mock_group_chat = MagicMock()
                mock_agents = [MagicMock(name="User"), MagicMock(name="Coder")]
                mock_group_chat.agents = mock_agents

                mock_session = MagicMock()
                mock_session.group_chat = mock_group_chat
                mock_session.run = AsyncMock(return_value="Result")
                mock_session.get_message_count.return_value = 3
                mock_session.get_speakers.return_value = ["User", "Coder"]
                mock_session_class.return_value = mock_session

                config_class.return_value.create_council.return_value = (
                    MagicMock(),
                    mock_group_chat,
                    MagicMock(),
                )
                await self.orchestrator.run_council(task_id, context)

                # Sprawdź że broadcast zawiera informacje o członkach
                calls = self.event_broadcaster.broadcast_event.call_args_list
                members_call = [
                    c for c in calls if c[1]["event_type"] == "COUNCIL_MEMBERS"
                ]
                assert len(members_call) > 0

    async def test_run_council_broadcasts_completed_event(self):
        """Test: run_council broadcastuje COUNCIL_COMPLETED event po sukcesie."""
        task_id = uuid4()
        context = "Test task"

        with patch("venom_core.core.council.CouncilConfig") as config_class:
            config_class.return_value.create_council.return_value = (
                MagicMock(),
                SimpleNamespace(agents=[SimpleNamespace(name="Coder")]),
                MagicMock(),
            )
            with patch("venom_core.core.council.CouncilSession") as mock_session_class:
                mock_session = MagicMock()
                mock_session.run = AsyncMock(return_value="Success result")
                mock_session.get_message_count.return_value = 10
                mock_session.get_speakers.return_value = ["User", "Architect", "Coder"]
                mock_session_class.return_value = mock_session

                await self.orchestrator.run_council(task_id, context)

                # Sprawdź że broadcast completed został wywołany
                calls = self.event_broadcaster.broadcast_event.call_args_list
                completed_call = [
                    c for c in calls if c[1]["event_type"] == "COUNCIL_COMPLETED"
                ]
                assert len(completed_call) > 0

    async def test_run_council_broadcasts_error_event_on_exception(self):
        """Test: run_council broadcastuje COUNCIL_ERROR event przy wyjątku."""
        task_id = uuid4()
        context = "Test task"

        with patch("venom_core.core.council.CouncilConfig") as mock_config_class:
            # Symuluj błąd podczas inicjalizacji
            mock_config_class.side_effect = Exception("Test error")

            with pytest.raises(Exception, match="Test error"):
                await self.orchestrator.run_council(task_id, context)

            # Sprawdź że broadcast error został wywołany
            calls = self.event_broadcaster.broadcast_event.call_args_list
            error_call = [c for c in calls if c[1]["event_type"] == "COUNCIL_ERROR"]
            assert len(error_call) > 0

    async def test_run_council_logs_to_state_manager(self):
        """Test: run_council loguje postęp do state_manager."""
        task_id = uuid4()
        context = "Test task"

        with patch("venom_core.core.council.CouncilConfig") as config_class:
            config_class.return_value.create_council.return_value = (
                MagicMock(),
                SimpleNamespace(agents=[SimpleNamespace(name="Coder")]),
                MagicMock(),
            )
            with patch("venom_core.core.council.CouncilSession") as mock_session_class:
                mock_session = MagicMock()
                mock_session.run = AsyncMock(return_value="Result")
                mock_session.get_message_count.return_value = 5
                mock_session.get_speakers.return_value = ["User", "Coder"]
                mock_session_class.return_value = mock_session

                await self.orchestrator.run_council(task_id, context)

                # Sprawdź że add_log został wywołany
                assert self.state_manager.add_log.called
                # Sprawdź że task_id był przekazany
                calls = self.state_manager.add_log.call_args_list
                assert any(
                    str(task_id) in str(call) or call[0][0] == task_id for call in calls
                )

    async def test_run_council_passes_context_to_session(self):
        """Test: run_council przekazuje context do CouncilSession.run()."""
        task_id = uuid4()
        context = "Specific test context"

        with patch("venom_core.core.council.CouncilConfig") as config_class:
            config_class.return_value.create_council.return_value = (
                MagicMock(),
                SimpleNamespace(agents=[SimpleNamespace(name="Coder")]),
                MagicMock(),
            )
            with patch("venom_core.core.council.CouncilSession") as mock_session_class:
                mock_session = MagicMock()
                mock_session.run = AsyncMock(return_value="Result")
                mock_session.get_message_count.return_value = 1
                mock_session.get_speakers.return_value = ["User"]
                mock_session_class.return_value = mock_session

                await self.orchestrator.run_council(task_id, context)

                # Missing generation overrides retain native defaults.
                mock_session.run.assert_awaited_once_with(
                    context, generation_params=None
                )


@pytest.mark.asyncio
async def test_active_orchestrator_passes_generation_budget_and_failure():
    from venom_core.core.council import CouncilExecutionError

    state = MagicMock()
    state.get_task.return_value = SimpleNamespace(
        context_history={"generation_params": {"max_tokens": 37, "temperature": 0}}
    )
    orch = Orchestrator(state_manager=state, event_broadcaster=AsyncMock())
    orch._council_config = SimpleNamespace(
        create_council=lambda: ("u", SimpleNamespace(agents=[]), "m")
    )
    session = SimpleNamespace(
        run=AsyncMock(side_effect=CouncilExecutionError("provider-unavailable"))
    )
    with patch("venom_core.core.council.CouncilSession", return_value=session):
        with pytest.raises(CouncilExecutionError, match="provider-unavailable"):
            await orch.run_council(uuid4(), "task")
    session.run.assert_awaited_once_with(
        "task", generation_params={"max_tokens": 37, "temperature": 0}
    )
