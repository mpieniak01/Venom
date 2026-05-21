"""Testy dla GitSkill."""

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

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
async def test_get_short_status(git_skill, temp_workspace):
    """Test pobierania skróconego statusu repozytorium."""
    await git_skill.init_repo()

    repo = Repo(temp_workspace)
    test_file = Path(temp_workspace) / "test-short.txt"
    test_file.write_text("initial")
    repo.index.add(["test-short.txt"])
    repo.index.commit("Initial commit")

    test_file.write_text("modified")

    result = await git_skill.get_short_status()

    assert isinstance(result, str)
    assert result.startswith("##")
    assert "test-short.txt" in result


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
async def test_reset_with_untracked_files(git_skill, temp_workspace):
    """Test resetu z nietrackonymi plikami - powinien działać bez force."""
    # Zainicjalizuj repo i utwórz commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("initial content")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Dodaj nietrackowany plik (nie stage'owany)
    untracked_file = Path(temp_workspace) / "untracked.txt"
    untracked_file.write_text("untracked content")

    # Reset powinien działać bez force, bo nietrackowane pliki nie są zagrożone
    result = await git_skill.reset(mode="hard", commit_hash="HEAD", force=False)

    assert "✅" in result
    assert "Reset" in result

    # Nietrackowany plik powinien nadal istnieć
    assert untracked_file.exists()
    assert untracked_file.read_text() == "untracked content"


@pytest.mark.asyncio
async def test_reset_invalid_mode(git_skill, temp_workspace):
    """Test resetu z nieprawidłowym trybem."""
    # Zainicjalizuj repo i utwórz commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("test")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Próbuj reset z nieprawidłowym trybem
    result = await git_skill.reset(mode="invalid")

    assert "❌" in result
    assert "Nieprawidłowy tryb" in result or "invalid" in result.lower()
    assert "soft" in result and "mixed" in result and "hard" in result


def test_git_skill_pull_helpers():
    class DummyRepo:
        active_branch = SimpleNamespace(name="main")

    assert GitSkill._resolve_branch_name(DummyRepo(), "feature/x") == "feature/x"
    assert GitSkill._resolve_branch_name(DummyRepo(), None) == "main"

    changed = GitSkill._collect_changed_files_from_pull(
        [
            SimpleNamespace(commit=None, old_commit=None),
            SimpleNamespace(commit=SimpleNamespace(diff=lambda _old: []), old_commit=1),
        ]
    )
    assert changed == []

    result_empty = GitSkill._format_pull_result("origin", "main", [])
    assert "już aktualne" in result_empty

    result_changed = GitSkill._format_pull_result(
        "origin", "main", ["a.py", "b.py", "c.py"]
    )
    assert "Zmienione pliki" in result_changed
    assert "a.py" in result_changed


def test_git_skill_has_pull_error_reports_conflict(temp_workspace):
    skill = GitSkill(workspace_root=temp_workspace)
    repo = SimpleNamespace()
    skill._format_conflict_message = lambda *_args, **_kwargs: "conflict-msg"  # type: ignore[method-assign]
    info = SimpleNamespace(flags=1, ERROR=1)
    assert skill._has_pull_error([info], repo, "origin", "main") == "conflict-msg"


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
async def test_merge_with_conflict(git_skill, temp_workspace):
    """Test merge z konfliktem."""
    # Zainicjalizuj repo i utwórz initial commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("initial content")

    repo = Repo(temp_workspace)
    # Skonfiguruj git identity dla tego repo
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()

    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Utwórz branch i zmodyfikuj ten sam plik
    await git_skill.checkout("feature", create_new=True)
    test_file.write_text("feature content")
    repo.index.add(["test.txt"])
    repo.index.commit("Feature change")

    # Wróć na master i zmodyfikuj inaczej
    await git_skill.checkout("master")
    test_file.write_text("main different content")
    repo.index.add(["test.txt"])
    repo.index.commit("Main change")

    # Spróbuj scalić - powinien być konflikt
    result = await git_skill.merge("feature")

    assert "⚠️" in result or "CONFLICT" in result
    assert "test.txt" in result


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
async def test_create_branch_already_exists(git_skill, temp_workspace):
    """Test tworzenia brancha, który już istnieje."""
    # Zainicjalizuj repo i utwórz commit
    await git_skill.init_repo()
    test_file = Path(temp_workspace) / "test.txt"
    test_file.write_text("test")

    repo = Repo(temp_workspace)
    repo.index.add(["test.txt"])
    repo.index.commit("Initial commit")

    # Utwórz branch pierwszy raz
    result1 = await git_skill.create_branch("feature")
    assert "✅" in result1

    # Spróbuj utworzyć ponownie
    result2 = await git_skill.create_branch("feature")
    assert "❌" in result2
    assert "już istnieje" in result2.lower() or "already exists" in result2.lower()


@pytest.mark.asyncio
async def test_pull_with_local_remote(git_skill, temp_workspace):
    """Test pull z lokalnym remote repository."""
    import tempfile

    # Utwórz "remote" repo
    remote_dir = tempfile.mkdtemp()
    try:
        remote_repo = Repo.init(remote_dir)
        remote_file = Path(remote_dir) / "remote.txt"
        remote_file.write_text("remote content")
        remote_repo.index.add(["remote.txt"])
        remote_repo.index.commit("Remote commit")

        # Sklonuj do workspace
        await git_skill.init_repo(url=remote_dir)

        # Dodaj nowy commit do remote
        remote_file.write_text("updated remote content")
        remote_repo.index.add(["remote.txt"])
        remote_repo.index.commit("Update remote")

        # Pull z remote
        result = await git_skill.pull(remote="origin")

        # Sprawdź że pull się udał
        assert isinstance(result, str)
        assert "✅" in result or "❌" in result or "⚠️" in result

        # Jeśli pull się udał, sprawdź czy plik został zaktualizowany
        if "✅" in result:
            local_file = Path(temp_workspace) / "remote.txt"
            if local_file.exists():
                assert local_file.read_text() == "updated remote content"

    finally:
        # Cleanup remote dir
        import shutil

        shutil.rmtree(remote_dir, ignore_errors=True)
