from types import SimpleNamespace

import pytest
from git import InvalidGitRepositoryError

from venom_core.execution.skills.git_skill import GitSkill


def test_get_repo_missing_repository(tmp_path):
    skill = GitSkill(workspace_root=str(tmp_path))
    with pytest.raises(InvalidGitRepositoryError) as exc:
        skill._get_repo()
    assert "nie jest repozytorium Git" in str(exc.value)


def test_format_conflict_message_lists_files():
    skill = GitSkill(workspace_root=".")
    repo = SimpleNamespace(
        index=SimpleNamespace(unmerged_blobs=lambda: {"a.py": None, "b.txt": None})
    )
    message = skill._format_conflict_message(repo, "merge", "feature-x")
    assert "CONFLICT" in message
    assert "a.py" in message
    assert "b.txt" in message


def test_pull_helper_methods_cover_new_paths(tmp_path):
    skill = GitSkill(workspace_root=str(tmp_path))
    repo = SimpleNamespace(active_branch=SimpleNamespace(name="main"))

    assert skill._resolve_branch_name(repo, "feature/z") == "feature/z"
    assert skill._resolve_branch_name(repo, None) == "main"

    info_ok = SimpleNamespace(flags=0, ERROR=1)
    assert skill._has_pull_error([info_ok], repo, "origin", "main") is None

    skill._format_conflict_message = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: "conflict"
    )
    info_err = SimpleNamespace(flags=1, ERROR=1)
    assert skill._has_pull_error([info_err], repo, "origin", "main") == "conflict"

    class DiffItem:
        def __init__(self, a, b):
            self.a_path = a
            self.b_path = b

    info_with_diff = SimpleNamespace(
        commit=SimpleNamespace(
            diff=lambda _old: [DiffItem("a.py", None), DiffItem(None, "b.py")]
        ),
        old_commit=object(),
    )
    changed = skill._collect_changed_files_from_pull(
        [SimpleNamespace(commit=None, old_commit=None), info_with_diff]
    )
    assert changed == ["a.py", "b.py"]

    assert "już aktualne" in skill._format_pull_result("origin", "main", [])
    many_files = [f"f{i}.py" for i in range(12)]
    formatted = skill._format_pull_result("origin", "main", many_files)
    assert "Zmienione pliki" in formatted
    assert "... i 2 więcej" in formatted
