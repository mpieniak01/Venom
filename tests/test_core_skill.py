"""Testy jednostkowe dla CoreSkill."""

from pathlib import Path

import pytest

import venom_core.execution.skills.core_skill as core_skill_module
from venom_core.execution.skills.core_skill import CoreSkill


@pytest.fixture
def allowed_core_skill(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> CoreSkill:
    monkeypatch.setattr(
        core_skill_module, "require_core_patch_permission", lambda: None
    )
    return CoreSkill(backup_dir=str(tmp_path / "backups"))


def test_hot_patch_missing_file_returns_error(
    allowed_core_skill: CoreSkill, tmp_path: Path
) -> None:
    result = allowed_core_skill.hot_patch(str(tmp_path / "missing.py"), "print('x')")
    assert "nie istnieje" in result


def test_hot_patch_rejects_directory(
    allowed_core_skill: CoreSkill, tmp_path: Path
) -> None:
    result = allowed_core_skill.hot_patch(str(tmp_path), "print('x')")
    assert "jest katalogiem" in result


def test_hot_patch_writes_file_and_creates_backup(
    allowed_core_skill: CoreSkill, tmp_path: Path
) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('before')\n", encoding="utf-8")

    result = allowed_core_skill.hot_patch(str(target), "print('after')\n")

    assert "został zmodyfikowany" in result
    assert "Backup:" in result
    assert target.read_text(encoding="utf-8") == "print('after')\n"
    backups = list(allowed_core_skill.get_backup_dir().glob("sample.py.*.bak"))
    assert len(backups) == 1


def test_rollback_returns_error_when_no_backups(
    allowed_core_skill: CoreSkill, tmp_path: Path
) -> None:
    target = tmp_path / "restore_me.py"
    target.write_text("new", encoding="utf-8")

    result = allowed_core_skill.rollback(str(target))
    assert "Brak backupów" in result


def test_rollback_with_specific_backup_restores_file(
    allowed_core_skill: CoreSkill, tmp_path: Path
) -> None:
    target = tmp_path / "app.py"
    target.write_text("broken\n", encoding="utf-8")
    backup = allowed_core_skill.get_backup_dir() / "app.py.manual.bak"
    backup.write_text("healthy\n", encoding="utf-8")

    result = allowed_core_skill.rollback(str(target), str(backup))

    assert "przywrócony z backupu" in result
    assert target.read_text(encoding="utf-8") == "healthy\n"


def test_rollback_returns_error_for_missing_backup(
    allowed_core_skill: CoreSkill, tmp_path: Path
) -> None:
    target = tmp_path / "app.py"
    target.write_text("broken\n", encoding="utf-8")

    result = allowed_core_skill.rollback(
        str(target), str(allowed_core_skill.get_backup_dir() / "missing.bak")
    )
    assert "Backup" in result
    assert "nie istnieje" in result


def test_list_backups_empty_and_filtered(
    allowed_core_skill: CoreSkill, tmp_path: Path
) -> None:
    assert allowed_core_skill.list_backups() == "Brak backupów"

    (allowed_core_skill.get_backup_dir() / "a.py.1.bak").write_text(
        "a", encoding="utf-8"
    )
    (allowed_core_skill.get_backup_dir() / "b.py.1.bak").write_text(
        "b", encoding="utf-8"
    )

    result = allowed_core_skill.list_backups(str(tmp_path / "a.py"))
    assert "a.py.1.bak" in result
    assert "b.py.1.bak" not in result


def test_restart_service_requires_confirmation(allowed_core_skill: CoreSkill) -> None:
    result = allowed_core_skill.restart_service(confirm=False)
    assert "wymaga potwierdzenia" in result


def test_restart_service_handles_execv_exception(
    allowed_core_skill: CoreSkill, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_execv(*_args, **_kwargs):
        raise RuntimeError("execv failed")

    monkeypatch.setattr(core_skill_module.os, "execv", _raise_execv)
    result = allowed_core_skill.restart_service(confirm=True)
    assert "Błąd podczas restartu" in result


def test_verify_syntax_success_and_wrong_extension(
    allowed_core_skill: CoreSkill, tmp_path: Path
) -> None:
    py_file = tmp_path / "ok.py"
    py_file.write_text("x = 1\n", encoding="utf-8")
    assert "jest poprawna" in allowed_core_skill.verify_syntax(str(py_file))

    txt_file = tmp_path / "readme.txt"
    txt_file.write_text("hello", encoding="utf-8")
    assert "nie jest plikiem Python" in allowed_core_skill.verify_syntax(str(txt_file))


def test_verify_syntax_reports_syntax_error(
    allowed_core_skill: CoreSkill, tmp_path: Path
) -> None:
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("def broken(:\n    pass\n", encoding="utf-8")

    result = allowed_core_skill.verify_syntax(str(bad_file))
    assert "Błąd składni" in result
    assert "Linia" in result
