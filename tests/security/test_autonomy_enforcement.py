"""Security regression tests for autonomy enforcement on mutating paths."""

import pytest

from venom_core.core.permission_guard import permission_guard
from venom_core.execution.skills.core_skill import CoreSkill
from venom_core.skills.mcp_manager_skill import McpManagerSkill


@pytest.fixture(autouse=True)
def _reset_autonomy_level():
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(0)
    try:
        yield
    finally:
        permission_guard.set_level(previous_level)


def test_core_hot_patch_blocked_when_not_root(tmp_path):
    skill = CoreSkill(backup_dir=str(tmp_path / "backups"))
    test_file = tmp_path / "test.py"
    test_file.write_text("print('ok')", encoding="utf-8")

    with pytest.raises(PermissionError, match="AutonomyViolation"):
        skill.hot_patch(str(test_file), "print('blocked')")


def test_core_rollback_blocked_when_not_root(tmp_path):
    skill = CoreSkill(backup_dir=str(tmp_path / "backups"))
    test_file = tmp_path / "test.py"
    test_file.write_text("print('ok')", encoding="utf-8")

    with pytest.raises(PermissionError, match="AutonomyViolation"):
        skill.rollback(str(test_file))


@pytest.mark.asyncio
async def test_mcp_import_blocked_without_shell_permission():
    manager = McpManagerSkill()

    result = await manager.import_mcp_tool(
        repo_url="https://example.com/r.git", tool_name="r"
    )

    assert "AutonomyViolation" in result


@pytest.mark.asyncio
async def test_mcp_run_shell_blocked_without_shell_permission():
    manager = McpManagerSkill()

    with pytest.raises(PermissionError, match="AutonomyViolation"):
        await manager._run_shell("echo no")
