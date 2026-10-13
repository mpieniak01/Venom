"""Security regression tests for autonomy enforcement on mutating paths."""

from unittest.mock import Mock

import pytest

import venom_core.execution.skills.core_skill as core_skill_module
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


@pytest.mark.parametrize(
    "mode,level,allowed,audit_action",
    [
        ("hard", 0, False, "autonomy.blocked"),
        ("hard", 30, False, "autonomy.blocked"),
        ("hard", 40, True, None),
        ("soft", 0, True, "autonomy.degraded_allow"),
    ],
)
def test_confirmed_core_restart_respects_existing_autonomy_policy(
    monkeypatch, tmp_path, mode, level, allowed, audit_action
):
    monkeypatch.setenv("AUTONOMY_ENFORCEMENT_MODE", mode)
    permission_guard.set_level(level)
    execv = Mock()
    monkeypatch.setattr(core_skill_module.os, "execv", execv)
    monkeypatch.setattr(core_skill_module.sys, "executable", "/opt/venom/bin/python")
    monkeypatch.setattr(
        core_skill_module.sys, "argv", ["/opt/venom/bin/uvicorn", "venom_core.main:app"]
    )
    skill = CoreSkill(backup_dir=str(tmp_path / "backups"))

    if allowed:
        assert "Restarting" in skill.restart_service(confirm=True)
        execv.assert_called_once_with(
            "/opt/venom/bin/python",
            ["/opt/venom/bin/python", "/opt/venom/bin/uvicorn", "venom_core.main:app"],
        )
    else:
        with pytest.raises(PermissionError, match="AutonomyViolation"):
            skill.restart_service(confirm=True)
        execv.assert_not_called()

    if audit_action:
        entries = get_audit_stream().get_entries(action=audit_action, limit=5)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.details["operation"] == "core_patch"
        assert entry.details["required_level"] == 40
        assert entry.details["enforcement_mode"] == mode
        assert entry.status == ("degraded" if allowed else "blocked")
    else:
        assert not get_audit_stream().get_entries(action="autonomy.blocked", limit=5)


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


def test_autonomy_soft_mode_allows_with_degraded_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTONOMY_ENFORCEMENT_MODE", "soft")
    skill = CoreSkill(backup_dir=str(tmp_path / "backups"))
    target = tmp_path / "soft_mode.py"
    target.write_text("print('before')", encoding="utf-8")

    skill.hot_patch(str(target), "print('soft-allowed')")

    entries = get_audit_stream().get_entries(action="autonomy.degraded_allow", limit=5)
    assert entries
    entry = entries[0]
    assert entry.source == "core.autonomy"
    assert entry.status == "degraded"
    assert entry.details["decision"] == "degraded_allow"
    assert entry.details["reason_code"] == "AUTONOMY_PERMISSION_DENIED"
    assert entry.details["operation"] == "core_patch"
    assert entry.details["enforcement_mode"] == "soft"
    assert entry.details["terminal"] is False
    assert entry.details["retryable"] is False
