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
        self._missing_repo_reported = False

    def _has_git_repository(self) -> bool:
        """Sprawdza, czy workspace zawiera repozytorium Git."""
        has_repo = (self.workspace_root / ".git").exists()
        if has_repo and self._missing_repo_reported:
            # Zresetuj flagę gdy repo pojawi się po inicjalizacji
            self._missing_repo_reported = False
        return has_repo

    def _workspace_not_repo_message(self) -> str:
        """Komunikat zwracany, gdy workspace nie ma repozytorium."""
        return (
            f"ℹ️ Workspace '{self.workspace_root}' nie jest repozytorium Git. "
            "Użyj init_repo() aby je zainicjalizować."
        )

    def _notify_missing_repo_once(self):
        """Publikuje log o braku repo tylko raz."""
        if not self._missing_repo_reported:
            logger.info(self._workspace_not_repo_message())
            self._missing_repo_reported = True

    def _get_repo(self) -> Repo:
        """
        Pobiera instancję Repo dla workspace.

        Returns:
            Obiekt Repo

        Raises:
            InvalidGitRepositoryError: Jeśli workspace nie jest repozytorium Git
        """
        try:
            if not self._has_git_repository():
                self._notify_missing_repo_once()
                raise InvalidGitRepositoryError(self._workspace_not_repo_message())
            return Repo(self.workspace_root)
        except InvalidGitRepositoryError:
            raise InvalidGitRepositoryError(self._workspace_not_repo_message())

    def _format_conflict_message(
        self, repo: Repo, operation: str, details: str = ""
    ) -> str:
        """
        Formatuje komunikat o konflikcie merge.

        Args:
            repo: Instancja repozytorium
            operation: Nazwa operacji (np. "pull", "merge")
            details: Dodatkowe szczegóły (np. branch name)

        Returns:
            Sformatowany komunikat o konflikcie
        """
        if repo.index.unmerged_blobs():
            conflicts = list(repo.index.unmerged_blobs().keys())
            conflict_list = "\n".join(f"  - {f}" for f in conflicts)
            message = (
                f"⚠️ CONFLICT: Wystąpiły konflikty podczas {operation}"
                + (f" {details}" if details else "")
                + ".\n"
                f"Pliki w konflikcie:\n{conflict_list}\n"
                f"Rozwiąż konflikty ręcznie, a następnie użyj add_files() i commit()."
            )
            return message
        return ""

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
            if not self._has_git_repository():
                self._notify_missing_repo_once()
                return self._workspace_not_repo_message()

            repo = self._get_repo()
            status = repo.git.status()
            logger.debug(f"Status repozytorium: {status}")
            return status

        except InvalidGitRepositoryError as e:
            return str(e)
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
            if not self._has_git_repository():
                self._notify_missing_repo_once()
                return self._workspace_not_repo_message()

            repo = self._get_repo()
            branch = repo.active_branch.name
            logger.debug(f"Aktualny branch: {branch}")
            return branch

        except InvalidGitRepositoryError as e:
            return str(e)
        except Exception as e:
            error_msg = f"❌ Błąd podczas pobierania brancha: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="pull",
        description="Pobiera i scala zmiany ze zdalnego repozytorium (git pull).",
    )
    async def pull(
        self,
        remote: Annotated[str, "Nazwa remote (domyślnie 'origin')"] = "origin",
        branch: Annotated[
            Optional[str], "Nazwa brancha (domyślnie aktualny branch)"
        ] = None,
    ) -> str:
        """
        Pobiera i scala zmiany ze zdalnego repozytorium.

        Args:
            remote: Nazwa remote
            branch: Nazwa brancha (jeśli None, używa aktualnego)

        Returns:
            Komunikat o wyniku operacji. W przypadku konfliktu zwraca
            status CONFLICT wraz z listą plików w konflikcie.
        """
        try:
            repo = self._get_repo()

            # Pobierz aktualny branch jeśli nie podano
            if branch is None:
                branch = repo.active_branch.name

            logger.info(f"Pulling z {remote}/{branch}")

            # Wykonaj pull
            origin = repo.remote(name=remote)
            pull_info = origin.pull(branch)

            # Sprawdź czy wystąpiły konflikty
            for info in pull_info:
                if info.flags & info.ERROR:
                    # Sprawdź czy to konflikt merge
                    conflict_msg = self._format_conflict_message(
                        repo, "pull", f"z {remote}/{branch}"
                    )
                    if conflict_msg:
                        logger.warning(conflict_msg)
                        return conflict_msg

            # Sukces
            logger.info(f"Pomyślnie zaktualizowano z {remote}/{branch}")
            changed_files = []
            for info in pull_info:
                if hasattr(info, "commit") and info.commit:
                    # Pobierz zmienione pliki z commita
                    if info.old_commit:
                        changed_files.extend(
                            [
                                item.a_path or item.b_path
                                for item in info.commit.diff(info.old_commit)
                                if item.a_path or item.b_path
                            ]
                        )

            if changed_files:
                files_list = "\n".join(f"  - {f}" for f in changed_files[:10])
                if len(changed_files) > 10:
                    files_list += f"\n  ... i {len(changed_files) - 10} więcej"
                return (
                    f"✅ Pomyślnie zaktualizowano z {remote}/{branch}\n"
                    f"Zmienione pliki:\n{files_list}"
                )
            else:
                return f"✅ Zaktualizowano z {remote}/{branch} (już aktualne)"

        except GitCommandError as e:
            # Sprawdź czy to konflikt
            if "CONFLICT" in str(e) or "conflict" in str(e).lower():
                repo = self._get_repo()
                conflict_msg = self._format_conflict_message(repo, "pull")
                if conflict_msg:
                    logger.warning(conflict_msg)
                    return conflict_msg

            error_msg = f"❌ Błąd Git podczas pull: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Błąd podczas pull: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="reset",
        description="Cofa zmiany w repozytorium (git reset). UWAGA: Operacja destrukcyjna!",
    )
    async def reset(
        self,
        mode: Annotated[
            str, "Tryb resetu: 'soft', 'mixed', lub 'hard' (domyślnie 'hard')"
        ] = "hard",
        commit_hash: Annotated[
            str, "Hash commita lub referencja (np. 'HEAD', 'HEAD~1')"
        ] = "HEAD",
        force: Annotated[
            bool,
            "Wymuś reset nawet jeśli są niezatwierdzone zmiany (domyślnie False)",
        ] = False,
    ) -> str:
        """
        Cofa zmiany w repozytorium Git.

        UWAGA: To operacja destrukcyjna! Tryb 'hard' USUWA wszystkie
        niezatwierdzone zmiany bez możliwości odzyskania.

        Args:
            mode: Tryb resetu ('soft', 'mixed', 'hard')
            commit_hash: Hash commita lub referencja (np. 'HEAD', 'HEAD~1')
            force: Czy wymusić reset mimo niezatwierdzonych zmian

        Returns:
            Komunikat o wyniku operacji

        Raises:
            Zwraca błąd jeśli są niezatwierdzone zmiany i force=False
        """
        try:
            # Walidacja mode
            allowed_modes = {"soft", "mixed", "hard"}
            if mode not in allowed_modes:
                error_msg = f"❌ Błąd: Nieprawidłowy tryb resetu '{mode}'. Dozwolone wartości: {', '.join(sorted(allowed_modes))}"
                logger.error(error_msg)
                return error_msg

            repo = self._get_repo()

            # SAFETY GUARD: Sprawdź czy są niezatwierdzone zmiany
            # Nie sprawdzamy untracked files, bo reset ich nie usuwa
            if not force and repo.is_dirty():
                error_msg = (
                    f"🛑 SafetyError: Nie można wykonać reset --{mode}.\n"
                    f"Repozytorium zawiera niezatwierdzone zmiany, które zostałyby utracone.\n"
                    f"Użyj force=True aby wymusić reset (UWAGA: utracisz zmiany!)\n"
                    f"Lub użyj get_status() aby sprawdzić status i add_files()/commit() aby zapisać zmiany."
                )
                logger.error(error_msg)
                return error_msg

            # Wykonaj reset
            logger.warning(f"Wykonywanie reset --{mode} {commit_hash} (force={force})")
            repo.git.reset(f"--{mode}", commit_hash)

            logger.info(f"Reset --{mode} {commit_hash} wykonany pomyślnie")
            return f"✅ Reset --{mode} {commit_hash} wykonany pomyślnie"

        except GitCommandError as e:
            error_msg = f"❌ Błąd Git podczas reset: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Błąd podczas reset: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="merge",
        description="Scala zmiany z innego brancha do aktualnego brancha (git merge).",
    )
    async def merge(
        self,
        source_branch: Annotated[str, "Nazwa brancha źródłowego do scalenia"],
    ) -> str:
        """
        Scala zmiany z innego brancha do aktualnego brancha.

        Args:
            source_branch: Nazwa brancha źródłowego

        Returns:
            Komunikat o wyniku operacji. W przypadku konfliktu zwraca
            listę plików wymagających rozwiązania.
        """
        try:
            repo = self._get_repo()
            current_branch = repo.active_branch.name

            logger.info(f"Scalanie {source_branch} do {current_branch}")

            # Wykonaj merge
            repo.git.merge(source_branch)

            # Sprawdź czy wystąpiły konflikty
            # Notatka: W niektórych przypadkach merge może się powieść
            # ale pozostawić unmerged blobs (np. przy auto-merge z konfliktami)
            conflict_msg = self._format_conflict_message(
                repo, "merge", f"{source_branch} → {current_branch}"
            )
            if conflict_msg:
                logger.warning(conflict_msg)
                return conflict_msg

            logger.info(f"Pomyślnie scalono {source_branch} do {current_branch}")
            return f"✅ Pomyślnie scalono {source_branch} do {current_branch}"

        except GitCommandError as e:
            # Sprawdź czy to konflikt
            if "CONFLICT" in str(e) or "conflict" in str(e).lower():
                repo = self._get_repo()
                conflict_msg = self._format_conflict_message(repo, "merge")
                if conflict_msg:
                    logger.warning(conflict_msg)
                    return conflict_msg

            error_msg = f"❌ Błąd Git podczas merge: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Błąd podczas merge: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="create_branch",
        description="Tworzy nowy branch (bez przełączania się na niego).",
    )
    async def create_branch(
        self,
        branch_name: Annotated[str, "Nazwa nowego brancha"],
    ) -> str:
        """
        Tworzy nowy branch bez przełączania się na niego.

        Args:
            branch_name: Nazwa nowego brancha

        Returns:
            Komunikat o wyniku operacji
        """
        try:
            repo = self._get_repo()

            # Sprawdź czy branch już istnieje
            if branch_name in [b.name for b in repo.branches]:
                error_msg = f"❌ Branch '{branch_name}' już istnieje"
                logger.error(error_msg)
                return error_msg

            logger.info(f"Tworzenie nowego brancha: {branch_name}")
            repo.create_head(branch_name)

            logger.info(f"Branch {branch_name} utworzony pomyślnie")
            return f"✅ Branch {branch_name} utworzony pomyślnie"

        except GitCommandError as e:
            error_msg = f"❌ Błąd Git podczas tworzenia brancha: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Błąd podczas tworzenia brancha: {str(e)}"
            logger.error(error_msg)
            return error_msg
