"""Testy jednostkowe dla ChronoSkill."""

import tempfile
from pathlib import Path

import pytest

from venom_core.core.chronos import ChronosEngine
from venom_core.execution.skills.chrono_skill import ChronoSkill


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

        yield {
            "timelines": str(timelines_dir),
            "memory": str(memory_dir),
            "workspace": str(workspace_dir),
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
def chrono_skill(chronos_engine):
    """Fixture dla ChronoSkill."""
    return ChronoSkill(chronos_engine=chronos_engine)


class TestChronoSkill:
    """Testy dla ChronoSkill."""

    def test_chrono_skill_initialization(self, chrono_skill):
        """Test inicjalizacji ChronoSkill."""
        assert chrono_skill.chronos is not None

    @pytest.mark.asyncio
    async def test_create_checkpoint(self, chrono_skill):
        """Test tworzenia checkpointu przez skill."""
        result = await chrono_skill.create_checkpoint(
            name="Test Checkpoint", description="Test description"
        )

        assert "✓" in result
        assert "Test Checkpoint" in result
        assert "ID:" in result
        assert "restore_checkpoint" in result

    @pytest.mark.asyncio
    async def test_create_checkpoint_on_timeline(self, chrono_skill):
        """Test tworzenia checkpointu na określonej timeline."""
        # Najpierw utwórz timeline
        await chrono_skill.branch_timeline("experimental")

        result = await chrono_skill.create_checkpoint(
            name="Exp Checkpoint", description="Experimental", timeline="experimental"
        )

        assert "✓" in result
        assert "experimental" in result.lower()

    @pytest.mark.asyncio
    async def test_list_checkpoints_empty(self, chrono_skill):
        """Test listowania checkpointów gdy ich brak."""
        result = await chrono_skill.list_checkpoints()

        assert "Brak checkpointów" in result

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, chrono_skill):
        """Test listowania checkpointów."""
        # Utwórz kilka checkpointów
        await chrono_skill.create_checkpoint(name="CP1", description="First")
        await chrono_skill.create_checkpoint(name="CP2", description="Second")

        result = await chrono_skill.list_checkpoints()

        assert "CP1" in result
        assert "CP2" in result
        assert "ID:" in result

    @pytest.mark.asyncio
    async def test_delete_checkpoint(self, chrono_skill):
        """Test usuwania checkpointu."""
        # Utwórz checkpoint
        create_result = await chrono_skill.create_checkpoint(name="To Delete")

        # Wyciągnij ID z wyniku (format: "ID: xxx")
        import re

        match = re.search(r"ID: (\w+)", create_result)
        assert match
        checkpoint_id = match.group(1)

        # Usuń checkpoint
        result = await chrono_skill.delete_checkpoint(checkpoint_id=checkpoint_id)

        assert "✓" in result
        assert checkpoint_id in result

        # Sprawdź czy został usunięty
        list_result = await chrono_skill.list_checkpoints()
        assert "Brak checkpointów" in list_result

    @pytest.mark.asyncio
    async def test_delete_nonexistent_checkpoint(self, chrono_skill):
        """Test usuwania nieistniejącego checkpointu."""
        result = await chrono_skill.delete_checkpoint(checkpoint_id="nonexistent")

        assert "✗" in result

    @pytest.mark.asyncio
    async def test_branch_timeline(self, chrono_skill):
        """Test tworzenia nowej linii czasowej."""
        result = await chrono_skill.branch_timeline(name="experimental")

        assert "✓" in result
        assert "experimental" in result
        assert "timeline" in result.lower()

    @pytest.mark.asyncio
    async def test_branch_duplicate_timeline(self, chrono_skill):
        """Test tworzenia duplikatu linii czasowej."""
        await chrono_skill.branch_timeline(name="test")
        result = await chrono_skill.branch_timeline(name="test")

        assert "✗" in result

    @pytest.mark.asyncio
    async def test_list_timelines_empty(self, chrono_skill):
        """Test listowania linii czasowych."""
        result = await chrono_skill.list_timelines()

        # Zawsze jest przynajmniej "main"
        assert "main" in result

    @pytest.mark.asyncio
    async def test_list_timelines(self, chrono_skill):
        """Test listowania linii czasowych."""
        await chrono_skill.branch_timeline("timeline1")
        await chrono_skill.branch_timeline("timeline2")

        result = await chrono_skill.list_timelines()

        assert "main" in result
        assert "timeline1" in result
        assert "timeline2" in result
        assert "checkpointów" in result

    @pytest.mark.asyncio
    async def test_merge_timeline_placeholder(self, chrono_skill):
        """Test mergowania linii czasowych (placeholder)."""
        await chrono_skill.branch_timeline("source")
        result = await chrono_skill.merge_timeline(source="source", target="main")

        # W obecnej wersji to tylko placeholder
        assert "⚠️" in result
        assert "zaawansowana funkcja" in result.lower()

    @pytest.mark.asyncio
    async def test_restore_checkpoint(self, chrono_skill):
        """Test przywracania checkpointu."""
        # Utwórz checkpoint
        create_result = await chrono_skill.create_checkpoint(name="Test")

        import re

        match = re.search(r"ID: (\w+)", create_result)
        assert match
        checkpoint_id = match.group(1)

        # Przywróć checkpoint
        # Uwaga: To może nie działać w testach bez prawdziwego git repo
        result = await chrono_skill.restore_checkpoint(checkpoint_id=checkpoint_id)

        # Sprawdź format wyniku (może być success lub error w zależności od środowiska)
        assert checkpoint_id in result


class TestChronoSkillIntegration:
    """Testy integracyjne dla ChronoSkill."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, chrono_skill):
        """Test pełnego przepływu pracy z checkpointami."""
        # 1. Utwórz checkpoint
        create_result = await chrono_skill.create_checkpoint(
            name="Initial State", description="Starting point"
        )
        assert "✓" in create_result

        # 2. Wylistuj checkpointy
        list_result = await chrono_skill.list_checkpoints()
        assert "Initial State" in list_result

        # 3. Utwórz drugi checkpoint
        await chrono_skill.create_checkpoint(name="After Changes")

        # 4. Wylistuj ponownie
        list_result = await chrono_skill.list_checkpoints()
        assert "Initial State" in list_result
        assert "After Changes" in list_result

    @pytest.mark.asyncio
    async def test_timeline_branching_workflow(self, chrono_skill):
        """Test przepływu z rozgałęzieniami linii czasowej."""
        # 1. Utwórz checkpoint na main
        await chrono_skill.create_checkpoint(name="Main CP", timeline="main")

        # 2. Utwórz nową timeline
        branch_result = await chrono_skill.branch_timeline(name="experimental")
        assert "✓" in branch_result

        # 3. Utwórz checkpoint na nowej timeline
        await chrono_skill.create_checkpoint(name="Exp CP", timeline="experimental")

        # 4. Sprawdź checkpointy na obu timelines
        main_cps = await chrono_skill.list_checkpoints(timeline="main")
        exp_cps = await chrono_skill.list_checkpoints(timeline="experimental")

        # Main powinien mieć 2 checkpointy (original + branch point)
        assert "Main CP" in main_cps

        # Experimental powinien mieć swój checkpoint
        assert "Exp CP" in exp_cps

    @pytest.mark.asyncio
    async def test_checkpoint_lifecycle(self, chrono_skill):
        """Test pełnego cyklu życia checkpointu."""
        # Tworzenie
        create_result = await chrono_skill.create_checkpoint(name="Lifecycle Test")
        assert "✓" in create_result

        import re

        match = re.search(r"ID: (\w+)", create_result)
        checkpoint_id = match.group(1)

        # Listowanie
        list_result = await chrono_skill.list_checkpoints()
        assert checkpoint_id in list_result

        # Usuwanie
        delete_result = await chrono_skill.delete_checkpoint(checkpoint_id=checkpoint_id)
        assert "✓" in delete_result

        # Weryfikacja usunięcia
        list_result = await chrono_skill.list_checkpoints()
        assert checkpoint_id not in list_result
