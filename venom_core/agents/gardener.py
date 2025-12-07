"""Moduł: gardener - Agent Ogrodnik do automatycznej re-indeksacji grafu wiedzy.

UWAGA: GardenerAgent nie dziedziczy po BaseAgent, ponieważ jest usługą działającą
w tle (background service), a nie agentem konwersacyjnym. Nie wymaga Semantic Kernel
ani metody `process()`.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from venom_core.config import SETTINGS
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class GardenerAgent:
    """
    Agent Ogrodnik (Gardener) - odpowiedzialny za utrzymanie aktualności grafu wiedzy.
    Działa w tle i monitoruje zmiany w plikach workspace.

    NOTE: Ten agent nie dziedziczy po BaseAgent, bo jest background service, nie conversational agent.
    """

    def __init__(
        self,
        graph_store: CodeGraphStore = None,
        workspace_root: str = None,
        scan_interval: int = 300,  # 5 minut
        orchestrator=None,  # Referencja do orchestratora dla idle mode
        event_broadcaster=None,  # Broadcaster zdarzeń
    ):
        """
        Inicjalizacja GardenerAgent.

        Args:
            graph_store: Instancja CodeGraphStore (domyślnie nowa)
            workspace_root: Katalog workspace (domyślnie z SETTINGS)
            scan_interval: Interwał skanowania w sekundach (domyślnie 300s = 5min)
            orchestrator: Referencja do Orchestrator dla śledzenia aktywności
            event_broadcaster: Broadcaster zdarzeń do WebSocket
        """
        self.graph_store = graph_store or CodeGraphStore(workspace_root=workspace_root)
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.scan_interval = scan_interval
        self.orchestrator = orchestrator
        self.event_broadcaster = event_broadcaster

        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._last_scan_time: Optional[datetime] = None
        self._last_file_mtimes: dict = {}
        self._last_idle_check: Optional[datetime] = None
        self._idle_refactoring_in_progress = False

        logger.info(
            f"GardenerAgent zainicjalizowany: workspace={self.workspace_root}, interval={scan_interval}s"
        )

    async def start(self) -> None:
        """Uruchamia agenta Ogrodnika w tle."""
        if self.is_running:
            logger.warning("GardenerAgent już działa")
            return

        self.is_running = True
        logger.info("Uruchamianie GardenerAgent...")

        # Wykonaj początkowe skanowanie
        await self.scan_and_update()

        # Uruchom pętlę monitorowania
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("GardenerAgent uruchomiony")

    async def stop(self) -> None:
        """Zatrzymuje agenta Ogrodnika."""
        if not self.is_running:
            logger.warning("GardenerAgent nie działa")
            return

        logger.info("Zatrzymywanie GardenerAgent...")
        self.is_running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                # Expected when cancelling task - no action needed
                pass

        logger.info("GardenerAgent zatrzymany")

    async def _monitoring_loop(self) -> None:
        """Pętla monitorowania zmian w plikach i idle mode."""
        while self.is_running:
            try:
                # Czekaj określony interwał
                await asyncio.sleep(self.scan_interval)

                # Sprawdź czy były zmiany
                if await self._check_for_changes():
                    logger.info("Wykryto zmiany w workspace, rozpoczynam re-indeksację")
                    await self.scan_and_update()
                else:
                    logger.debug("Brak zmian w workspace")

                # Sprawdź idle mode (jeśli włączony)
                if SETTINGS.ENABLE_AUTO_GARDENING and self.orchestrator:
                    await self._check_idle_mode()

            except asyncio.CancelledError:
                logger.info("Monitoring loop anulowany")
                break
            except Exception as e:
                logger.error(f"Błąd w pętli monitorowania: {e}")
                # Kontynuuj pomimo błędu
                await asyncio.sleep(10)

    async def _check_for_changes(self) -> bool:
        """
        Sprawdza czy były zmiany w plikach Python.

        Returns:
            True jeśli wykryto zmiany, False w przeciwnym razie
        """
        try:
            # Znajdź wszystkie pliki Python
            python_files = list(self.workspace_root.rglob("*.py"))

            # Sprawdź mtime każdego pliku
            current_mtimes = {}
            for file_path in python_files:
                try:
                    mtime = file_path.stat().st_mtime
                    current_mtimes[str(file_path)] = mtime
                except (OSError, PermissionError) as e:
                    # Plik mógł zostać usunięty lub brak uprawnień
                    logger.debug(f"Nie można odczytać {file_path}: {e}")
                    pass

            # Porównaj z poprzednim stanem
            if not self._last_file_mtimes:
                # Pierwsze sprawdzenie
                self._last_file_mtimes = current_mtimes
                return False

            # Sprawdź czy są różnice
            changed = (
                set(current_mtimes.keys()) != set(self._last_file_mtimes.keys())
                or current_mtimes != self._last_file_mtimes
            )

            self._last_file_mtimes = current_mtimes
            return changed

        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania zmian: {e}")
            return False

    async def scan_and_update(self, force_rescan: bool = False) -> dict:
        """
        Skanuje workspace i aktualizuje graf.

        Args:
            force_rescan: Czy wymusić pełne reskanowanie

        Returns:
            Statystyki skanowania
        """
        logger.info("Rozpoczynam skanowanie workspace...")
        start_time = datetime.now()

        try:
            # Załaduj istniejący graf jeśli nie wymuszono rescanu
            if not force_rescan:
                self.graph_store.load_graph()

            # Skanuj workspace
            stats = self.graph_store.scan_workspace(force_rescan=force_rescan)

            # Aktualizuj czas ostatniego skanu
            self._last_scan_time = datetime.now()

            duration = (self._last_scan_time - start_time).total_seconds()
            logger.info(f"Skanowanie zakończone w {duration:.2f}s: {stats}")

            return {
                **stats,
                "duration_seconds": duration,
                "timestamp": start_time.isoformat(),
            }

        except Exception as e:
            logger.error(f"Błąd podczas skanowania: {e}")
            return {"error": str(e)}

    async def trigger_manual_scan(self) -> dict:
        """
        Wyzwala manualne skanowanie (asynchroniczne).

        Returns:
            Statystyki skanowania
        """
        logger.info("Manualne skanowanie wywołane")

        try:
            # Uruchom operacje blokujące I/O w executor, aby nie blokować event loop
            import asyncio

            loop = asyncio.get_event_loop()

            # Załaduj graf w executor
            await loop.run_in_executor(None, self.graph_store.load_graph)

            # Skanuj w executor
            stats = await loop.run_in_executor(
                None, self.graph_store.scan_workspace, False
            )
            self._last_scan_time = datetime.now()

            logger.info(f"Manualne skanowanie zakończone: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Błąd podczas manualnego skanowania: {e}")
            return {"error": str(e)}

    def get_status(self) -> dict:
        """
        Zwraca status agenta.

        Returns:
            Słownik ze statusem
        """
        return {
            "is_running": self.is_running,
            "last_scan_time": (
                self._last_scan_time.isoformat() if self._last_scan_time else None
            ),
            "scan_interval_seconds": self.scan_interval,
            "workspace_root": str(self.workspace_root),
            "monitored_files": len(self._last_file_mtimes),
            "idle_refactoring_enabled": SETTINGS.ENABLE_AUTO_GARDENING,
            "idle_refactoring_in_progress": self._idle_refactoring_in_progress,
        }

    async def _check_idle_mode(self) -> None:
        """
        Sprawdza czy system jest bezczynny i uruchamia refaktoryzację jeśli tak.
        """
        if self._idle_refactoring_in_progress:
            logger.debug("Refaktoryzacja już w toku, pomijam")
            return

        # Sprawdź czas ostatniej aktywności
        if not self.orchestrator.last_activity:
            logger.debug("Brak informacji o ostatniej aktywności")
            return

        now = datetime.now()
        idle_time = (now - self.orchestrator.last_activity).total_seconds() / 60

        idle_threshold = SETTINGS.IDLE_THRESHOLD_MINUTES

        if idle_time >= idle_threshold:
            logger.info(
                f"System bezczynny przez {idle_time:.1f} minut (próg: {idle_threshold}), "
                "uruchamiam auto-refaktoryzację"
            )
            await self._run_idle_refactoring()
        else:
            logger.debug(
                f"System aktywny ({idle_time:.1f}/{idle_threshold} minut do idle)"
            )

    async def _run_idle_refactoring(self) -> None:
        """
        Uruchamia automatyczną refaktoryzację w trybie idle.
        """
        self._idle_refactoring_in_progress = True

        try:
            if self.event_broadcaster:
                from venom_core.api.stream import EventType

                await self.event_broadcaster.broadcast_event(
                    event_type=EventType.IDLE_REFACTORING_STARTED,
                    message="Starting idle refactoring",
                    data={
                        "timestamp": datetime.now().isoformat(),
                    },
                )

            logger.info("Rozpoczynam automatyczną refaktoryzację w trybie idle")

            # 1. Znajdź pliki o wysokiej złożoności
            complex_files = await self._find_complex_files()

            if not complex_files:
                logger.info("Brak plików wymagających refaktoryzacji")
                return

            # 2. Wybierz plik do refaktoryzacji (pierwszy z listy)
            target_file = complex_files[0]
            logger.info(f"Refaktoryzacja pliku: {target_file['path']}")

            # 3. Utwórz branch (jeśli Git jest dostępny)
            branch_created = await self._create_refactoring_branch()

            if branch_created:
                logger.info(
                    "Branch refactor/auto-gardening utworzony, zmiany gotowe do przeglądu"
                )

            if self.event_broadcaster:
                from venom_core.api.stream import EventType

                await self.event_broadcaster.broadcast_event(
                    event_type=EventType.IDLE_REFACTORING_COMPLETED,
                    message=f"Idle refactoring completed for {target_file['path']}",
                    data={
                        "file": target_file["path"],
                        "branch_created": branch_created,
                    },
                )

        except Exception as e:
            logger.error(f"Błąd podczas idle refactoring: {e}")
        finally:
            self._idle_refactoring_in_progress = False

    async def _find_complex_files(self) -> list[dict]:
        """
        Znajduje pliki o wysokiej złożoności cyklomatycznej.

        Returns:
            Lista plików z metrykami złożoności
        """
        try:
            from radon.visitors import ComplexityVisitor

            complex_files = []

            # Znajdź wszystkie pliki Python w workspace
            python_files = list(self.workspace_root.rglob("*.py"))

            for file_path in python_files:
                # Pomiń pliki testowe i migracje
                if "test_" in file_path.name or "/tests/" in str(file_path):
                    continue

                try:
                    content = file_path.read_text()

                    # Analizuj złożoność
                    visitor = ComplexityVisitor.from_code(content)

                    # Oblicz średnią złożoność
                    if visitor.functions:
                        avg_complexity = sum(
                            f.complexity for f in visitor.functions
                        ) / len(visitor.functions)

                        # Próg złożoności: 10 (wysoka złożoność)
                        if avg_complexity > 10:
                            complex_files.append(
                                {
                                    "path": str(
                                        file_path.relative_to(self.workspace_root)
                                    ),
                                    "avg_complexity": avg_complexity,
                                    "functions_count": len(visitor.functions),
                                }
                            )

                except Exception as e:
                    logger.debug(f"Nie można przeanalizować {file_path}: {e}")
                    continue

            # Sortuj po złożoności (malejąco)
            complex_files.sort(key=lambda x: x["avg_complexity"], reverse=True)

            logger.info(f"Znaleziono {len(complex_files)} plików o wysokiej złożoności")
            return complex_files

        except ImportError:
            logger.warning(
                "Radon nie jest zainstalowany, nie można analizować złożoności"
            )
            return []
        except Exception as e:
            logger.error(f"Błąd podczas analizy złożoności: {e}")
            return []

    async def _create_refactoring_branch(self) -> bool:
        """
        Tworzy branch dla automatycznej refaktoryzacji.

        Returns:
            True jeśli branch został utworzony, False w przeciwnym razie
        """
        try:
            from git import GitCommandError, Repo

            repo = Repo(self.workspace_root)

            # Sprawdź czy jesteśmy w repo Git
            if repo.bare:
                logger.warning("Workspace nie jest repozytorium Git")
                return False

            branch_name = "refactor/auto-gardening"

            # Sprawdź czy branch już istnieje
            if branch_name in [b.name for b in repo.branches]:
                logger.info(f"Branch {branch_name} już istnieje")
                return False

            # Utwórz nowy branch
            repo.create_head(branch_name)
            logger.info(f"Utworzono branch: {branch_name}")

            return True

        except GitCommandError as e:
            logger.warning(f"Nie można utworzyć brancha: {e}")
            return False
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia brancha: {e}")
            return False
