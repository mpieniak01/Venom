from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from venom_core.api.routes import git as git_routes


class DummyGitSkill:
    def __init__(self, branch: str, status: str, workspace_root: str = "."):
        self._branch = branch
        self._status = status
        self.workspace_root = workspace_root

    async def get_current_branch(self):
        return self._branch

    async def get_status(self):
        return self._status

    async def init_repo(self, url=None):
        return "✅ initialized" if not url else "❌ failed"


@pytest.mark.asyncio
async def test_collect_compare_state_no_local_main(monkeypatch):
    async def fake_run_git_ok(_repo_root: Path, args: list[str]) -> bool:
        if args[-1] == "refs/heads/main":
            return False
        return True

    monkeypatch.setattr(git_routes, "_run_git_ok", fake_run_git_ok)

    state = await git_routes._collect_compare_state(Path("."))

    assert state["compare_status"] == "no_local_main"
    assert state["ahead_count"] == 0
    assert state["behind_count"] == 0


@pytest.mark.asyncio
async def test_collect_compare_state_diverged(monkeypatch):
    async def fake_run_git_ok(_repo_root: Path, args: list[str]) -> bool:
        return True

    async def fake_run_git(_repo_root: Path, args: list[str]) -> str:
        assert args[:3] == ["rev-list", "--left-right", "--count"]
        return "3 2"

    monkeypatch.setattr(git_routes, "_run_git_ok", fake_run_git_ok)
    monkeypatch.setattr(git_routes, "_run_git", fake_run_git)

    state = await git_routes._collect_compare_state(Path("."))

    assert state["compare_status"] == "diverged"
    assert state["behind_count"] == 3
    assert state["ahead_count"] == 2


@pytest.mark.asyncio
async def test_build_local_repo_status_returns_workspace_error(monkeypatch):
    async def fake_run_git(_repo_root: Path, _args: list[str]) -> str:
        raise RuntimeError("fatal: not a git repository")

    monkeypatch.setattr(git_routes, "_run_git", fake_run_git)

    result = await git_routes._build_local_repo_status(Path("."))

    assert result["status"] == "error"
    assert result["is_git_repo"] is False


@pytest.mark.asyncio
async def test_build_local_repo_status_success(monkeypatch):
    async def fake_run_git(_repo_root: Path, args: list[str]) -> str:
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return "feat/test"
        if args == ["status"]:
            return "On branch feat/test"
        if args == ["status", "--porcelain"]:
            return " M a.py\n?? b.py\n"
        return "true"

    async def fake_compare(_repo_root: Path) -> dict:
        return {
            "compare_branch": "main",
            "compare_ref": "origin/main",
            "compare_status": "ahead",
            "ahead_count": 1,
            "behind_count": 0,
        }

    monkeypatch.setattr(git_routes, "_run_git", fake_run_git)
    monkeypatch.setattr(git_routes, "_collect_compare_state", fake_compare)

    result = await git_routes._build_local_repo_status(Path("."))

    assert result["status"] == "success"
    assert result["branch"] == "feat/test"
    assert result["has_changes"] is True
    assert result["modified_count"] == 2
    assert result["compare_status"] == "ahead"


def test_count_modified_from_status_output():
    output = "\n".join(
        [
            "modified: a.py",
            "new file: b.py",
            "deleted: c.py",
            "renamed: d.py -> e.py",
            "nothing else",
        ]
    )
    assert git_routes._count_modified_from_status_output(output) == 4


def test_is_workspace_git_error_variants():
    assert git_routes._is_workspace_git_error("❌ błąd")
    assert git_routes._is_workspace_git_error("⚠️ warning")
    assert git_routes._is_workspace_git_error("To nie jest repozytorium Git")
    assert not git_routes._is_workspace_git_error("")
    assert not git_routes._is_workspace_git_error(123)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_git_status_impl_local_repo_path(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(
        git_routes,
        "SETTINGS",
        SimpleNamespace(REPO_ROOT=str(tmp_path), WORKSPACE_ROOT=str(tmp_path)),
    )

    async def fake_build(_repo_root: Path) -> dict:
        return {"status": "success", "branch": "local"}

    monkeypatch.setattr(git_routes, "_build_local_repo_status", fake_build)

    result = await git_routes._get_git_status_impl()
    assert result["branch"] == "local"


@pytest.mark.asyncio
async def test_get_git_status_impl_local_repo_runtime_error(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(
        git_routes,
        "SETTINGS",
        SimpleNamespace(REPO_ROOT=str(tmp_path), WORKSPACE_ROOT=str(tmp_path)),
    )

    async def boom(_repo_root: Path) -> dict:
        raise RuntimeError("git failed")

    monkeypatch.setattr(git_routes, "_build_local_repo_status", boom)

    with pytest.raises(HTTPException) as exc:
        await git_routes._get_git_status_impl()
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_git_status_impl_without_repo_and_without_skill(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        git_routes,
        "SETTINGS",
        SimpleNamespace(REPO_ROOT=str(tmp_path), WORKSPACE_ROOT=str(tmp_path)),
    )
    git_routes.set_dependencies(None)

    result = await git_routes._get_git_status_impl()
    assert result["status"] == "error"
    assert result["is_git_repo"] is False


@pytest.mark.asyncio
async def test_get_git_status_impl_git_skill_failure_raises_500(monkeypatch, tmp_path):
    monkeypatch.setattr(
        git_routes,
        "SETTINGS",
        SimpleNamespace(REPO_ROOT=str(tmp_path), WORKSPACE_ROOT=str(tmp_path)),
    )
    git_routes.set_dependencies(object())

    async def boom() -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr(git_routes, "_build_git_skill_status", boom)

    with pytest.raises(HTTPException) as exc:
        await git_routes._get_git_status_impl()
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_build_git_skill_status_branch_error():
    git_routes.set_dependencies(
        DummyGitSkill(branch="❌ not a git repo", status="", workspace_root=".")
    )
    result = await git_routes._build_git_skill_status()
    assert result["status"] == "error"
    assert result["is_git_repo"] is False


@pytest.mark.asyncio
async def test_build_git_skill_status_status_error():
    git_routes.set_dependencies(
        DummyGitSkill(
            branch="main", status="nie jest repozytorium git", workspace_root="."
        )
    )
    result = await git_routes._build_git_skill_status()
    assert result["status"] == "error"
    assert result["branch"] == "main"


@pytest.mark.asyncio
async def test_build_git_skill_status_fallback_modified_count(monkeypatch, tmp_path):
    git_routes.set_dependencies(
        DummyGitSkill(
            branch="main",
            status="modified: a.py\nnew file: b.py",
            workspace_root=str(tmp_path / "missing-repo"),
        )
    )
    monkeypatch.setattr(git_routes, "_count_modified_from_status_output", lambda _s: 2)

    result = await git_routes._build_git_skill_status()
    assert result["status"] == "success"
    assert result["modified_count"] == 2
    assert result["has_changes"] is True


@pytest.mark.asyncio
async def test_get_git_status_impl_uses_git_skill_when_no_dot_git(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        git_routes,
        "SETTINGS",
        SimpleNamespace(REPO_ROOT=str(tmp_path), WORKSPACE_ROOT=str(tmp_path)),
    )
    git_routes.set_dependencies(object())

    async def fake_build_skill() -> dict:
        return {"status": "success", "branch": "skill-branch"}

    monkeypatch.setattr(git_routes, "_build_git_skill_status", fake_build_skill)
    result = await git_routes._get_git_status_impl()
    assert result["branch"] == "skill-branch"


@pytest.mark.asyncio
async def test_init_repository_clears_cache():
    skill = DummyGitSkill(branch="main", status="ok")
    git_routes.set_dependencies(skill)
    git_routes._git_status_cache.set({"status": "success"})
    result = await git_routes.init_repository(git_routes.InitRepoRequest(url=None))
    assert result["status"] == "success"
    assert git_routes._git_status_cache.get() is None


@pytest.mark.asyncio
async def test_sync_and_undo_raise_expected_http_errors():
    git_routes.set_dependencies(None)
    with pytest.raises(HTTPException) as sync_exc:
        await git_routes.sync_repository()
    assert sync_exc.value.status_code == 503

    with pytest.raises(HTTPException) as undo_exc:
        await git_routes.undo_changes()
    assert undo_exc.value.status_code == 503

    git_routes.set_dependencies(DummyGitSkill(branch="main", status="ok"))
    with pytest.raises(HTTPException) as sync_not_impl:
        await git_routes.sync_repository()
    assert sync_not_impl.value.status_code == 501

    with pytest.raises(HTTPException) as undo_not_impl:
        await git_routes.undo_changes()
    assert undo_not_impl.value.status_code == 501
