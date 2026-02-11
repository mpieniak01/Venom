"""Testy jednostkowe dla FileSkill."""

import tempfile
from pathlib import Path

import pytest

from venom_core.core.permission_guard import permission_guard
from venom_core.execution.skills.file_skill import FileSkill


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(autouse=True)
def _allow_file_writes_for_tests():
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(30)
    try:
        yield
    finally:
        permission_guard.set_level(previous_level)


def test_file_skill_initialization(temp_workspace):
    """Test inicjalizacji FileSkill."""
    skill = FileSkill(workspace_root=temp_workspace)
    assert skill.workspace_root == Path(temp_workspace).resolve()
    assert skill.workspace_root.exists()


@pytest.mark.asyncio
async def test_write_file_success(temp_workspace):
    """Test zapisu pliku."""
    skill = FileSkill(workspace_root=temp_workspace)
    content = "print('Hello World')"
    result = await skill.write_file("test.py", content)

    assert "pomyślnie zapisany" in result
    assert (Path(temp_workspace) / "test.py").exists()
    assert (Path(temp_workspace) / "test.py").read_text() == content


@pytest.mark.asyncio
async def test_write_file_with_subdirectory(temp_workspace):
    """Test zapisu pliku w podkatalogu."""
    skill = FileSkill(workspace_root=temp_workspace)
    content = "test content"
    result = await skill.write_file("subdir/nested/file.txt", content)

    assert "pomyślnie zapisany" in result
    file_path = Path(temp_workspace) / "subdir" / "nested" / "file.txt"
    assert file_path.exists()
    assert file_path.read_text() == content


@pytest.mark.asyncio
async def test_read_file_success(temp_workspace):
    """Test odczytu pliku."""
    skill = FileSkill(workspace_root=temp_workspace)
    content = "test content"

    # Najpierw zapisz plik
    await skill.write_file("test.txt", content)

    # Następnie odczytaj
    read_content = await skill.read_file("test.txt")
    assert read_content == content


@pytest.mark.asyncio
async def test_read_file_not_found(temp_workspace):
    """Test odczytu nieistniejącego pliku."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Expect error string, not exception
    result = await skill.read_file("nonexistent.txt")
    assert "Wystąpił błąd" in result
    assert "nie istnieje" in result


def test_list_files_empty_directory(temp_workspace):
    """Test listowania pustego katalogu."""
    skill = FileSkill(workspace_root=temp_workspace)
    result = skill.list_files(".")

    assert "jest pusty" in result


@pytest.mark.asyncio
async def test_list_files_with_content(temp_workspace):
    """Test listowania katalogu z plikami."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Utwórz kilka plików
    await skill.write_file("file1.txt", "content1")
    await skill.write_file("file2.py", "content2")
    await skill.write_file("subdir/file3.txt", "content3")

    result = skill.list_files(".")

    assert "file1.txt" in result
    assert "file2.py" in result
    assert "subdir" in result


@pytest.mark.asyncio
async def test_file_exists_true(temp_workspace):
    """Test sprawdzenia istnienia pliku - plik istnieje."""
    skill = FileSkill(workspace_root=temp_workspace)
    await skill.write_file("exists.txt", "content")

    result = skill.file_exists("exists.txt")
    assert result == "True"


def test_file_exists_false(temp_workspace):
    """Test sprawdzenia istnienia pliku - plik nie istnieje."""
    skill = FileSkill(workspace_root=temp_workspace)

    result = skill.file_exists("nonexistent.txt")
    assert result == "False"


@pytest.mark.asyncio
async def test_path_traversal_attack_parent(temp_workspace):
    """Test ochrony przed path traversal z ../"""
    skill = FileSkill(workspace_root=temp_workspace)

    # Expect error string
    result = await skill.write_file("../../etc/passwd", "malicious content")
    assert "Odmowa dostępu" in result or "Wystąpił błąd" in result


@pytest.mark.asyncio
async def test_path_traversal_attack_absolute(temp_workspace):
    """Test ochrony przed path traversal z absolutną ścieżką."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Expect error string
    result = await skill.write_file("/etc/passwd", "malicious content")
    assert "Odmowa dostępu" in result or "Wystąpił błąd" in result


@pytest.mark.asyncio
async def test_path_traversal_attack_read(temp_workspace):
    """Test ochrony przed path traversal przy odczycie."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Expect error string
    result = await skill.read_file("../../../etc/passwd")
    assert "Odmowa dostępu" in result or "Wystąpił błąd" in result


def test_path_traversal_attack_list(temp_workspace):
    """Test ochrony przed path traversal przy listowaniu."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Expect error string
    result = skill.list_files("../../")
    assert "Odmowa dostępu" in result or "Wystąpił błąd" in result


def test_path_traversal_attack_exists(temp_workspace):
    """Test ochrony przed path traversal przy sprawdzaniu istnienia."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Expect error string
    result = skill.file_exists("../../../etc/passwd")
    assert "Odmowa dostępu" in result or "Wystąpił błąd" in result


def test_list_files_recursive_and_helper_branches(temp_workspace):
    skill = FileSkill(workspace_root=temp_workspace)
    root = Path(temp_workspace)
    (root / "a").mkdir()
    (root / "a" / "nested").mkdir()
    (root / "a" / "f.txt").write_text("ok")

    output = skill.list_files("a", recursive=True, max_depth=1)
    assert "rekurencyjnie" in output
    assert "[plik]" in output

    depth = skill._get_relative_depth(str(root / "a" / "nested"), root / "a")
    assert depth == 1
    assert skill._get_relative_depth("/outside/root", root / "a") == 0

    items: list[str] = []
    skill._append_recursive_dirs(
        items, ["nested"], str(root / "a"), depth=0, max_depth=1
    )
    assert any("nested/" in item for item in items)

    skipped = skill._append_recursive_files(items, ["missing.txt"], str(root / "a"), "")
    assert skipped == 1


@pytest.mark.asyncio
async def test_overwrite_file(temp_workspace):
    """Test nadpisania istniejącego pliku."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Zapisz plik
    await skill.write_file("test.txt", "original content")
    assert (Path(temp_workspace) / "test.txt").read_text() == "original content"

    # Nadpisz
    await skill.write_file("test.txt", "new content")
    assert (Path(temp_workspace) / "test.txt").read_text() == "new content"


@pytest.mark.asyncio
async def test_read_directory_as_file(temp_workspace):
    """Test próby odczytu katalogu jako pliku."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Utwórz podkatalog
    (Path(temp_workspace) / "subdir").mkdir()

    # Expect error string
    result = await skill.read_file("subdir")
    assert "Wystąpił błąd" in result
    assert "nie jest plikiem" in result


@pytest.mark.asyncio
async def test_empty_path_validation(temp_workspace):
    """Test walidacji pustych ścieżek."""
    skill = FileSkill(workspace_root=temp_workspace)

    # Test pustego stringa
    # Expect error string
    result = await skill.write_file("", "content")
    assert "Wystąpił błąd" in result
    assert "nie może być pusta" in result

    # Test stringa ze spacjami
    result = await skill.write_file("   ", "content")
    assert "Wystąpił błąd" in result
    assert "nie może być pusta" in result


@pytest.mark.asyncio
async def test_symlink_security(temp_workspace):
    """Test ochrony przed symlinkami wskazującymi poza workspace."""
    import os

    skill = FileSkill(workspace_root=temp_workspace)

    # Utwórz symlink wskazujący poza workspace
    symlink_path = Path(temp_workspace) / "evil_link"
    try:
        os.symlink("/etc", str(symlink_path))

        # Próba zapisu przez symlink powinna być zablokowana
        # Expect error string
        result = await skill.write_file("evil_link/passwd", "malicious")

        assert "Odmowa dostępu" in result or "Wystąpił błąd" in result

    except OSError:
        # Jeśli nie można utworzyć symlinku (np. brak uprawnień), pomiń test
        pytest.skip("Nie można utworzyć symlinku w tym środowisku")
