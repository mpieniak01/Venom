"""Security regression tests for autonomy enforcement on mutating paths."""

import pytest

from venom_core.core.permission_guard import permission_guard
from venom_core.execution.skills.core_skill import CoreSkill
from venom_core.services.audit_stream import get_audit_stream
from venom_core.skills.mcp_manager_skill import McpManagerSkill


@pytest.fixture(autouse=True)
def _reset_autonomy_level():
    previous_level = permission_guard.get_current_level()
    get_audit_stream().clear()
    permission_guard.set_level(0)
    try:
        yield
    finally:
        permission_guard.set_level(previous_level)
        get_audit_stream().clear()


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


def test_autonomy_block_publishes_audit_entry():
    skill = CoreSkill()
    with pytest.raises(PermissionError, match="AutonomyViolation"):
        skill.hot_patch(__file__, "print('blocked')")

    entries = get_audit_stream().get_entries(action="autonomy.blocked", limit=5)
    assert entries
    entry = entries[0]
    assert entry.source == "core.autonomy"
    assert entry.status == "blocked"
    assert entry.details["decision"] == "block"
    assert entry.details["reason_code"] == "AUTONOMY_PERMISSION_DENIED"
    assert "autonomy" in entry.details["tags"]
    assert entry.details["operation"] == "core_patch"
    assert entry.details["current_autonomy_level"] == 0
    assert entry.details["current_autonomy_level_name"] == "ISOLATED"
    assert isinstance(entry.details["technical_context"], dict)
