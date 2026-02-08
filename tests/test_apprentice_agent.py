"""Testy jednostkowe dla ApprenticeAgent."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.agents.apprentice import ApprenticeAgent
from venom_core.learning.demonstration_analyzer import ActionIntent


class TestApprenticeAgent:
    """Testy dla ApprenticeAgent."""

    @pytest.fixture
    def temp_workspace(self):
        """Fixture: tymczasowy katalog workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_kernel(self):
        """Fixture: mock Kernel."""
        return MagicMock()

    @pytest.fixture
    def apprentice_agent(self, mock_kernel, temp_workspace):
        """Fixture: ApprenticeAgent."""
        with (
            patch("venom_core.agents.apprentice.DemonstrationRecorder"),
            patch("venom_core.agents.apprentice.DemonstrationAnalyzer"),
        ):
            agent = ApprenticeAgent(kernel=mock_kernel, workspace_root=temp_workspace)
            return agent

    def test_initialization(self, apprentice_agent, temp_workspace):
        """Test inicjalizacji ApprenticeAgent."""
        assert apprentice_agent.workspace_root == Path(temp_workspace)
        assert apprentice_agent.custom_skills_dir.exists()
        assert apprentice_agent.current_session_id is None

    def test_start_recording(self, apprentice_agent):
        """Test rozpoczęcia nagrywania."""
        apprentice_agent.recorder.is_recording = False
        apprentice_agent.recorder.start_recording = MagicMock(
            return_value="test_session"
        )

        result = apprentice_agent._start_recording("Rozpocznij nagrywanie")

        assert "Rozpoczęto nagrywanie" in result
        assert "test_session" in result
        assert apprentice_agent.current_session_id == "test_session"

    def test_start_recording_already_running(self, apprentice_agent):
        """Test próby rozpoczęcia nagrywania gdy już trwa."""
        apprentice_agent.recorder.is_recording = True

        result = apprentice_agent._start_recording("Rozpocznij nagrywanie")

        assert "już trwa" in result

    def test_stop_recording(self, apprentice_agent):
        """Test zatrzymania nagrywania."""
        apprentice_agent.recorder.is_recording = True
        apprentice_agent.recorder.stop_recording = MagicMock(
            return_value="/path/to/session.json"
        )
        apprentice_agent.current_session_id = "test_session"

        result = apprentice_agent._stop_recording("Zatrzymaj nagrywanie")

        assert "Zakończono nagrywanie" in result
        assert "/path/to/session.json" in result

    def test_stop_recording_not_active(self, apprentice_agent):
        """Test zatrzymania gdy nie nagrywa."""
        apprentice_agent.recorder.is_recording = False

        result = apprentice_agent._stop_recording("Zatrzymaj nagrywanie")

        assert "nie jest aktywne" in result

    @pytest.mark.asyncio
    async def test_analyze_demonstration(self, apprentice_agent):
        """Test analizy demonstracji."""
        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = "test_session"

        apprentice_agent.recorder.load_session = MagicMock(return_value=mock_session)

        # Mock analyzer
        mock_actions = [
            ActionIntent(
                action_type="click",
                description="Click button",
                timestamp=1.0,
                params={},
            )
        ]
        apprentice_agent.analyzer.analyze_session = AsyncMock(return_value=mock_actions)
        apprentice_agent.analyzer.generate_workflow_summary = MagicMock(
            return_value="Summary"
        )

        result = await apprentice_agent._analyze_demonstration(
            "Analizuj sesję test_session"
        )

        assert "Analiza zakończona" in result
        assert "test_session" in result
        assert apprentice_agent.analyzer.analyze_session.called

    @pytest.mark.asyncio
    async def test_analyze_demonstration_session_not_found(self, apprentice_agent):
        """Test analizy nieistniejącej sesji."""
        apprentice_agent.recorder.load_session = MagicMock(return_value=None)

        result = await apprentice_agent._analyze_demonstration(
            "Analizuj sesję nonexistent"
        )

        assert "Nie znaleziono sesji" in result

    @pytest.mark.asyncio
    async def test_generate_skill(self, apprentice_agent, temp_workspace):
        """Test generowania skill."""
        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = "test_session"

        apprentice_agent.recorder.load_session = MagicMock(return_value=mock_session)
        apprentice_agent.current_session_id = "test_session"

        # Mock analyzer
        mock_actions = [
            ActionIntent(
                action_type="click",
                description="Click button",
                timestamp=1.0,
                params={
                    "element_description": "blue button",
                    "fallback_coords": {"x": 100, "y": 200},
                },
            )
        ]
        apprentice_agent.analyzer.analyze_session = AsyncMock(return_value=mock_actions)

        result = await apprentice_agent._generate_skill("Generuj skill test_workflow")

        assert "Skill wygenerowany" in result
        assert "test_workflow" in result

        # Sprawdź czy plik został utworzony
        skill_file = Path(temp_workspace) / "custom_skills" / "test_workflow.py"
        assert skill_file.exists()

        # Sprawdź zawartość
        content = skill_file.read_text()
        assert "async def test_workflow" in content
        assert "GhostAgent" in content

    @pytest.mark.asyncio
    async def test_generate_skill_no_name(self, apprentice_agent):
        """Test generowania skill bez nazwy."""
        result = await apprentice_agent._generate_skill("Generuj skill")

        assert "Nie podano nazwy skill" in result

    def test_extract_session_name(self, apprentice_agent):
        """Test wyodrębniania nazwy sesji."""
        name = apprentice_agent._extract_session_name(
            "Rozpocznij nagrywanie nazwany login_workflow"
        )
        assert name == "login_workflow"

    def test_extract_session_id(self, apprentice_agent):
        """Test wyodrębniania ID sesji."""
        session_id = apprentice_agent._extract_session_id(
            "Analizuj sesję demo_20241208_123456"
        )
        assert session_id == "demo_20241208_123456"

    def test_extract_skill_name(self, apprentice_agent):
        """Test wyodrębniania nazwy skill."""
        name = apprentice_agent._extract_skill_name("Generuj skill send_email")
        assert name == "send_email"

        # Test z nazwą ze spacjami
        name = apprentice_agent._extract_skill_name("Generuj skill 'Send Email Report'")
        assert name == "send_email_report"

    @pytest.mark.asyncio
    async def test_process_start_recording(self, apprentice_agent):
        """Test przetwarzania żądania rozpoczęcia nagrywania."""
        apprentice_agent.recorder.is_recording = False
        apprentice_agent.recorder.start_recording = MagicMock(
            return_value="test_session"
        )

        result = await apprentice_agent.process("Rozpocznij nagrywanie")

        assert "Rozpoczęto nagrywanie" in result

    @pytest.mark.asyncio
    async def test_process_stop_recording(self, apprentice_agent):
        """Test przetwarzania żądania zatrzymania nagrywania."""
        apprentice_agent.recorder.is_recording = True
        apprentice_agent.recorder.stop_recording = MagicMock(
            return_value="/path/to/session.json"
        )

        result = await apprentice_agent.process("Zatrzymaj nagrywanie")

        assert "Zakończono nagrywanie" in result

    def test_generate_skill_code_with_multiple_actions(self, apprentice_agent):
        """Test generowania kodu z wieloma akcjami."""
        actions = [
            ActionIntent(
                action_type="click",
                description="Click login button",
                timestamp=1.0,
                params={
                    "element_description": "login button",
                    "fallback_coords": {"x": 100, "y": 200},
                },
            ),
            ActionIntent(
                action_type="type",
                description="Type username",
                timestamp=2.0,
                params={"text": "user@example.com", "is_sensitive": False},
            ),
            ActionIntent(
                action_type="hotkey",
                description="Press Ctrl+S",
                timestamp=3.0,
                params={"keys": ["ctrl", "s"]},
            ),
        ]

        code = apprentice_agent._generate_skill_code("test_workflow", actions)

        assert "async def test_workflow" in code
        assert "vision_click" in code
        assert "keyboard_type" in code
        assert "keyboard_hotkey" in code
        assert "login button" in code

    def test_sanitize_identifier_with_special_chars(self, apprentice_agent):
        """Test sanityzacji identyfikatorów ze znakami specjalnymi."""
        assert (
            apprentice_agent._sanitize_identifier("hello'; drop table")
            == "hello___drop_table"
        )
        assert apprentice_agent._sanitize_identifier("123abc") == "_123abc"
        assert apprentice_agent._sanitize_identifier("") == "skill"
        assert apprentice_agent._sanitize_identifier("valid_name") == "valid_name"
        assert (
            apprentice_agent._sanitize_identifier("name-with-dash") == "name_with_dash"
        )
        assert (
            apprentice_agent._sanitize_identifier("name with spaces")
            == "name_with_spaces"
        )
        assert (
            apprentice_agent._sanitize_identifier("name/with/slash")
            == "name_with_slash"
        )
        assert (
            apprentice_agent._sanitize_identifier("../../../etc/passwd")
            == "____________etc_passwd"
        )
