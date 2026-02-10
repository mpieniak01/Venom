"""Moduł: documenter - Agent Dokumentalista dla automatycznej aktualizacji dokumentacji."""

import asyncio
from pathlib import Path
from typing import Any, Optional

from venom_core.api.stream import EventType
from venom_core.config import SETTINGS
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.git_skill import GitSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class DocumenterAgent:
    """
    Agent Dokumentalista - automatycznie aktualizuje dokumentację przy zmianie kodu.

    UWAGA: Ten agent nie dziedziczy po BaseAgent, bo jest background service
    reagującym na zdarzenia, nie conversational agent.
    """

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        git_skill: Optional[GitSkill] = None,
        file_skill: Optional[FileSkill] = None,
        event_broadcaster: Optional[Any] = None,
    ):
        """
        Inicjalizacja DocumenterAgent.

        Args:
            workspace_root: Katalog workspace
            git_skill: Instancja GitSkill (opcjonalna)
            file_skill: Instancja FileSkill (opcjonalna)
            event_broadcaster: Broadcaster zdarzeń do WebSocket
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.git_skill = git_skill or GitSkill(workspace_root=str(self.workspace_root))
        self.file_skill = file_skill or FileSkill(
            workspace_root=str(self.workspace_root)
        )
        self.event_broadcaster = event_broadcaster

        # Tracking: ostatnie zmiany aby uniknąć pętli
        self._last_processed_files: set[str] = set()
        self._processing_lock = asyncio.Lock()
        self._changelog_lock = asyncio.Lock()  # Lock dla operacji na changelog
        self._background_tasks: set[asyncio.Task[Any]] = set()

        logger.info(f"DocumenterAgent zainicjalizowany dla: {self.workspace_root}")

    async def handle_code_change(self, file_path: str) -> None:
        """
        Obsługuje zmianę pliku kodu.

        Args:
            file_path: Ścieżka do zmienionego pliku
        """
        # Sprawdź czy plik był już przetwarzany (unikanie pętli)
        async with self._processing_lock:
            if file_path in self._last_processed_files:
                logger.debug(f"Plik {file_path} już przetwarzany, pomijam")
                return

            self._last_processed_files.add(file_path)

        try:
            await self._process_file_change(file_path)
        finally:
            # Odłożone czyszczenie tracking (unikanie resource leak przy cancel)
            cleanup_task = asyncio.create_task(self._cleanup_tracking(file_path))
            self._background_tasks.add(cleanup_task)
            cleanup_task.add_done_callback(self._background_tasks.discard)

    async def _cleanup_tracking(self, file_path: str) -> None:
        """
        Usuwa plik z tracking po 60 sekundach.

        Args:
            file_path: Ścieżka do pliku
        """
        try:
            await asyncio.sleep(60)
            async with self._processing_lock:
                self._last_processed_files.discard(file_path)
        except asyncio.CancelledError:
            # Jeśli task został anulowany, usuń od razu
            async with self._processing_lock:
                self._last_processed_files.discard(file_path)
            raise

    async def _process_file_change(self, file_path: str) -> None:
        """
        Przetwarza zmianę pliku.

        Args:
            file_path: Ścieżka do zmienionego pliku
        """
        if not SETTINGS.ENABLE_AUTO_DOCUMENTATION:
            logger.debug("Auto-documentation wyłączona, pomijam")
            return

        file_path_obj = Path(file_path)

        if not self._is_python_file(file_path_obj):
            logger.debug(f"Plik {file_path} nie jest plikiem Python, pomijam")
            return

        if self._is_bot_commit_author():
            logger.debug("Zmiana dokonana przez venom-bot, pomijam")
            return

        logger.info(f"Przetwarzam zmianę w {file_path}")
        await self._broadcast_if_available(
            event_type=EventType.BACKGROUND_JOB_STARTED,
            message=f"Updating documentation for {file_path_obj.name}",
            data={"file_path": file_path, "agent": "documenter"},
        )

        try:
            diff = await self._get_file_diff(file_path)
            if not diff or "diff --git" not in diff:
                logger.debug(f"Brak zmian w git dla {file_path}")
                return

            needs_update = self._analyze_changes(diff)
            if needs_update:
                await self._apply_documentation_update(
                    file_path, file_path_obj.name, diff
                )
            await self._broadcast_if_available(
                event_type=EventType.BACKGROUND_JOB_COMPLETED,
                message=f"Documentation check completed for {file_path_obj.name}",
                data={"file_path": file_path, "updated": needs_update},
            )

        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji dokumentacji dla {file_path}: {e}")
            await self._broadcast_if_available(
                event_type=EventType.BACKGROUND_JOB_FAILED,
                message=f"Documentation update failed for {file_path_obj.name}: {e}",
                data={"file_path": file_path, "error": str(e)},
            )

    def _is_python_file(self, file_path_obj: Path) -> bool:
        return file_path_obj.suffix == ".py"

    def _is_bot_commit_author(self) -> bool:
        try:
            last_commit_author = self._get_last_commit_author()
            if not last_commit_author:
                return False
            author_lower = last_commit_author.lower()
            return "venom-bot" in author_lower or (
                "venom" in author_lower and "bot" in author_lower
            )
        except Exception as e:
            logger.debug(f"Błąd podczas sprawdzania autora: {e}")
            logger.debug(f"Nie można sprawdzić autora commita: {e}")
            return False

    async def _broadcast_if_available(
        self, event_type: str, message: str, data: dict[str, Any]
    ) -> None:
        if not self.event_broadcaster:
            return
        await self.event_broadcaster.broadcast_event(
            event_type=event_type, message=message, data=data
        )

    async def _apply_documentation_update(
        self, file_path: str, file_name: str, diff: str
    ) -> None:
        await self._update_documentation(file_path, diff)
        await self._commit_documentation_changes(file_name)
        await self._broadcast_if_available(
            event_type=EventType.DOCUMENTATION_UPDATED,
            message=f"Documentation updated for {file_name}",
            data={"file_path": file_path},
        )
        logger.info(f"Dokumentacja zaktualizowana dla {file_path}")

    async def _get_file_diff(self, file_path: str) -> str:
        """
        Pobiera diff dla pliku.

        Args:
            file_path: Ścieżka do pliku

        Returns:
            Diff jako string
        """
        try:
            # Użyj GitSkill do pobrania diffa
            try:
                relative_path = str(
                    Path(file_path).resolve().relative_to(self.workspace_root)
                )
            except ValueError:
                logger.warning(
                    f"Plik {file_path} nie znajduje się w workspace {self.workspace_root}, pomijam diff."
                )
                return ""

            result = await self.git_skill.get_diff(file_path=relative_path)
            return result
        except Exception as e:
            logger.debug(f"Błąd podczas pobierania diff: {e}")
            return ""

    def _get_last_commit_author(self) -> Optional[str]:
        """
        Pobiera autora ostatniego commita.

        Returns:
            Autor commita lub None
        """
        try:
            from git import Repo

            repo = Repo(self.workspace_root)
            if repo.head.is_valid():
                return repo.head.commit.author.name
        except Exception as e:
            # Nie można pobrać autora - repo może nie mieć commitów lub inny błąd
            logger.debug(f"Nie można pobrać autora ostatniego commita: {e}")
        return None

    def _analyze_changes(self, diff: str) -> bool:
        """
        Analizuje czy zmiany wymagają aktualizacji dokumentacji.

        Args:
            diff: Diff zmian

        Returns:
            True jeśli potrzebna aktualizacja dokumentacji
        """
        keywords = ["def ", "class ", "async def ", '"""', "'''"]

        for line in diff.splitlines():
            if (
                (line.startswith("+") or line.startswith("-"))
                and not line.startswith("+++")
                and not line.startswith("---")
            ):
                for keyword in keywords:
                    if keyword in line:
                        logger.debug(
                            f"Wykryto zmianę wymagającą aktualizacji dokumentacji: {keyword}"
                        )
                        return True

        return False

    async def _update_documentation(self, file_path: str, diff: str) -> None:
        """
        Aktualizuje dokumentację na podstawie zmian.

        Args:
            file_path: Ścieżka do pliku
            diff: Diff zmian

        NOTE: To jest uproszczona wersja. Pełna implementacja wymagałaby
        integracji z LLM do analizy zmian i generowania dokumentacji.
        """
        # Dla tej wersji, tworzymy prosty log zmian
        docs_dir = self.workspace_root / "docs"
        docs_dir.mkdir(exist_ok=True)

        changelog_file = docs_dir / "CHANGELOG_AUTO.md"

        # Przygotuj wpis
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_name = Path(file_path).name

        entry = f"\n## {timestamp} - {file_name}\n\n"
        entry += f"Wykryto zmiany w pliku `{file_name}`.\n\n"
        entry += "```diff\n"
        entry += diff[:500] + ("..." if len(diff) > 500 else "")  # Ogranicz długość
        entry += "\n```\n"

        # Dopisz do pliku z lockiem (unikanie race condition)
        async with self._changelog_lock:
            try:
                if changelog_file.exists():
                    content = changelog_file.read_text()
                    changelog_file.write_text(entry + content)
                else:
                    changelog_file.write_text(
                        "# Automatic Changelog\n\nThis file is automatically generated by DocumenterAgent.\n"
                        + entry
                    )

                logger.info(f"Zaktualizowano {changelog_file}")

            except Exception as e:
                logger.error(f"Błąd podczas zapisu changelog: {e}")

    async def _commit_documentation_changes(self, file_name: str) -> None:
        """
        Commituje zmiany w dokumentacji.

        Args:
            file_name: Nazwa zmienionego pliku
        """
        try:
            # Dodaj wszystkie zmiany w docs/
            docs_dir = self.workspace_root / "docs"
            if docs_dir.exists():
                # Użyj GitSkill do dodania i commitu
                message = f"docs: auto-update documentation for {file_name}"

                # Najpierw dodaj pliki
                from git import Repo

                repo = Repo(self.workspace_root)

                # Dodaj tylko pliki z docs/ - batch operation
                files_to_add = [
                    str(file.relative_to(self.workspace_root))
                    for file in docs_dir.rglob("*")
                    if file.is_file()
                ]

                try:
                    if files_to_add:
                        repo.index.add(files_to_add)
                except Exception as e:
                    logger.warning(f"Błąd podczas dodawania plików do indeksu git: {e}")
                    return

                # Sprawdź czy są zmiany do commitu
                if repo.index.diff("HEAD"):
                    result = await self.git_skill.commit(message)
                    logger.info(f"Commit dokumentacji: {result}")
                else:
                    logger.debug("Brak zmian do commitu w dokumentacji")

        except Exception as e:
            logger.warning(f"Nie można commitować zmian dokumentacji: {e}")

    def get_status(self) -> dict:
        """
        Zwraca status agenta.

        Returns:
            Słownik ze statusem
        """
        return {
            "enabled": SETTINGS.ENABLE_AUTO_DOCUMENTATION,
            "workspace_root": str(self.workspace_root),
            "processing_files": len(self._last_processed_files),
        }
