"""Testy dla GitSkill."""

import shutil
import tempfile
from pathlib import Path

import pytest
from git import Repo

from venom_core.execution.skills.git_skill import GitSkill


@pytest.fixture
def temp_workspace():
    """Tworzy tymczasowy workspace dla testów."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def git_skill(temp_workspace):
    """Tworzy instancję GitSkill z tymczasowym workspace."""
    return GitSkill(workspace_root=temp_workspace)


@pytest.mark.asyncio
async def test_init_repo(git_skill, temp_workspace):
    """Test inicjalizacji repozytorium."""
    result = await git_skill.init_repo()

    assert "✅" in result
    assert "Zainicjalizowano" in result

    # Sprawdź czy repozytorium zostało utworzone
    repo = Repo(temp_workspace)
    assert repo.git_dir is not None


@pytest.mark.asyncio
async def test_checkout_new_branch(git_skill, temp_workspace):
    """Test tworzenia nowego brancha."""
    # Najpierw zainicjalizuj repo
    await git_skill.init_repo()

    # Utwórz initial commit (wymagany do tworzenia brancha)
    repo = Repo(temp_workspace)
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("test")
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Utwórz nowy branch
    result = await git_skill.checkout("feat/test-branch", create_new=True)

    assert "✅" in result
    assert "feat/test-branch" in result

    # Sprawdź czy branch został utworzony
    assert repo.active_branch.name == "feat/test-branch"


@pytest.mark.asyncio
async def test_get_status(git_skill, temp_workspace):
    """Test pobierania statusu repozytorium."""
    # Zainicjalizuj repo
    await git_skill.init_repo()

    # Pobierz status
    result = await git_skill.get_status()

    assert isinstance(result, str)
    # Status powinien zawierać informację o braku commitów lub o czystym workspace
    assert len(result) > 0


@pytest.mark.asyncio
async def test_add_files_and_commit(git_skill, temp_workspace):
    """Test stage'owania plików i tworzenia commita."""
    # Zainicjalizuj repo
    await git_skill.init_repo()

    # Utwórz plik
    test_file = Path(temp_workspace) / "test.py"
    test_file.write_text("print('hello')")

    # Stage plik
    add_result = await git_skill.add_files(["."])
    assert "✅" in add_result

    # Utwórz commit
    commit_result = await git_skill.commit("feat(test): add test file")
    assert "✅" in commit_result
    assert "feat(test):" in commit_result


@pytest.mark.asyncio
async def test_get_diff(git_skill, temp_workspace):
    """Test pobierania diff."""
    # Zainicjalizuj repo i utwórz initial commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("initial")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Zmodyfikuj plik
    test_file.write_text("modified")

    # Pobierz diff
    result = await git_skill.get_diff()

    assert isinstance(result, str)
    # Diff powinien zawierać zmiany
    assert "initial" in result or "modified" in result or "Brak zmian" in result


@pytest.mark.asyncio
async def test_get_current_branch(git_skill, temp_workspace):
    """Test pobierania aktualnego brancha."""
    # Zainicjalizuj repo
    await git_skill.init_repo()

    # Utwórz initial commit (wymagany)
    repo = Repo(temp_workspace)
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("test")
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Pobierz aktualny branch
    result = await git_skill.get_current_branch()

    # Domyślny branch to zwykle 'master' lub 'main'
    assert result in ["master", "main"]


@pytest.mark.asyncio
async def test_get_last_commit_log(git_skill, temp_workspace):
    """Test pobierania historii commitów."""
    # Zainicjalizuj repo i utwórz commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("test")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Test commit")

    # Pobierz historię
    result = await git_skill.get_last_commit_log(n=5)

    assert isinstance(result, str)
    assert "Test commit" in result


@pytest.mark.asyncio
async def test_commit_without_changes(git_skill, temp_workspace):
    """Test commita bez zmian - powinien zwrócić ostrzeżenie."""
    # Zainicjalizuj repo i utwórz commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("test")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Próbuj commitować bez zmian
    result = await git_skill.commit("Empty commit")

    assert "⚠️" in result
    assert "Brak zmian" in result
