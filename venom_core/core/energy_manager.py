"""Moduł: energy_manager - Zarządca Energii dla Systemu Śnienia."""

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

import psutil

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SystemMetrics:
    """Metryki użycia systemu."""

    cpu_percent: float  # Użycie CPU (0-100)
    memory_percent: float  # Użycie pamięci (0-100)
    temperature: Optional[float] = None  # Temperatura CPU (jeśli dostępna)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class EnergyManager:
    """
    Zarządca Energii - monitoruje zasoby systemowe i zarządza procesami śnienia.

    Rola:
    - Monitoruje CPU, pamięć, temperaturę
    - Wykrywa aktywność użytkownika
    - Zarządza priorytetami procesów śnienia
    - Natychmiastowo przerywa śnienie gdy użytkownik wraca
    """

    def __init__(
        self,
        cpu_threshold: float = None,
        memory_threshold: float = None,
        check_interval: int = 5,
    ):
        """
        Inicjalizacja EnergyManager.

        Args:
            cpu_threshold: Próg użycia CPU (0.0-1.0), domyślnie z SETTINGS
            memory_threshold: Próg użycia pamięci (0.0-1.0), domyślnie z SETTINGS
            check_interval: Interwał sprawdzania w sekundach
        """
        self.cpu_threshold = (
            cpu_threshold or SETTINGS.DREAMING_CPU_THRESHOLD
        )  # np. 0.7 = 70%
        self.memory_threshold = (
            memory_threshold or SETTINGS.DREAMING_MEMORY_THRESHOLD
        )  # np. 0.8 = 80%
        self.check_interval = check_interval

        self.is_monitoring = False
        self.last_activity_time = time.time()
        self._monitor_task: Optional[asyncio.Task] = None
        self._alert_callbacks: List[Callable] = []
        self.sensors_active = True  # Flaga aktywności sensorów sprzętowych

        logger.info(
            f"EnergyManager zainicjalizowany (CPU threshold={self.cpu_threshold}, "
            f"Memory threshold={self.memory_threshold})"
        )

    def get_metrics(self) -> SystemMetrics:
        """
        Pobiera aktualne metryki systemu.

        Returns:
            SystemMetrics z danymi o użyciu zasobów
        """
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent

        # Próba pobrania temperatury (nie wszystkie systemy to wspierają)
        temperature = None
        try:
            temps = psutil.sensors_temperatures()
            if temps and "coretemp" in temps:
                # Średnia temperatura z rdzeni
                core_temps = [temp.current for temp in temps["coretemp"]]
                temperature = sum(core_temps) / len(core_temps) if core_temps else None
        except (AttributeError, Exception) as e:
            # sensors_temperatures może nie być dostępne na wszystkich platformach
            logger.warning(f"Hardware sensor failure: {e}")
            self.sensors_active = False

        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            temperature=temperature,
        )

    def is_system_busy(self) -> bool:
        """
        Sprawdza czy system jest zajęty (powyżej progów).

        Returns:
            True jeśli system przekroczył progi, False w przeciwnym razie
        """
        metrics = self.get_metrics()

        cpu_busy = metrics.cpu_percent > (self.cpu_threshold * 100)
        memory_busy = metrics.memory_percent > (self.memory_threshold * 100)

        if cpu_busy or memory_busy:
            logger.debug(
                f"System zajęty: CPU={metrics.cpu_percent:.1f}%, "
                f"Memory={metrics.memory_percent:.1f}%"
            )
            return True

        return False

    def set_low_priority(self, pid: Optional[int] = None) -> bool:
        """
        Ustawia niski priorytet dla procesu (nice value).

        Args:
            pid: ID procesu (None = aktualny proces)

        Returns:
            True jeśli udało się ustawić priorytet
        """
        try:
            process = psutil.Process(pid) if pid else psutil.Process()

            # Na Linux/Unix używamy nice value (19 = najniższy priorytet)
            # Na Windows używamy priority class
            if os.name == "posix":
                # Linux/Unix
                os.nice(SETTINGS.DREAMING_PROCESS_PRIORITY)
                logger.info(
                    f"Ustawiono niski priorytet "
                    f"(nice={SETTINGS.DREAMING_PROCESS_PRIORITY}) "
                    f"dla PID {process.pid}"
                )
            else:
                # Windows
                process.nice(psutil.IDLE_PRIORITY_CLASS)
                logger.info(f"Ustawiono IDLE priority dla PID {process.pid}")

            return True

        except Exception as e:
            logger.warning(
                f"Nie udało się ustawić priorytetu procesu: {e}", exc_info=True
            )
            return False

    def register_alert_callback(self, callback: Callable) -> None:
        """
        Rejestruje callback wywoływany gdy system staje się zajęty.

        Args:
            callback: Async funkcja do wywołania
        """
        self._alert_callbacks.append(callback)
        logger.debug(f"Zarejestrowano alert callback: {callback.__name__}")

    async def start_monitoring(self) -> None:
        """Rozpoczyna monitorowanie systemu w tle."""
        if self.is_monitoring:
            logger.warning("Monitoring już działa")
            return

        self.is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Rozpoczęto monitorowanie systemu")

    async def stop_monitoring(self) -> None:
        """Zatrzymuje monitorowanie systemu."""
        self.is_monitoring = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                # Oczekiwane anulowanie zadania monitoringu — brak dalszych działań
                pass

        logger.info("Zatrzymano monitorowanie systemu")

    async def _monitoring_loop(self) -> None:
        """Główna pętla monitorowania (działa w tle)."""
        logger.debug("Monitoring loop uruchomiony")

        while self.is_monitoring:
            try:
                if self.is_system_busy():
                    logger.warning("System zajęty - wywoływanie callbacków")

                    # Wywołaj wszystkie zarejestrowane callbacki
                    for callback in self._alert_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback()
                            else:
                                callback()
                        except Exception as e:
                            logger.error(f"Błąd w alert callback: {e}", exc_info=True)

                # Czekaj przed następnym sprawdzeniem
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                logger.debug("Monitoring loop anulowany")
                break
            except Exception as e:
                logger.error(f"Błąd w monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)

    def get_idle_time(self) -> float:
        """
        Zwraca czas bezczynności w sekundach.

        Returns:
            Liczba sekund od ostatniej aktywności
        """
        return time.time() - self.last_activity_time

    def mark_activity(self) -> None:
        """Oznacza aktywność użytkownika (resetuje licznik bezczynności)."""
        self.last_activity_time = time.time()
        logger.debug("Aktywność użytkownika zarejestrowana")

    def is_idle(self, threshold_minutes: Optional[int] = None) -> bool:
        """
        Sprawdza czy system jest bezczynny.

        Args:
            threshold_minutes: Próg bezczynności w minutach (domyślnie z SETTINGS)

        Returns:
            True jeśli system jest bezczynny przez więcej niż threshold_minutes
        """
        threshold = (threshold_minutes or SETTINGS.DREAMING_IDLE_THRESHOLD_MINUTES) * 60
        idle_time = self.get_idle_time()
        return idle_time >= threshold

    async def wake_up(self) -> None:
        """
        Natychmiastowe "obudzenie" - przerywa wszystkie procesy śnienia.
        Wywoływane gdy użytkownik wraca do aktywności.
        """
        logger.warning("⏰ WAKE UP! Użytkownik aktywny - przerywanie śnienia")

        # Oznacz aktywność
        self.mark_activity()

        # Tu można dodać logikę zatrzymania kontenerów Docker
        # lub innych procesów śnienia (zostanie zaimplementowane w DreamEngine)

        logger.info("System wybudzony, zasoby zwolnione")

    def get_status(self) -> dict:
        """
        Zwraca status EnergyManager.

        Returns:
            Słownik ze statusem
        """
        metrics = self.get_metrics()
        idle_time = self.get_idle_time()

        return {
            "is_monitoring": self.is_monitoring,
            "cpu_percent": metrics.cpu_percent,
            "memory_percent": metrics.memory_percent,
            "temperature": metrics.temperature,
            "cpu_threshold": self.cpu_threshold * 100,
            "memory_threshold": self.memory_threshold * 100,
            "is_busy": self.is_system_busy(),
            "idle_time_seconds": idle_time,
            "is_idle": self.is_idle(),
            "registered_callbacks": len(self._alert_callbacks),
        }
