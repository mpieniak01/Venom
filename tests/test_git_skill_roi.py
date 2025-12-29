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
