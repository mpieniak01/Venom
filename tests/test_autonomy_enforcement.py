"""Unit tests for autonomy enforcement guard helpers."""

import pytest

from venom_core.core import autonomy_enforcement as ae


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
