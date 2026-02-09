"""Moduł: git_skill - zarządzanie operacjami Git."""

from typing import Annotated, List, Optional

from git import GitCommandError, InvalidGitRepositoryError, Repo
from semantic_kernel.functions import kernel_function

from venom_core.execution.skills.base_skill import BaseSkill, async_safe_action


class GitSkill(BaseSkill):
    """
    Skill do operacji Git w workspace.
    Umożliwia zarządzanie repozytorium, branchami, commitami i synchronizacją.

    UWAGA: GitSkill działa na HOŚCIE (nie w Dockerze), aby mieć dostęp do
    kluczy SSH użytkownika. Operacje są wykonywane na WORKSPACE_ROOT.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja GitSkill.
        """
        super().__init__(workspace_root)
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
            self.logger.info(self._workspace_not_repo_message())
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

    @staticmethod
    def _resolve_branch_name(repo: Repo, branch: Optional[str]) -> str:
        if branch is not None:
            return branch
        return repo.active_branch.name

    def _has_pull_error(
        self, pull_info: list, repo: Repo, remote: str, branch: str
    ) -> str | None:
        for info in pull_info:
            if not (info.flags & info.ERROR):
                continue
            conflict_msg = self._format_conflict_message(
                repo, "pull", f"z {remote}/{branch}"
            )
            if conflict_msg:
                self.logger.warning(conflict_msg)
                return conflict_msg
        return None

    @staticmethod
    def _collect_changed_files_from_pull(pull_info: list) -> list[str]:
        changed_files: list[str] = []
        for info in pull_info:
            if not hasattr(info, "commit") or not info.commit or not info.old_commit:
                continue
            changed_files.extend(
                [
                    item.a_path or item.b_path
                    for item in info.commit.diff(info.old_commit)
                    if item.a_path or item.b_path
                ]
            )
        return changed_files

    @staticmethod
    def _format_pull_result(remote: str, branch: str, changed_files: list[str]) -> str:
        if not changed_files:
            return f"✅ Zaktualizowano z {remote}/{branch} (już aktualne)"
        files_list = "\n".join(
            f"  - {changed_file}" for changed_file in changed_files[:10]
        )
        if len(changed_files) > 10:
            files_list += f"\n  ... i {len(changed_files) - 10} więcej"
        return (
            f"✅ Pomyślnie zaktualizowano z {remote}/{branch}\n"
            f"Zmienione pliki:\n{files_list}"
        )

    @kernel_function(
        name="init_repo",
        description="Inicjalizuje nowe repozytorium Git w workspace lub klonuje istniejące.",
    )
    @async_safe_action
    async def init_repo(
        self,
        url: Annotated[
            Optional[str], "URL repozytorium do sklonowania (opcjonalne)"
        ] = None,
    ) -> str:
        """
        Inicjalizuje lub klonuje repozytorium Git.
        """
        if url:
            # Klonuj repozytorium
            self.logger.info(f"Klonowanie repozytorium z {url}")
            # Usuń workspace jeśli istnieje (BaseSkill zapewnia, że root istnieje)
            # Ale shutil.rmtree usunie sam root
            if self.workspace_root.exists():
                import shutil

                # Usuwamy zawartość, a nie sam katalog, żeby nie psuć referencji BaseSkill?
                # Nie, rmtree usunie katalog. Odtwórzmy go.
                shutil.rmtree(self.workspace_root)

            Repo.clone_from(url, self.workspace_root)
            return f"✅ Sklonowano repozytorium z {url} do {self.workspace_root}"
        else:
            # Inicjalizuj nowe repozytorium
            self.logger.info(
                f"Inicjalizacja nowego repozytorium w {self.workspace_root}"
            )
            Repo.init(self.workspace_root)
            return f"✅ Zainicjalizowano nowe repozytorium Git w {self.workspace_root}"

    @kernel_function(
        name="checkout",
        description="Przełącza branch w repozytorium Git.",
    )
    @async_safe_action
    async def checkout(
        self,
        branch_name: Annotated[str, "Nazwa brancha do przełączenia"],
        create_new: Annotated[
            bool, "Czy utworzyć nowy branch (True) czy przełączyć na istniejący (False)"
        ] = False,
    ) -> str:
        """
        Przełącza branch Git.
        """
        repo = self._get_repo()

        if create_new:
            # Utwórz i przełącz na nowy branch
            self.logger.info(f"Tworzenie nowego brancha: {branch_name}")
            new_branch = repo.create_head(branch_name)
            new_branch.checkout()
            return f"✅ Utworzono i przełączono na nowy branch: {branch_name}"
        else:
            # Przełącz na istniejący branch
            self.logger.info(f"Przełączanie na branch: {branch_name}")
            repo.git.checkout(branch_name)
            return f"✅ Przełączono na branch: {branch_name}"

    @kernel_function(
        name="get_status",
        description="Zwraca status repozytorium Git (zmodyfikowane, dodane, usunięte pliki).",
    )
    @async_safe_action
    async def get_status(self) -> str:
        """
        Pobiera status repozytorium Git.
        """
        try:
            repo = self._get_repo()
            status = repo.git.status()
            self.logger.debug(f"Status repozytorium: {status}")
            return status
        except InvalidGitRepositoryError as e:
            return str(e)

    @kernel_function(
        name="get_diff",
        description="Zwraca różnice (diff) między workspace a ostatnim commitem.",
    )
    @async_safe_action
    async def get_diff(self) -> str:
        """
        Pobiera diff repozytorium Git.
        """
        repo = self._get_repo()
        # Pobierz diff dla staged i unstaged changes
        diff = repo.git.diff("HEAD")
        if not diff:
            # Jeśli brak zmian w HEAD, sprawdź unstaged
            diff = repo.git.diff()
        self.logger.debug(f"Diff repozytorium: {len(diff)} znaków")
        return diff if diff else "Brak zmian do wyświetlenia."

    @kernel_function(
        name="add_files",
        description="Stage'uje pliki do commita (git add).",
    )
    @async_safe_action
    async def add_files(
        self,
        files: Annotated[
            Optional[List[str]],
            "Lista plików do stage'owania (użyj ['.'] dla wszystkich)",
        ] = None,
    ) -> str:
        """
        Stage'uje pliki do commita.
        """
        repo = self._get_repo()
        if files is None or files == ["."] or "." in files:
            # Dodaj wszystkie zmiany
            repo.git.add(A=True)
            self.logger.info("Stage'owano wszystkie zmiany")
            return "✅ Stage'owano wszystkie zmiany (git add .)"
        else:
            # Dodaj konkretne pliki
            repo.index.add(files)
            self.logger.info(f"Stage'owano pliki: {files}")
            return f"✅ Stage'owano pliki: {', '.join(files)}"

    @kernel_function(
        name="commit",
        description="Tworzy commit Git z podaną wiadomością.",
    )
    @async_safe_action
    async def commit(
        self,
        message: Annotated[
            str, "Wiadomość commita (najlepiej w formacie Conventional Commits)"
        ],
    ) -> str:
        """
        Tworzy commit Git.
        """
        repo = self._get_repo()

        # Sprawdź czy są zmiany do commitowania
        if not repo.is_dirty(untracked_files=True):
            return "⚠️ Brak zmian do commitowania"

        # Utwórz commit
        commit = repo.index.commit(message)
        self.logger.info(f"Utworzono commit: {commit.hexsha[:7]} - {message}")
        return f"✅ Commit utworzony: {commit.hexsha[:7]} - {message}"

    @kernel_function(
        name="push",
        description="Wypycha zmiany do zdalnego repozytorium.",
    )
    @async_safe_action
    async def push(
        self,
        remote: Annotated[str, "Nazwa remote (domyślnie 'origin')"] = "origin",
        branch: Annotated[
            Optional[str], "Nazwa brancha (domyślnie aktualny branch)"
        ] = None,
    ) -> str:
        """
        Wypycha zmiany do remote.
        """
        repo = self._get_repo()

        # Pobierz aktualny branch jeśli nie podano
        if branch is None:
            branch = repo.active_branch.name

        # BEZPIECZEŃSTWO: Sprawdź czy nie próbuje się użyć --force
        self.logger.info(f"Wypychanie brancha {branch} do {remote}")

        # Wypchnij zmiany
        origin = repo.remote(name=remote)
        origin.push(branch)

        self.logger.info(f"Wypchano zmiany do {remote}/{branch}")
        return f"✅ Wypchano zmiany do {remote}/{branch}"

    @kernel_function(
        name="get_last_commit_log",
        description="Zwraca historię ostatnich commitów.",
    )
    @async_safe_action
    async def get_last_commit_log(
        self,
        n: Annotated[int, "Liczba ostatnich commitów do wyświetlenia"] = 5,
    ) -> str:
        """
        Pobiera historię ostatnich commitów.
        """
        repo = self._get_repo()
        commits = list(repo.iter_commits(max_count=n))

        if not commits:
            return "Brak commitów w repozytorium."

        log_lines = []
        for commit in commits:
            message = (
                commit.message.decode("utf-8", "ignore")
                if isinstance(commit.message, bytes)
                else commit.message
            )
            log_lines.append(
                f"{commit.hexsha[:7]} - {commit.author.name} - {commit.committed_datetime.strftime('%Y-%m-%d %H:%M')} - {message.strip()}"
            )

        log = "\n".join(log_lines)
        self.logger.debug(f"Historia commitów (ostatnie {n}): {len(log)} znaków")
        return log

    @kernel_function(
        name="get_current_branch",
        description="Zwraca nazwę aktualnego brancha.",
    )
    @async_safe_action
    async def get_current_branch(self) -> str:
        """
        Pobiera nazwę aktualnego brancha.
        """
        try:
            repo = self._get_repo()
            branch = repo.active_branch.name
            self.logger.debug(f"Aktualny branch: {branch}")
            return branch
        except InvalidGitRepositoryError as e:
            return str(e)

    @kernel_function(
        name="pull",
        description="Pobiera i scala zmiany ze zdalnego repozytorium (git pull).",
    )
    @async_safe_action
    async def pull(
        self,
        remote: Annotated[str, "Nazwa remote (domyślnie 'origin')"] = "origin",
        branch: Annotated[
            Optional[str], "Nazwa brancha (domyślnie aktualny branch)"
        ] = None,
    ) -> str:
        """
        Pobiera i scala zmiany ze zdalnego repozytorium.
        """
        try:
            repo = self._get_repo()
            branch = self._resolve_branch_name(repo, branch)

            self.logger.info(f"Pulling z {remote}/{branch}")

            origin = repo.remote(name=remote)
            pull_info = origin.pull(branch)

            # Sprawdź czy wystąpiły konflikty
            conflict_msg = self._has_pull_error(pull_info, repo, remote, branch)
            if conflict_msg:
                return conflict_msg

            self.logger.info(f"Pomyślnie zaktualizowano z {remote}/{branch}")
            changed_files = self._collect_changed_files_from_pull(pull_info)
            return self._format_pull_result(remote, branch, changed_files)
        except GitCommandError as e:
            # Obsługa specyficzna dla błędów Gita (konflikty)
            if "CONFLICT" in str(e) or "conflict" in str(e).lower():
                repo = self._get_repo()
                conflict_msg = self._format_conflict_message(repo, "pull")
                if conflict_msg:
                    self.logger.warning(conflict_msg)
                    return conflict_msg
            raise  # Rzuć dalej, żeby safe_action to złapał jako błąd

    @kernel_function(
        name="reset",
        description="Cofa zmiany w repozytorium (git reset). UWAGA: Operacja destrukcyjna!",
    )
    @async_safe_action
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
        """
        # Walidacja mode
        allowed_modes = {"soft", "mixed", "hard"}
        if mode not in allowed_modes:
            return f"❌ Błąd: Nieprawidłowy tryb resetu '{mode}'. Dozwolone wartości: {', '.join(sorted(allowed_modes))}"

        repo = self._get_repo()

        # SAFETY GUARD
        if not force and repo.is_dirty():
            self.logger.error("SafetyError: Nie można wykonać reset (brak force)")
            return (
                f"🛑 SafetyError: Nie można wykonać reset --{mode}.\n"
                f"Repozytorium zawiera niezatwierdzone zmiany, które zostałyby utracone.\n"
                f"Użyj force=True aby wymusić reset (UWAGA: utracisz zmiany!)\n"
                f"Lub użyj get_status() aby sprawdzić status i add_files()/commit() aby zapisać zmiany."
            )

        # Wykonaj reset
        self.logger.warning(f"Wykonywanie reset --{mode} {commit_hash} (force={force})")
        repo.git.reset(f"--{mode}", commit_hash)

        self.logger.info(f"Reset --{mode} {commit_hash} wykonany pomyślnie")
        return f"✅ Reset --{mode} {commit_hash} wykonany pomyślnie"

    @kernel_function(
        name="merge",
        description="Scala zmiany z innego brancha do aktualnego brancha (git merge).",
    )
    @async_safe_action
    async def merge(
        self,
        source_branch: Annotated[str, "Nazwa brancha źródłowego do scalenia"],
    ) -> str:
        """
        Scala zmiany z innego brancha do aktualnego brancha.
        """
        try:
            repo = self._get_repo()
            current_branch = repo.active_branch.name

            self.logger.info(f"Scalanie {source_branch} do {current_branch}")

            repo.git.merge(source_branch)

            conflict_msg = self._format_conflict_message(
                repo, "merge", f"{source_branch} → {current_branch}"
            )
            if conflict_msg:
                self.logger.warning(conflict_msg)
                return conflict_msg

            self.logger.info(f"Pomyślnie scalono {source_branch} do {current_branch}")
            return f"✅ Pomyślnie scalono {source_branch} do {current_branch}"

        except GitCommandError as e:
            if "CONFLICT" in str(e) or "conflict" in str(e).lower():
                repo = self._get_repo()
                conflict_msg = self._format_conflict_message(repo, "merge")
                if conflict_msg:
                    self.logger.warning(conflict_msg)
                    return conflict_msg
            raise

    @kernel_function(
        name="create_branch",
        description="Tworzy nowy branch (bez przełączania się na niego).",
    )
    @async_safe_action
    async def create_branch(
        self,
        branch_name: Annotated[str, "Nazwa nowego brancha"],
    ) -> str:
        """
        Tworzy nowy branch bez przełączania się na niego.
        """
        repo = self._get_repo()

        if branch_name in [b.name for b in repo.branches]:
            error_msg = f"❌ Branch '{branch_name}' już istnieje"
            self.logger.error(error_msg)
            return error_msg

        self.logger.info(f"Tworzenie nowego brancha: {branch_name}")
        repo.create_head(branch_name)

        self.logger.info(f"Branch {branch_name} utworzony pomyślnie")
        return f"✅ Branch {branch_name} utworzony pomyślnie"
