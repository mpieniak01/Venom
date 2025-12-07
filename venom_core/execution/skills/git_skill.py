"""Moduł: git_skill - zarządzanie operacjami Git."""

from pathlib import Path
from typing import Annotated, List, Optional

from git import GitCommandError, InvalidGitRepositoryError, Repo
from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class GitSkill:
    """
    Skill do operacji Git w workspace.
    Umożliwia zarządzanie repozytorium, branchami, commitami i synchronizacją.

    UWAGA: GitSkill działa na HOŚCIE (nie w Dockerze), aby mieć dostęp do
    kluczy SSH użytkownika. Operacje są wykonywane na WORKSPACE_ROOT.
    """

    def __init__(self, workspace_root: str = None):
        """
        Inicjalizacja GitSkill.

        Args:
            workspace_root: Katalog workspace (domyślnie z SETTINGS.WORKSPACE_ROOT)
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        logger.info(f"GitSkill zainicjalizowany z workspace: {self.workspace_root}")

        # Upewnij się, że katalog workspace istnieje
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def _get_repo(self) -> Repo:
        """
        Pobiera instancję Repo dla workspace.

        Returns:
            Obiekt Repo

        Raises:
            InvalidGitRepositoryError: Jeśli workspace nie jest repozytorium Git
        """
        try:
            return Repo(self.workspace_root)
        except InvalidGitRepositoryError:
            raise InvalidGitRepositoryError(
                f"Workspace '{self.workspace_root}' nie jest repozytorium Git. "
                f"Użyj init_repo() aby je zainicjalizować."
            )

    @kernel_function(
        name="init_repo",
        description="Inicjalizuje nowe repozytorium Git w workspace lub klonuje istniejące.",
    )
    async def init_repo(
        self,
        url: Annotated[
            Optional[str], "URL repozytorium do sklonowania (opcjonalne)"
        ] = None,
    ) -> str:
        """
        Inicjalizuje lub klonuje repozytorium Git.

        Args:
            url: URL repozytorium do sklonowania (jeśli None, inicjalizuje puste repo)

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            if url:
                # Klonuj repozytorium
                logger.info(f"Klonowanie repozytorium z {url}")
                # Usuń workspace jeśli istnieje
                if self.workspace_root.exists():
                    import shutil

                    shutil.rmtree(self.workspace_root)
                Repo.clone_from(url, self.workspace_root)
                return f"✅ Sklonowano repozytorium z {url} do {self.workspace_root}"
            else:
                # Inicjalizuj nowe repozytorium
                logger.info(
                    f"Inicjalizacja nowego repozytorium w {self.workspace_root}"
                )
                Repo.init(self.workspace_root)
                return (
                    f"✅ Zainicjalizowano nowe repozytorium Git w {self.workspace_root}"
                )

        except Exception as e:
            error_msg = f"❌ Błąd podczas inicjalizacji repozytorium: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="checkout",
        description="Przełącza branch w repozytorium Git.",
    )
    async def checkout(
        self,
        branch_name: Annotated[str, "Nazwa brancha do przełączenia"],
        create_new: Annotated[
            bool, "Czy utworzyć nowy branch (True) czy przełączyć na istniejący (False)"
        ] = False,
    ) -> str:
        """
        Przełącza branch Git.

        Args:
            branch_name: Nazwa brancha
            create_new: Czy utworzyć nowy branch

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            repo = self._get_repo()

            if create_new:
                # Utwórz i przełącz na nowy branch
                logger.info(f"Tworzenie nowego brancha: {branch_name}")
                new_branch = repo.create_head(branch_name)
                new_branch.checkout()
                return f"✅ Utworzono i przełączono na nowy branch: {branch_name}"
            else:
                # Przełącz na istniejący branch
                logger.info(f"Przełączanie na branch: {branch_name}")
                repo.git.checkout(branch_name)
                return f"✅ Przełączono na branch: {branch_name}"

        except GitCommandError as e:
            error_msg = f"❌ Błąd Git podczas checkout: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Błąd podczas checkout: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="get_status",
        description="Zwraca status repozytorium Git (zmodyfikowane, dodane, usunięte pliki).",
    )
    async def get_status(self) -> str:
        """
        Pobiera status repozytorium Git.

        Returns:
            Status repozytorium jako string
        """
        try:
            repo = self._get_repo()
            status = repo.git.status()
            logger.debug(f"Status repozytorium: {status}")
            return status

        except Exception as e:
            error_msg = f"❌ Błąd podczas pobierania statusu: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="get_diff",
        description="Zwraca różnice (diff) między workspace a ostatnim commitem.",
    )
    async def get_diff(self) -> str:
        """
        Pobiera diff repozytorium Git.

        Returns:
            Diff jako string
        """
        try:
            repo = self._get_repo()
            # Pobierz diff dla staged i unstaged changes
            diff = repo.git.diff("HEAD")
            if not diff:
                # Jeśli brak zmian w HEAD, sprawdź unstaged
                diff = repo.git.diff()
            logger.debug(f"Diff repozytorium: {len(diff)} znaków")
            return diff if diff else "Brak zmian do wyświetlenia."

        except Exception as e:
            error_msg = f"❌ Błąd podczas pobierania diff: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="add_files",
        description="Stage'uje pliki do commita (git add).",
    )
    async def add_files(
        self,
        files: Annotated[
            List[str], "Lista plików do stage'owania (użyj ['.'] dla wszystkich)"
        ] = None,
    ) -> str:
        """
        Stage'uje pliki do commita.

        Args:
            files: Lista plików do dodania (domyślnie wszystkie zmiany)

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            repo = self._get_repo()
            if files is None or files == ["."] or "." in files:
                # Dodaj wszystkie zmiany
                repo.git.add(A=True)
                logger.info("Stage'owano wszystkie zmiany")
                return "✅ Stage'owano wszystkie zmiany (git add .)"
            else:
                # Dodaj konkretne pliki
                repo.index.add(files)
                logger.info(f"Stage'owano pliki: {files}")
                return f"✅ Stage'owano pliki: {', '.join(files)}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas stage'owania plików: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="commit",
        description="Tworzy commit Git z podaną wiadomością.",
    )
    async def commit(
        self,
        message: Annotated[
            str, "Wiadomość commita (najlepiej w formacie Conventional Commits)"
        ],
    ) -> str:
        """
        Tworzy commit Git.

        Args:
            message: Wiadomość commita

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            repo = self._get_repo()

            # Sprawdź czy są zmiany do commitowania
            if not repo.is_dirty(untracked_files=True):
                return "⚠️ Brak zmian do commitowania"

            # Utwórz commit
            commit = repo.index.commit(message)
            logger.info(f"Utworzono commit: {commit.hexsha[:7]} - {message}")
            return f"✅ Commit utworzony: {commit.hexsha[:7]} - {message}"

        except Exception as e:
            error_msg = f"❌ Błąd podczas tworzenia commita: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="push",
        description="Wypycha zmiany do zdalnego repozytorium.",
    )
    async def push(
        self,
        remote: Annotated[str, "Nazwa remote (domyślnie 'origin')"] = "origin",
        branch: Annotated[
            Optional[str], "Nazwa brancha (domyślnie aktualny branch)"
        ] = None,
    ) -> str:
        """
        Wypycha zmiany do remote.

        Args:
            remote: Nazwa remote
            branch: Nazwa brancha (jeśli None, używa aktualnego)

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            repo = self._get_repo()

            # Pobierz aktualny branch jeśli nie podano
            if branch is None:
                branch = repo.active_branch.name

            # BEZPIECZEŃSTWO: Sprawdź czy nie próbuje się użyć --force
            # To zabezpieczenie przed przypadkowym nadpisaniem historii
            logger.info(f"Wypychanie brancha {branch} do {remote}")

            # Wypchnij zmiany
            origin = repo.remote(name=remote)
            origin.push(branch)

            logger.info(f"Wypchano zmiany do {remote}/{branch}")
            return f"✅ Wypchano zmiany do {remote}/{branch}"

        except GitCommandError as e:
            error_msg = f"❌ Błąd Git podczas push: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Błąd podczas push: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="get_last_commit_log",
        description="Zwraca historię ostatnich commitów.",
    )
    async def get_last_commit_log(
        self,
        n: Annotated[int, "Liczba ostatnich commitów do wyświetlenia"] = 5,
    ) -> str:
        """
        Pobiera historię ostatnich commitów.

        Args:
            n: Liczba commitów do pobrania

        Returns:
            Historia commitów jako string
        """
        try:
            repo = self._get_repo()
            commits = list(repo.iter_commits(max_count=n))

            if not commits:
                return "Brak commitów w repozytorium."

            log_lines = []
            for commit in commits:
                log_lines.append(
                    f"{commit.hexsha[:7]} - {commit.author.name} - {commit.committed_datetime.strftime('%Y-%m-%d %H:%M')} - {commit.message.strip()}"
                )

            log = "\n".join(log_lines)
            logger.debug(f"Historia commitów (ostatnie {n}): {len(log)} znaków")
            return log

        except Exception as e:
            error_msg = f"❌ Błąd podczas pobierania historii: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="get_current_branch",
        description="Zwraca nazwę aktualnego brancha.",
    )
    async def get_current_branch(self) -> str:
        """
        Pobiera nazwę aktualnego brancha.

        Returns:
            Nazwa aktualnego brancha
        """
        try:
            repo = self._get_repo()
            branch = repo.active_branch.name
            logger.debug(f"Aktualny branch: {branch}")
            return branch

        except Exception as e:
            error_msg = f"❌ Błąd podczas pobierania brancha: {str(e)}"
            logger.error(error_msg)
            return error_msg
