"""Moduł: watcher - Obserwator systemu plików dla automatycznej reakcji na zmiany."""

import asyncio
import time
from pathlib import Path
from typing import Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from venom_core.api.stream import EventType
from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class VenomFileSystemEventHandler(FileSystemEventHandler):
    """
    Handler zdarzeń systemu plików.
    Implementuje debouncing aby uniknąć wielokrotnego triggerowania na tej samej zmianie.
    """

    def __init__(
        self, callback, debounce_seconds: int = 5, ignored_patterns: Set[str] = None
    ):
        """
        Inicjalizacja handlera.

        Args:
            callback: Async funkcja callback do wywołania przy zmianie
            debounce_seconds: Czas debounce w sekundach
            ignored_patterns: Wzorce ścieżek do ignorowania
        """
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.ignored_patterns = ignored_patterns or {
            ".git",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "node_modules",
            ".venv",
            "venv",
            ".idea",
            ".vscode",
            "*.pyc",
            "*.pyo",
            "*.swp",
            "*.tmp",
        }

        # Debouncing: ścieżka -> timestamp ostatniej zmiany
        self._pending_changes: dict[str, float] = {}
        self._debounce_task: Optional[asyncio.Task] = None
        self._loop = None

    def _should_ignore(self, path: str) -> bool:
        """
        Sprawdza czy ścieżka powinna być ignorowana.

        Args:
            path: Ścieżka do sprawdzenia

        Returns:
            True jeśli ścieżka powinna być ignorowana
        """
        path_obj = Path(path)

        # Sprawdź każdy pattern
        for pattern in self.ignored_patterns:
            # Pattern z gwiazdką (np. *.pyc)
            if "*" in pattern:
                if path_obj.match(pattern):
                    return True
            # Zwykły pattern (katalog lub nazwa)
            else:
                if pattern in path_obj.parts or pattern in str(path_obj):
                    return True

        return False

    def on_modified(self, event: FileSystemEvent) -> None:
        """
        Callback wywoływany gdy plik jest modyfikowany.

        Args:
            event: Zdarzenie systemu plików
        """
        if event.is_directory:
            return

        # Ignoruj pliki niebędące Pythonem lub markdown
        if not (event.src_path.endswith(".py") or event.src_path.endswith(".md")):
            return

        # Sprawdź czy ścieżka powinna być ignorowana
        if self._should_ignore(event.src_path):
            logger.debug(f"Ignorowanie zmiany w: {event.src_path}")
            return

        # Dodaj do pending changes z aktualnym timestampem
        self._pending_changes[event.src_path] = time.time()

        # Uruchom debounce task jeśli nie działa
        if self._debounce_task is None or self._debounce_task.done():
            if self._loop is None:
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    # Brak running loop - utwórz nowy task w głównym loop
                    self._loop = asyncio.get_event_loop()

            self._debounce_task = self._loop.create_task(self._debounce_handler())

    async def _debounce_handler(self) -> None:
        """Async handler dla debouncing."""
        await asyncio.sleep(self.debounce_seconds)

        # Przetwórz wszystkie pending changes
        if self._pending_changes:
            changes = list(self._pending_changes.keys())
            self._pending_changes.clear()

            logger.info(f"Wykryto {len(changes)} zmian plików po debounce")

            # Wywołaj callback dla każdej zmiany
            for file_path in changes:
                try:
                    await self.callback(file_path)
                except Exception as e:
                    logger.error(f"Błąd w callback dla {file_path}: {e}")


class FileWatcher:
    """
    Obserwator systemu plików monitorujący zmiany w workspace.
    """

    def __init__(
        self,
        workspace_root: str = None,
        on_change_callback=None,
        event_broadcaster=None,
    ):
        """
        Inicjalizacja watchera.

        Args:
            workspace_root: Katalog do monitorowania
            on_change_callback: Async callback wywoływany przy zmianie pliku
            event_broadcaster: Broadcaster zdarzeń do WebSocket
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.on_change_callback = on_change_callback
        self.event_broadcaster = event_broadcaster

        self.observer: Optional[Observer] = None
        self.is_running = False

        # Utwórz event handler z debouncing
        self.event_handler = VenomFileSystemEventHandler(
            callback=self._handle_file_change,
            debounce_seconds=SETTINGS.WATCHER_DEBOUNCE_SECONDS,
        )

        logger.info(f"FileWatcher zainicjalizowany dla: {self.workspace_root}")

    async def start(self) -> None:
        """Uruchamia obserwatora."""
        if self.is_running:
            logger.warning("FileWatcher już działa")
            return

        if not self.workspace_root.exists():
            logger.warning(
                f"Katalog workspace nie istnieje: {self.workspace_root}, tworzę..."
            )
            self.workspace_root.mkdir(parents=True, exist_ok=True)

        try:
            # Utwórz i uruchom observer
            self.observer = Observer()
            self.observer.schedule(
                self.event_handler, str(self.workspace_root), recursive=True
            )
            self.observer.start()
            self.is_running = True

            logger.info(f"FileWatcher uruchomiony, monitoruje: {self.workspace_root}")

            if self.event_broadcaster:
                await self.event_broadcaster.broadcast_event(
                    event_type=EventType.SYSTEM_LOG,
                    message=f"File Watcher started monitoring {self.workspace_root}",
                    data={"level": "INFO"},
                )

        except Exception as e:
            logger.error(f"Błąd podczas uruchamiania FileWatcher: {e}")
            raise

    async def stop(self) -> None:
        """Zatrzymuje obserwatora."""
        if not self.is_running:
            logger.warning("FileWatcher nie działa")
            return

        try:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=5)

            self.is_running = False
            logger.info("FileWatcher zatrzymany")

            if self.event_broadcaster:
                await self.event_broadcaster.broadcast_event(
                    event_type=EventType.SYSTEM_LOG,
                    message="File Watcher stopped",
                    data={"level": "INFO"},
                )

        except Exception as e:
            logger.error(f"Błąd podczas zatrzymywania FileWatcher: {e}")
            raise

    async def _handle_file_change(self, file_path: str) -> None:
        """
        Obsługuje zmianę pliku.

        Args:
            file_path: Ścieżka do zmienionego pliku
        """
        logger.info(f"Wykryto zmianę w pliku: {file_path}")

        # Broadcast zdarzenia CODE_CHANGED
        if self.event_broadcaster:
            await self.event_broadcaster.broadcast_event(
                event_type=EventType.CODE_CHANGED,
                message=f"File changed: {Path(file_path).name}",
                data={
                    "file_path": file_path,
                    "relative_path": str(
                        Path(file_path).relative_to(self.workspace_root)
                    ),
                    "timestamp": time.time(),
                },
            )

        # Wywołaj user callback jeśli jest zdefiniowany
        if self.on_change_callback:
            try:
                await self.on_change_callback(file_path)
            except Exception as e:
                logger.error(f"Błąd w callback użytkownika dla {file_path}: {e}")

    def get_status(self) -> dict:
        """
        Zwraca status watchera.

        Returns:
            Słownik ze statusem
        """
        return {
            "is_running": self.is_running,
            "workspace_root": str(self.workspace_root),
            "debounce_seconds": SETTINGS.WATCHER_DEBOUNCE_SECONDS,
            "monitoring_extensions": [".py", ".md"],
        }
