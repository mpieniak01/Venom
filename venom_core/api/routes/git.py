"""Moduł: routes/git - Endpointy API dla Git."""

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from venom_core.api.schemas.git import GitStatusResponse, InitRepoRequest
from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger
from venom_core.utils.ttl_cache import TTLCache

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/git", tags=["git"])

# Cache dla statusu git (5 sekund TTL)
_git_status_cache = TTLCache[dict](ttl_seconds=5.0)
DEFAULT_COMPARE_BRANCH = "main"
DEFAULT_COMPARE_REF = "origin/main"


# Dependency - będzie ustawione w main.py
_git_skill = None


def _workspace_not_git_response(message: str) -> dict:
    return {
        "status": "error",
        "is_git_repo": False,
        "message": message,
    }


async def _run_git_command(
    repo_root: Path, args: list[str]
) -> subprocess.CompletedProcess:
    return await asyncio.to_thread(
        subprocess.run,
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


async def _run_git(repo_root: Path, args: list[str]) -> str:
    result = await _run_git_command(repo_root, args)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


async def _run_git_ok(repo_root: Path, args: list[str]) -> bool:
    result = await _run_git_command(repo_root, args)
    return result.returncode == 0


async def _collect_compare_state(repo_root: Path) -> dict:
    local_main_ok = await _run_git_ok(
        repo_root,
        ["show-ref", "--verify", "--quiet", f"refs/heads/{DEFAULT_COMPARE_BRANCH}"],
    )
    if not local_main_ok:
        return _build_compare_state("no_local_main", ahead_count=0, behind_count=0)

    remote_ok = await _run_git_ok(repo_root, ["remote", "get-url", "origin"])
    if not remote_ok:
        return _build_compare_state("no_remote", ahead_count=0, behind_count=0)

    remote_main_ok = await _run_git_ok(
        repo_root,
        ["show-ref", "--verify", "--quiet", "refs/remotes/origin/main"],
    )
    if not remote_main_ok:
        return _build_compare_state("no_remote_main", ahead_count=0, behind_count=0)

    ahead_count, behind_count = await _collect_ahead_behind_counts(repo_root)
    compare_status = _resolve_compare_status(ahead_count, behind_count)
    return _build_compare_state(
        compare_status,
        ahead_count=ahead_count,
        behind_count=behind_count,
    )


async def _collect_ahead_behind_counts(repo_root: Path) -> tuple[int, int]:
    counts = await _run_git(
        repo_root,
        [
            "rev-list",
            "--left-right",
            "--count",
            f"{DEFAULT_COMPARE_REF}...{DEFAULT_COMPARE_BRANCH}",
        ],
    )
    parts = counts.split()
    if len(parts) != 2:
        return 0, 0
    behind_count = int(parts[0])
    ahead_count = int(parts[1])
    return ahead_count, behind_count


def _build_compare_state(
    compare_status: str | None, *, ahead_count: int, behind_count: int
) -> dict:
    return {
        "compare_branch": DEFAULT_COMPARE_BRANCH,
        "compare_ref": DEFAULT_COMPARE_REF,
        "compare_status": compare_status,
        "ahead_count": ahead_count,
        "behind_count": behind_count,
    }


def _resolve_compare_status(ahead_count: int, behind_count: int) -> str:
    if ahead_count > 0 and behind_count > 0:
        return "diverged"
    if ahead_count > 0:
        return "ahead"
    if behind_count > 0:
        return "behind"
    return "equal"


async def _build_local_repo_status(repo_root: Path) -> dict:
    try:
        await _run_git(repo_root, ["rev-parse", "--is-inside-work-tree"])
    except RuntimeError as exc:
        return _workspace_not_git_response(
            str(exc) or "Workspace nie jest repozytorium Git."
        )

    branch = await _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    status_output = await _run_git(repo_root, ["status"])
    porcelain = await _run_git(repo_root, ["status", "--porcelain"])
    lines = [line for line in porcelain.splitlines() if line.strip()]
    has_changes = len(lines) > 0
    modified_count = len(lines)
    compare_state = await _collect_compare_state(repo_root)
    return {
        "status": "success",
        "is_git_repo": True,
        "branch": branch,
        "has_changes": has_changes,
        "modified_count": modified_count,
        "status_output": status_output,
        **compare_state,
    }


def _count_modified_from_status_output(status_output: str) -> int:
    modified_count = 0
    for line in status_output.split("\n"):
        if (
            "modified:" in line
            or "new file:" in line
            or "deleted:" in line
            or "renamed:" in line
        ):
            modified_count += 1
    return modified_count


def _build_skill_compare_state(repo) -> tuple[str | None, int, int]:
    compare_ref = DEFAULT_COMPARE_REF
    compare_branch = DEFAULT_COMPARE_BRANCH
    compare_status = None
    ahead_count = 0
    behind_count = 0

    has_remote = "origin" in repo.remotes
    has_local_main = compare_branch in repo.heads
    if not has_local_main:
        return "no_local_main", ahead_count, behind_count
    if not has_remote:
        return "no_remote", ahead_count, behind_count

    from git import GitCommandError

    try:
        repo.commit(compare_ref)
    except (ValueError, GitCommandError):
        compare_status = "no_remote_main"
    else:
        ahead_count = sum(
            1 for _ in repo.iter_commits(f"{compare_ref}..{compare_branch}")
        )
        behind_count = sum(
            1 for _ in repo.iter_commits(f"{compare_branch}..{compare_ref}")
        )
        if ahead_count > 0 and behind_count > 0:
            compare_status = "diverged"
        elif ahead_count > 0:
            compare_status = "ahead"
        elif behind_count > 0:
            compare_status = "behind"
        else:
            compare_status = "equal"
    return compare_status, ahead_count, behind_count


def _build_skill_modified_count(repo) -> int:
    if repo.head.is_valid():
        return len(repo.index.diff("HEAD")) + len(repo.untracked_files)
    return len(repo.untracked_files)


async def _build_git_skill_status() -> dict:
    if _git_skill is None:
        return _workspace_not_git_response("Repozytorium Git nie zostało wykryte.")

    branch = await _git_skill.get_current_branch()
    if _is_workspace_git_error(branch):
        return _workspace_not_git_response(branch)

    status_output = await _git_skill.get_status()
    if _is_workspace_git_error(status_output):
        return {
            "status": "error",
            "is_git_repo": False,
            "branch": branch,
            "message": status_output,
        }

    has_changes = (
        "nothing to commit" not in status_output
        and "working tree clean" not in status_output
    )

    modified_count = 0
    compare_status = None
    ahead_count = 0
    behind_count = 0
    compare_ref = DEFAULT_COMPARE_REF
    compare_branch = DEFAULT_COMPARE_BRANCH
    try:
        from git import Repo

        repo = Repo(_git_skill.workspace_root)
        modified_count = _build_skill_modified_count(repo)
        compare_status, ahead_count, behind_count = _build_skill_compare_state(repo)
    except Exception:
        modified_count = _count_modified_from_status_output(status_output)

    return {
        "status": "success",
        "is_git_repo": True,
        "branch": branch,
        "has_changes": has_changes,
        "modified_count": modified_count,
        "status_output": status_output,
        "compare_branch": compare_branch,
        "compare_ref": compare_ref,
        "compare_status": compare_status,
        "ahead_count": ahead_count,
        "behind_count": behind_count,
    }


def _is_workspace_git_error(message: str) -> bool:
    """Sprawdza, czy komunikat pochodzi z GitSkill i oznacza brak repozytorium."""
    if not isinstance(message, str):
        return False
    msg = message.strip()
    if not msg:
        return False
    normalized = msg.lower()
    return (
        msg.startswith("❌")
        or msg.startswith("⚠️")
        or "nie jest repozytorium git" in normalized
    )


def set_dependencies(git_skill: Any):
    """Ustaw zależności dla routera."""
    global _git_skill
    _git_skill = git_skill


@router.get(
    "/status",
    response_model=GitStatusResponse,
    responses={
        503: {"description": "Git status nie jest dostępny"},
        500: {"description": "Błąd wewnętrzny podczas pobierania statusu Git"},
    },
)
async def get_git_status():
    """
    Zwraca status repozytorium Git (aktualny branch, zmiany, liczba zmodyfikowanych plików).

    Returns:
        Status repozytorium Git

    Raises:
        HTTPException: 503 jeśli GitSkill nie jest dostępny lub workspace nie jest repozytorium Git
    """
    cached = _git_status_cache.get()
    if cached is not None:
        return cached

    res = await _get_git_status_impl()
    _git_status_cache.set(res)
    return res


async def _get_git_status_impl():
    """Implementacja pobierania statusu git (bez cache)."""
    repo_root = Path(getattr(SETTINGS, "REPO_ROOT", SETTINGS.WORKSPACE_ROOT)).resolve()
    if (repo_root / ".git").exists():
        try:
            return await _build_local_repo_status(repo_root)
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Git status nie jest dostępny. Upewnij się, że git jest zainstalowany.",
            )

    if _git_skill is None:
        return _workspace_not_git_response("Repozytorium Git nie zostało wykryte.")

    try:
        return await _build_git_skill_status()

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Git")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post(
    "/init",
    responses={
        503: {"description": "GitSkill nie jest dostępny"},
    },
)
async def init_repository(request: InitRepoRequest):
    """
    Inicjalizuje repozytorium w workspace lub klonuje istniejące.

    Args:
        request: Payload zawierający opcjonalny URL do klonowania
    """
    if _git_skill is None:
        raise HTTPException(
            status_code=503,
            detail="GitSkill nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        )

    result = await _git_skill.init_repo(url=request.url)
    status = "success" if result.startswith("✅") else "error"
    if status == "success":
        # Unieważnij cache, aby UI od razu pokazało nowe repozytorium
        _git_status_cache.clear()
    return {"status": status, "message": result}


@router.post(
    "/sync",
    responses={
        503: {"description": "GitSkill nie jest dostępny"},
        501: {"description": "Synchronizacja repozytorium nie jest zaimplementowana"},
    },
)
def sync_repository():
    """
    Synchronizuje repozytorium (pull z remote).

    Returns:
        Wynik synchronizacji

    Raises:
        HTTPException: 501 jeśli nie zaimplementowano, 503 jeśli GitSkill nie jest dostępny
    """
    if _git_skill is None:
        raise HTTPException(status_code=503, detail="GitSkill nie jest dostępny")

    # Feature nie jest jeszcze zaimplementowana - wymaga dodania metody pull() do GitSkill
    raise HTTPException(
        status_code=501,
        detail="Synchronizacja (git pull) nie jest jeszcze zaimplementowana. Użyj Integrator Agent lub wykonaj manualnie.",
    )


@router.post(
    "/undo",
    responses={
        503: {"description": "GitSkill nie jest dostępny"},
        501: {"description": "Cofnięcie zmian nie jest zaimplementowane"},
    },
)
def undo_changes():
    """
    Cofa wszystkie niezapisane zmiany (git reset --hard).

    UWAGA: To jest destrukcyjna operacja!

    Returns:
        Wynik cofnięcia zmian

    Raises:
        HTTPException: 501 jeśli nie zaimplementowano, 503 jeśli GitSkill nie jest dostępny
    """
    if _git_skill is None:
        raise HTTPException(status_code=503, detail="GitSkill nie jest dostępny")

    # Feature nie jest jeszcze zaimplementowana - wymaga dodania metody reset() do GitSkill
    raise HTTPException(
        status_code=501,
        detail="Cofnięcie zmian (git reset) nie jest jeszcze zaimplementowane. Użyj Integrator Agent z odpowiednim potwierdzeniem.",
    )
