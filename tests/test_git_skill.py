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


@pytest.mark.asyncio
async def test_reset_with_safety_guard(git_skill, temp_workspace):
    """Test resetu z zabezpieczeniem - blokada przy brudnym repo bez force."""
    # Zainicjalizuj repo i utwórz commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("initial content")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Zmodyfikuj plik (brudne repo)
    test_file.write_text("modified content")

    # Próbuj reset bez force - powinien zostać zablokowany
    result = await git_skill.reset(mode="hard", commit_hash="HEAD", force=False)

    assert "🛑" in result or "SafetyError" in result
    assert (
        "niezatwierdzone zmiany" in result.lower()
        or "uncommitted changes" in result.lower()
    )

    # Sprawdź że zmiany nadal istnieją
    assert test_file.read_text() == "modified content"


@pytest.mark.asyncio
async def test_reset_with_force(git_skill, temp_workspace):
    """Test resetu z force=True - zmiany powinny zostać usunięte."""
    # Zainicjalizuj repo i utwórz commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("initial content")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Zmodyfikuj plik
    test_file.write_text("modified content")

    # Reset z force=True
    result = await git_skill.reset(mode="hard", commit_hash="HEAD", force=True)

    assert "✅" in result
    assert "Reset" in result

    # Sprawdź że zmiany zostały usunięte
    assert test_file.read_text() == "initial content"


@pytest.mark.asyncio
async def test_reset_clean_repo(git_skill, temp_workspace):
    """Test resetu na czystym repo - powinien działać bez force."""
    # Zainicjalizuj repo i utwórz dwa commity
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("first")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("First commit")

    test_file.write_text("second")
    repo.index.add(["test.txt"])
    repo.index.commit("Second commit")

    # Reset do poprzedniego commita (bez force, bo repo czyste)
    result = await git_skill.reset(mode="hard", commit_hash="HEAD~1", force=False)

    assert "✅" in result
    assert "Reset" in result

    # Sprawdź że cofnęliśmy się do pierwszego commita
    assert test_file.read_text() == "first"


@pytest.mark.asyncio
async def test_merge_success(git_skill, temp_workspace):
    """Test pomyślnego merge dwóch branchy."""
    # Zainicjalizuj repo i utwórz initial commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("main content")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit on main")

    # Utwórz i przełącz się na nowy branch
    await git_skill.checkout("feature-branch", create_new=True)

    # Zmodyfikuj plik na feature branch
    feature_file = Path(temp_workspace) / "feature.txt"
    feature_file.write_text("feature content")
    repo.index.add(["feature.txt"])
    repo.index.commit("Add feature file")

    # Wróć na main
    await git_skill.checkout("main")

    # Scal feature branch do main
    result = await git_skill.merge("feature-branch")

    assert "✅" in result
    assert "scalono" in result.lower() or "merge" in result.lower()

    # Sprawdź że plik z feature branch jest teraz na main
    assert feature_file.exists()


@pytest.mark.asyncio
async def test_create_branch(git_skill, temp_workspace):
    """Test tworzenia nowego brancha bez przełączania."""
    # Zainicjalizuj repo i utwórz commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("test")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    current_branch = repo.active_branch.name

    # Utwórz nowy branch
    result = await git_skill.create_branch("new-feature")

    assert "✅" in result
    assert "new-feature" in result

    # Sprawdź że branch został utworzony
    assert "new-feature" in [b.name for b in repo.branches]

    # Sprawdź że nadal jesteśmy na poprzednim branchu
    assert repo.active_branch.name == current_branch


@pytest.mark.asyncio
async def test_pull_already_up_to_date(git_skill, temp_workspace):
    """Test pull gdy repo jest już aktualne."""
    # Ten test wymaga zdalnego repo, więc symulujemy sytuację
    # Zainicjalizuj repo
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("test")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Pull bez remote da błąd, ale testujemy format odpowiedzi
    result = await git_skill.pull(remote="origin", branch="main")

    # Oczekujemy błędu Git (brak remote), ale struktura odpowiedzi powinna być poprawna
    assert isinstance(result, str)
    # Odpowiedź powinna być czytelna
    assert "❌" in result or "✅" in result or "⚠️" in result
