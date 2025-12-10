"""Moduł: routes/git - Endpointy API dla Git."""

from fastapi import APIRouter, HTTPException

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/git", tags=["git"])


# Dependency - będzie ustawione w main.py
_git_skill = None


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


@router.get("/status")
async def get_git_status():
    """
    Zwraca status repozytorium Git (aktualny branch, zmiany, liczba zmodyfikowanych plików).

    Returns:
        Status repozytorium Git

    Raises:
        HTTPException: 503 jeśli GitSkill nie jest dostępny lub workspace nie jest repozytorium Git
    """
    if _git_skill is None:
        raise HTTPException(
            status_code=503,
            detail="GitSkill nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        )

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

        # Użyj GitPython do dokładniejszego liczenia zmian
        modified_count = 0
        if has_changes:
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
            except (GitCommandError, ValueError):
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
        }

    except Exception as e:
        logger.exception("Błąd podczas pobierania statusu Git")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/sync")
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


@router.post("/undo")
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
