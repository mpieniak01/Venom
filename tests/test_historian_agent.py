"""Testy jednostkowe dla HistorianAgent."""

import tempfile
from pathlib import Path

import pytest
from semantic_kernel import Kernel

from venom_core.agents.historian import HistorianAgent
from venom_core.core.chronos import ChronosEngine
from venom_core.memory.lessons_store import LessonsStore


@pytest.fixture
def kernel():
    """Fixture dla Semantic Kernel."""
    return Kernel()


@pytest.fixture
def temp_dirs():
    """Fixture dla tymczasowych katalogów."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        timelines_dir = base / "timelines"
        memory_dir = base / "memory"
        workspace_dir = base / "workspace"

        timelines_dir.mkdir()
        memory_dir.mkdir()
        workspace_dir.mkdir()

        lessons_file = memory_dir / "lessons.json"

        yield {
            "timelines": str(timelines_dir),
            "memory": str(memory_dir),
            "workspace": str(workspace_dir),
            "lessons": str(lessons_file),
        }


@pytest.fixture
def chronos_engine(temp_dirs):
    """Fixture dla ChronosEngine."""
    return ChronosEngine(
        timelines_dir=temp_dirs["timelines"],
        workspace_root=temp_dirs["workspace"],
        memory_root=temp_dirs["memory"],
    )


@pytest.fixture
def lessons_store(temp_dirs):
    """Fixture dla LessonsStore."""
    return LessonsStore(storage_path=temp_dirs["lessons"], vector_store=None)


@pytest.fixture
def historian_agent(kernel, chronos_engine, lessons_store):
    """Fixture dla HistorianAgent."""
    return HistorianAgent(
        kernel=kernel, chronos_engine=chronos_engine, lessons_store=lessons_store
    )


class TestHistorianAgent:
    """Testy dla HistorianAgent."""

    def test_historian_initialization(self, historian_agent):
        """Test inicjalizacji HistorianAgent."""
        assert historian_agent.chronos is not None
        assert historian_agent.lessons_store is not None
        assert historian_agent.kernel is not None

    @pytest.mark.asyncio
    async def test_assess_risk_high(self, historian_agent):
        """Test oceny wysokiego ryzyka."""
        operation = "Wykonaj hot_patch na krytycznym pliku systemu"
        risk = await historian_agent._assess_risk(operation)

        assert risk["risk_level"] == "high"
        assert "hot_patch" in risk["reason"]

    @pytest.mark.asyncio
    async def test_assess_risk_medium(self, historian_agent):
        """Test oceny średniego ryzyka."""
        operation = "Modify configuration file"
        risk = await historian_agent._assess_risk(operation)

        assert risk["risk_level"] == "medium"
        assert "modify" in risk["reason"].lower()

    @pytest.mark.asyncio
    async def test_assess_risk_low(self, historian_agent):
        """Test oceny niskiego ryzyka."""
        operation = "Read file contents"
        risk = await historian_agent._assess_risk(operation)

        assert risk["risk_level"] == "low"

    @pytest.mark.asyncio
    async def test_process_high_risk_operation(self, historian_agent):
        """Test przetwarzania operacji wysokiego ryzyka."""
        result = await historian_agent.process("Wykonaj hot_patch na systemie")

        assert "REKOMENDACJA" in result
        assert "checkpoint" in result.lower()
        assert "high" in result.lower() or "critical" in result.lower()

    @pytest.mark.asyncio
    async def test_process_low_risk_operation(self, historian_agent):
        """Test przetwarzania operacji niskiego ryzyka."""
        result = await historian_agent.process("Odczytaj dane z pliku")

        assert "niskie ryzyko" in result.lower() or "low" in result.lower()

    def test_recommend_checkpoint_for_risky_operation(self, historian_agent):
        """Test rekomendacji checkpointu dla ryzykownej operacji."""
        assert historian_agent.recommend_checkpoint("hot_patch") is True
        assert historian_agent.recommend_checkpoint("migration") is True
        assert historian_agent.recommend_checkpoint("major_refactor") is True

    def test_no_checkpoint_for_safe_operation(self, historian_agent):
        """Test braku rekomendacji checkpointu dla bezpiecznej operacji."""
        assert historian_agent.recommend_checkpoint("read_file") is False
        assert historian_agent.recommend_checkpoint("list_files") is False

    def test_create_safety_checkpoint(self, historian_agent):
        """Test tworzenia checkpointu bezpieczeństwa."""
        checkpoint_id = historian_agent.create_safety_checkpoint(
            name="test_operation", description="Test safety checkpoint"
        )

        assert checkpoint_id is not None
        assert len(checkpoint_id) == 8

        # Sprawdź czy checkpoint został utworzony
        checkpoints = historian_agent.chronos.list_checkpoints()
        assert len(checkpoints) == 1
        assert checkpoints[0].checkpoint_id == checkpoint_id

    def test_get_checkpoint_history(self, historian_agent):
        """Test pobierania historii checkpointów."""
        # Utwórz kilka checkpointów
        historian_agent.create_safety_checkpoint("op1", "Operation 1")
        historian_agent.create_safety_checkpoint("op2", "Operation 2")
        historian_agent.create_safety_checkpoint("op3", "Operation 3")

        history = historian_agent.get_checkpoint_history(limit=2)
        assert len(history) == 2

    def test_get_checkpoint_history_empty(self, historian_agent):
        """Test pobierania historii gdy brak checkpointów."""
        history = historian_agent.get_checkpoint_history()
        assert history == []

    def test_analyze_failure(self, historian_agent, lessons_store):
        """Test analizy błędu."""
        checkpoint_id = historian_agent.create_safety_checkpoint(
            "test", "Test checkpoint"
        )

        historian_agent.analyze_failure(
            operation="Test operation",
            error="Test error message",
            checkpoint_before=checkpoint_id,
        )

        # Sprawdź czy lekcja została zapisana
        lessons = lessons_store.list_lessons(limit=10)
        assert len(lessons) > 0

        lesson = lessons[0]
        assert "Test operation" in lesson.situation
        assert "Test error message" in lesson.result
        assert checkpoint_id in lesson.feedback

    def test_analyze_failure_without_checkpoint(self, historian_agent, lessons_store):
        """Test analizy błędu bez checkpointu."""
        historian_agent.analyze_failure(
            operation="Test operation", error="Test error", checkpoint_before=None
        )

        lessons = lessons_store.list_lessons(limit=10)
        assert len(lessons) > 0
        assert "utworzyć checkpoint" in lessons[0].feedback


class TestHistorianIntegration:
    """Testy integracyjne dla HistorianAgent."""

    @pytest.mark.asyncio
    async def test_full_risk_management_flow(self, historian_agent):
        """Test pełnego przepływu zarządzania ryzykiem."""
        # 1. Oceń operację
        operation = "Wykonaj hot_patch na module core"
        result = await historian_agent.process(operation)

        # Powinien rekomendować checkpoint
        assert "REKOMENDACJA" in result

        # 2. Utwórz checkpoint
        checkpoint_id = historian_agent.create_safety_checkpoint(
            "pre_hot_patch", "Before hot patch operation"
        )
        assert checkpoint_id is not None

        # 3. Symuluj błąd
        historian_agent.analyze_failure(
            operation=operation,
            error="SyntaxError: invalid syntax",
            checkpoint_before=checkpoint_id,
        )

        # 4. Sprawdź czy lekcja została zapisana
        lessons = historian_agent.lessons_store.list_lessons(limit=1)
        assert len(lessons) == 1
        assert checkpoint_id in lessons[0].feedback

    def test_checkpoint_history_ordering(self, historian_agent):
        """Test kolejności w historii checkpointów."""
        import time

        # Utwórz checkpointy z odstępami czasu
        id1 = historian_agent.create_safety_checkpoint("first", "First operation")
        time.sleep(0.1)
        id2 = historian_agent.create_safety_checkpoint("second", "Second operation")
        time.sleep(0.1)
        id3 = historian_agent.create_safety_checkpoint("third", "Third operation")

        history = historian_agent.get_checkpoint_history(limit=10)

        # Najnowsze powinny być pierwsze
        assert history[0].checkpoint_id == id3
        assert history[1].checkpoint_id == id2
        assert history[2].checkpoint_id == id1
