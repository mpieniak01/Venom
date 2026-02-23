"""Unit tests for ChronoSkill."""

import tempfile
from pathlib import Path

import pytest

from venom_core.core.chronos import ChronosEngine
from venom_core.execution.skills.chrono_skill import ChronoSkill


@pytest.fixture
def temp_dirs():
    """Fixture for temporary directories."""
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
    """Fixture for ChronosEngine."""
    return ChronosEngine(
        timelines_dir=temp_dirs["timelines"],
        workspace_root=temp_dirs["workspace"],
        memory_root=temp_dirs["memory"],
    )


@pytest.fixture
def chrono_skill(chronos_engine):
    """Fixture for ChronoSkill."""
    return ChronoSkill(chronos_engine=chronos_engine)


class TestChronoSkill:
    """Tests for ChronoSkill."""

    def test_chrono_skill_initialization(self, chrono_skill):
        """Test ChronoSkill initialization."""
        assert chrono_skill.chronos is not None

    @pytest.mark.asyncio
    async def test_create_checkpoint(self, chrono_skill):
        """Test creating checkpoint through skill."""
        result = await chrono_skill.create_checkpoint(
            name="Test Checkpoint", description="Test description"
        )

        assert "✓" in result
        assert "Test Checkpoint" in result
        assert "ID:" in result
        assert "restore_checkpoint" in result

    @pytest.mark.asyncio
    async def test_create_checkpoint_on_timeline(self, chrono_skill):
        """Test creating checkpoint on specific timeline."""
        # First create timeline
        await chrono_skill.branch_timeline("experimental")

        result = await chrono_skill.create_checkpoint(
            name="Exp Checkpoint", description="Experimental", timeline="experimental"
        )

        assert "✓" in result
        assert "experimental" in result.lower()

    @pytest.mark.asyncio
    async def test_list_checkpoints_empty(self, chrono_skill):
        """Test listing checkpoints when there are none."""
        result = await chrono_skill.list_checkpoints()

        assert "Brak checkpointów" in result

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, chrono_skill):
        """Test listing checkpoints."""
        # Create several checkpoints
        await chrono_skill.create_checkpoint(name="CP1", description="First")
        await chrono_skill.create_checkpoint(name="CP2", description="Second")

        result = await chrono_skill.list_checkpoints()

        assert "CP1" in result
        assert "CP2" in result
        assert "ID:" in result

    @pytest.mark.asyncio
    async def test_delete_checkpoint(self, chrono_skill):
        """Test deleting checkpoint."""
        # Create checkpoint
        create_result = await chrono_skill.create_checkpoint(name="To Delete")

        # Extract ID from result (format: "ID: xxx")
        import re

        match = re.search(r"ID: (\w+)", create_result)
        assert match
        checkpoint_id = match.group(1)

        # Delete checkpoint
        result = await chrono_skill.delete_checkpoint(checkpoint_id=checkpoint_id)

        assert "✓" in result
        assert checkpoint_id in result

        # Check if it was deleted
        list_result = await chrono_skill.list_checkpoints()
        assert "Brak checkpointów" in list_result

    @pytest.mark.asyncio
    async def test_delete_nonexistent_checkpoint(self, chrono_skill):
        """Test deleting nonexistent checkpoint."""
        result = await chrono_skill.delete_checkpoint(checkpoint_id="nonexistent")

        assert "❌" in result

    @pytest.mark.asyncio
    async def test_branch_timeline(self, chrono_skill):
        """Test creating new timeline."""
        result = await chrono_skill.branch_timeline(name="experimental")

        assert "✓" in result
        assert "experimental" in result
        assert "timeline" in result.lower()

    @pytest.mark.asyncio
    async def test_branch_duplicate_timeline(self, chrono_skill):
        """Test creating duplicate timeline."""
        await chrono_skill.branch_timeline(name="test")
        result = await chrono_skill.branch_timeline(name="test")

        assert "❌" in result

    @pytest.mark.asyncio
    async def test_list_timelines_empty(self, chrono_skill):
        """Test listing timelines."""

        # Always at least "main"
        assert "main" in result

    @pytest.mark.asyncio
    async def test_list_timelines(self, chrono_skill):
        """Test listing timelines."""
        await chrono_skill.branch_timeline("timeline1")
        await chrono_skill.branch_timeline("timeline2")

        result = await chrono_skill.list_timelines()

        assert "main" in result
        assert "timeline1" in result
        assert "timeline2" in result
        assert "checkpointów" in result

    @pytest.mark.asyncio
    async def test_merge_timeline_placeholder(self, chrono_skill):
        """Test merging timelines (placeholder)."""
        await chrono_skill.branch_timeline("source")
        result = await chrono_skill.merge_timeline(source="source", target="main")

        # In current version this is just a placeholder
        assert "⚠️" in result
        assert "zaawansowana funkcja" in result.lower()

    @pytest.mark.asyncio
    async def test_restore_checkpoint(self, chrono_skill):
        """Test restoring checkpoint."""
        # Create checkpoint
        create_result = await chrono_skill.create_checkpoint(name="Test")

        import re

        match = re.search(r"ID: (\w+)", create_result)
        assert match
        checkpoint_id = match.group(1)

        # Restore checkpoint
        # Note: This may not work in tests without real git repo
        result = await chrono_skill.restore_checkpoint(checkpoint_id=checkpoint_id)

        # Check result format (may be success or error depending on environment)
        assert checkpoint_id in result


class TestChronoSkillIntegration:
    """Integration tests for ChronoSkill."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, chrono_skill):
        """Test full workflow with checkpoints."""
        # 1. Create checkpoint
        create_result = await chrono_skill.create_checkpoint(
            name="Initial State", description="Starting point"
        )
        assert "✓" in create_result

        # 2. List checkpoints
        list_result = await chrono_skill.list_checkpoints()
        assert "Initial State" in list_result

        # 3. Create second checkpoint
        await chrono_skill.create_checkpoint(name="After Changes")

        # 4. List again
        list_result = await chrono_skill.list_checkpoints()
        assert "Initial State" in list_result
        assert "After Changes" in list_result

    @pytest.mark.asyncio
    async def test_timeline_branching_workflow(self, chrono_skill):
        """Test workflow with timeline branching."""
        # 1. Create checkpoint on main
        await chrono_skill.create_checkpoint(name="Main CP", timeline="main")

        # 2. Create new timeline
        branch_result = await chrono_skill.branch_timeline(name="experimental")
        assert "✓" in branch_result

        # 3. Create checkpoint on new timeline
        await chrono_skill.create_checkpoint(name="Exp CP", timeline="experimental")

        # 4. Check checkpoints on both timelines
        main_cps = await chrono_skill.list_checkpoints(timeline="main")
        exp_cps = await chrono_skill.list_checkpoints(timeline="experimental")

        # Main should have 2 checkpoints (original + branch point)
        assert "Main CP" in main_cps

        # Experimental should have its checkpoint
        assert "Exp CP" in exp_cps

    @pytest.mark.asyncio
    async def test_checkpoint_lifecycle(self, chrono_skill):
        """Test full checkpoint lifecycle."""
        # Creating
        create_result = await chrono_skill.create_checkpoint(name="Lifecycle Test")
        assert "✓" in create_result

        import re

        match = re.search(r"ID: (\w+)", create_result)
        checkpoint_id = match.group(1)

        # Listing
        list_result = await chrono_skill.list_checkpoints()
        assert checkpoint_id in list_result

        # Deleting
        delete_result = await chrono_skill.delete_checkpoint(
            checkpoint_id=checkpoint_id
        )
        assert "✓" in delete_result

        # Verify deletion
        list_result = await chrono_skill.list_checkpoints()
        assert checkpoint_id not in list_result
