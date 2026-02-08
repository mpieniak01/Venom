"""Moduł: routes/git - Endpointy API dla Git."""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger
from venom_core.utils.ttl_cache import TTLCache

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/git", tags=["git"])

# Cache dla statusu git (5 sekund TTL)
_git_status_cache = TTLCache[dict](ttl_seconds=5.0)


# Dependency - będzie ustawione w main.py
_git_skill = None


class InitRepoRequest(BaseModel):
    """Payload dla inicjalizacji repozytorium."""

    url: Optional[str] = None


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


def set_dependencies(git_skill):
    """Ustaw zależności dla routera."""
    global _git_skill
    _git_skill = git_skill


@router.get(
    "/status",
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

            async def run_git(args: list[str]) -> str:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(repo_root), *args],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout).strip())
                return result.stdout.strip()

            async def run_git_ok(args: list[str]) -> bool:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(repo_root), *args],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return result.returncode == 0

            try:
                await run_git(["rev-parse", "--is-inside-work-tree"])
            except RuntimeError as exc:
                return {
                    "status": "error",
                    "is_git_repo": False,
                    "message": str(exc) or "Workspace nie jest repozytorium Git.",
                }

            branch = await run_git(["rev-parse", "--abbrev-ref", "HEAD"])
            status_output = await run_git(["status"])
            porcelain = await run_git(["status", "--porcelain"])
            lines = [line for line in porcelain.splitlines() if line.strip()]
            has_changes = len(lines) > 0
            modified_count = len(lines)

            compare_branch = "main"
            compare_ref = "origin/main"
            compare_status = None
            ahead_count = 0
            behind_count = 0

            local_main_ok = await run_git_ok(
                ["show-ref", "--verify", "--quiet", "refs/heads/main"]
            )
            if not local_main_ok:
                compare_status = "no_local_main"
            else:
                remote_ok = await run_git_ok(["remote", "get-url", "origin"])
                if not remote_ok:
                    compare_status = "no_remote"
                else:
                    remote_main_ok = await run_git_ok(
                        ["show-ref", "--verify", "--quiet", "refs/remotes/origin/main"]
                    )
                    if not remote_main_ok:
                        compare_status = "no_remote_main"
                    else:
                        counts = await run_git(
                            [
                                "rev-list",
                                "--left-right",
                                "--count",
                                "origin/main...main",
                            ]
                        )
                        parts = counts.split()
                        if len(parts) == 2:
                            behind_count = int(parts[0])
                            ahead_count = int(parts[1])
                        if ahead_count > 0 and behind_count > 0:
                            compare_status = "diverged"
                        elif ahead_count > 0:
                            compare_status = "ahead"
                        elif behind_count > 0:
                            compare_status = "behind"
                        else:
                            compare_status = "equal"

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
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Git status nie jest dostępny. Upewnij się, że git jest zainstalowany.",
            )

    if _git_skill is None:
        return {
            "status": "error",
            "is_git_repo": False,
            "message": "Repozytorium Git nie zostało wykryte.",
        }

    try:
        # Pobierz aktualny branch
        branch = await _git_skill.get_current_branch()

        if _is_workspace_git_error(branch):
            return {
                "status": "error",
                "is_git_repo": False,
                "message": branch,
            }

        # Pobierz status repozytorium
        status_output = await _git_skill.get_status()
        if _is_workspace_git_error(status_output):
            return {
                "status": "error",
                "is_git_repo": False,
                "branch": branch,
                "message": status_output,
            }

        # Parsuj status aby określić czy są zmiany
        has_changes = (
            "nothing to commit" not in status_output
            and "working tree clean" not in status_output
        )

        # Użyj GitPython do dokładniejszego liczenia zmian + porównania z origin/main
        modified_count = 0
        compare_status = None
        ahead_count = 0
        behind_count = 0
        compare_ref = "origin/main"
        compare_branch = "main"
        try:
            # Pobierz obiekt Repo i policz zmiany
            from git import GitCommandError, Repo

            repo = Repo(_git_skill.workspace_root)
            # Sprawdź czy HEAD istnieje (czy repo ma commity)
            if repo.head.is_valid():
                # Zmodyfikowane i staged pliki względem HEAD
                modified_count = len(repo.index.diff("HEAD"))
            else:
                # Brak HEAD — policz tylko nieśledzone pliki
                modified_count = len(repo.untracked_files)
            # Dodaj nieśledzone pliki (jeśli HEAD istnieje)
            if repo.head.is_valid():
                modified_count += len(repo.untracked_files)

            has_remote = "origin" in repo.remotes
            has_local_main = compare_branch in repo.heads
            if not has_local_main:
                compare_status = "no_local_main"
            elif not has_remote:
                compare_status = "no_remote"
            else:
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
        except (GitCommandError, ValueError, ImportError):
            # Fallback: proste parsowanie jeśli GitPython zawiedzie (np. HEAD nie istnieje)
            lines = status_output.split("\n")
            for line in lines:
                if (
                    "modified:" in line
                    or "new file:" in line
                    or "deleted:" in line
                    or "renamed:" in line
                ):
                    modified_count += 1

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
async def sync_repository():
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
async def undo_changes():
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
