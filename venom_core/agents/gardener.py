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
    ):
        """
        Inicjalizacja GardenerAgent.

        Args:
            graph_store: Instancja CodeGraphStore (domyślnie nowa)
            workspace_root: Katalog workspace (domyślnie z SETTINGS)
            scan_interval: Interwał skanowania w sekundach (domyślnie 300s = 5min)
        """
        self.graph_store = graph_store or CodeGraphStore(workspace_root=workspace_root)
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.scan_interval = scan_interval

        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._last_scan_time: Optional[datetime] = None
        self._last_file_mtimes: dict = {}

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
                pass

        logger.info("GardenerAgent zatrzymany")

    async def _monitoring_loop(self) -> None:
        """Pętla monitorowania zmian w plikach."""
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

    def trigger_manual_scan(self) -> dict:
        """
        Wyzwala manualne skanowanie (synchroniczne).

        Returns:
            Statystyki skanowania
        """
        logger.info("Manualne skanowanie wywołane")

        try:
            # Załaduj graf
            self.graph_store.load_graph()

            # Skanuj
            stats = self.graph_store.scan_workspace(force_rescan=False)
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
        }
