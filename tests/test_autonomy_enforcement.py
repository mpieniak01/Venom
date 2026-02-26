"""Unit tests for autonomy enforcement guard helpers."""

import pytest

from venom_core.core import autonomy_enforcement as ae
from venom_core.services.audit_stream import get_audit_stream


def test_require_file_write_permission_allows(monkeypatch):
    monkeypatch.setattr(ae.permission_guard, "can_write_files", lambda: True)
    ae.require_file_write_permission()


def test_require_file_write_permission_denies(monkeypatch):
    monkeypatch.setattr(ae.permission_guard, "can_write_files", lambda: False)
    monkeypatch.setattr(
        ae.permission_guard, "get_current_level_name", lambda: "ISOLATED"
    )
    with pytest.raises(PermissionError) as exc:
        ae.require_file_write_permission()
    assert "Brak uprawnień do zapisu plików" in str(exc.value)


def test_require_shell_permission_allows(monkeypatch):
    monkeypatch.setattr(ae.permission_guard, "can_execute_shell", lambda: True)
    ae.require_shell_permission()


def test_require_shell_permission_denies(monkeypatch):
    monkeypatch.setattr(ae.permission_guard, "can_execute_shell", lambda: False)
    monkeypatch.setattr(ae.permission_guard, "get_current_level_name", lambda: "SCOUT")
    with pytest.raises(PermissionError) as exc:
        ae.require_shell_permission()
    assert "Brak uprawnień do shella" in str(exc.value)


def test_require_core_patch_permission_allows(monkeypatch):
    monkeypatch.setattr(ae.permission_guard, "get_current_level", lambda: 40)
    ae.require_core_patch_permission()


def test_require_core_patch_permission_denies(monkeypatch):
    monkeypatch.setattr(ae.permission_guard, "get_current_level", lambda: 20)
    monkeypatch.setattr(
        ae.permission_guard, "get_current_level_name", lambda: "BUILDER"
    )
    with pytest.raises(PermissionError) as exc:
        ae.require_core_patch_permission()
    assert "wymagany: ROOT" in str(exc.value)


def test_deny_publishes_optional_audit_details(monkeypatch):
    audit_stream = get_audit_stream()
    audit_stream.clear()
    monkeypatch.setattr(ae.permission_guard, "get_current_level", lambda: 20)
    monkeypatch.setattr(
        ae.permission_guard, "get_current_level_name", lambda: "BUILDER"
    )

    with pytest.raises(PermissionError, match="blocked"):
        ae._deny(
            "blocked",
            operation="custom_operation",
            required_level=30,
            required_level_name="EXECUTOR",
            skill_name="mcp_skill",
            task_id="task-123",
            session_id="session-456",
        )

    entries = audit_stream.get_entries(action="autonomy.blocked", limit=5)
    assert entries
    details = entries[0].details
    assert details["operation"] == "custom_operation"
    assert details["current_level"] == 20
    assert details["current_level_name"] == "BUILDER"
    assert details["required_level"] == 30
    assert details["required_level_name"] == "EXECUTOR"
    assert details["skill_name"] == "mcp_skill"
    assert details["task_id"] == "task-123"
    assert details["session_id"] == "session-456"
