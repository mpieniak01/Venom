"""Moduł: scheduler - System harmonogramowania zadań w tle (THE_OVERMIND)."""

import asyncio
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from venom_core.api.stream import EventType, event_broadcaster
from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class BackgroundScheduler:
    """
    System harmonogramowania zadań w tle.
    Wykorzystuje APScheduler do zarządzania zadaniami cyklicznymi i zdarzeniowymi.
    """

    def __init__(self, event_broadcaster=None):
        """
        Inicjalizacja schedulera.

        Args:
            event_broadcaster: Broadcaster zdarzeń do WebSocket
        """
        self.scheduler = AsyncIOScheduler()
        self.event_broadcaster = event_broadcaster
        self.is_running = False
        self._jobs_registry = {}  # Rejestr zadań: job_id -> metadata

        logger.info("BackgroundScheduler zainicjalizowany")

    async def start(self) -> None:
        """Uruchamia scheduler."""
        if self.is_running:
            logger.warning("Scheduler już działa")
            return

        if SETTINGS.VENOM_PAUSE_BACKGROUND_TASKS:
            logger.warning(
                "Zadania w tle są wstrzymane (VENOM_PAUSE_BACKGROUND_TASKS=True)"
            )
            return

        try:
            self.scheduler.start()
            self.is_running = True
            logger.info("BackgroundScheduler uruchomiony")

            if self.event_broadcaster:
                await self.event_broadcaster.broadcast_event(
                    event_type=EventType.SYSTEM_LOG,
                    message="Background Scheduler started",
                    data={"level": "INFO"},
                )

        except Exception as e:
            logger.error(f"Błąd podczas uruchamiania schedulera: {e}")
            raise

    async def stop(self) -> None:
        """Zatrzymuje scheduler."""
        if not self.is_running:
            logger.warning("Scheduler nie działa")
            return

        try:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("BackgroundScheduler zatrzymany")

            if self.event_broadcaster:
                await self.event_broadcaster.broadcast_event(
                    event_type=EventType.SYSTEM_LOG,
                    message="Background Scheduler stopped",
                    data={"level": "INFO"},
                )

        except Exception as e:
            logger.error(f"Błąd podczas zatrzymywania schedulera: {e}")
            raise

    def add_interval_job(
        self,
        func: Callable,
        minutes: Optional[int] = None,
        seconds: Optional[int] = None,
        job_id: str = None,
        description: str = "",
        **kwargs,
    ) -> str:
        """
        Dodaje zadanie wykonywane w interwałach.

        Args:
            func: Funkcja do wykonania (może być async)
            minutes: Interwał w minutach
            seconds: Interwał w sekundach
            job_id: Unikalne ID zadania (opcjonalne)
            description: Opis zadania
            **kwargs: Dodatkowe argumenty dla funkcji

        Returns:
            ID dodanego zadania
        """
        if not minutes and not seconds:
            raise ValueError("Musisz podać minutes lub seconds")

        trigger = IntervalTrigger(minutes=minutes or 0, seconds=seconds or 0)

        job = self.scheduler.add_job(
            func, trigger=trigger, id=job_id, kwargs=kwargs, replace_existing=True
        )

        self._jobs_registry[job.id] = {
            "type": "interval",
            "description": description,
            "added_at": datetime.now().isoformat(),
            "interval_minutes": minutes,
            "interval_seconds": seconds,
        }

        logger.info(f"Dodano zadanie interwałowe: {job.id} - {description}")
        return job.id

    def add_cron_job(
        self,
        func: Callable,
        cron_expression: str,
        job_id: str = None,
        description: str = "",
        **kwargs,
    ) -> str:
        """
        Dodaje zadanie wykonywane według wyrażenia cron.

        Args:
            func: Funkcja do wykonania (może być async)
            cron_expression: Wyrażenie cron (np. "0 2 * * *" dla 2:00 co dzień)
            job_id: Unikalne ID zadania (opcjonalne)
            description: Opis zadania
            **kwargs: Dodatkowe argumenty dla funkcji

        Returns:
            ID dodanego zadania
        """
        trigger = CronTrigger.from_crontab(cron_expression)

        job = self.scheduler.add_job(
            func, trigger=trigger, id=job_id, kwargs=kwargs, replace_existing=True
        )

        self._jobs_registry[job.id] = {
            "type": "cron",
            "description": description,
            "added_at": datetime.now().isoformat(),
            "cron_expression": cron_expression,
        }

        logger.info(f"Dodano zadanie cron: {job.id} - {description}")
        return job.id

    def remove_job(self, job_id: str) -> bool:
        """
        Usuwa zadanie.

        Args:
            job_id: ID zadania do usunięcia

        Returns:
            True jeśli zadanie zostało usunięte, False jeśli nie istnieje
        """
        try:
            self.scheduler.remove_job(job_id)
            if job_id in self._jobs_registry:
                del self._jobs_registry[job_id]
            logger.info(f"Usunięto zadanie: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Nie można usunąć zadania {job_id}: {e}")
            return False

    def get_jobs(self) -> list[dict]:
        """
        Zwraca listę wszystkich zadań.

        Returns:
            Lista zadań z metadanymi
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            job_info = {
                "id": job.id,
                "next_run_time": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "name": job.name,
            }

            # Dodaj metadane z rejestru jeśli są dostępne
            if job.id in self._jobs_registry:
                job_info.update(self._jobs_registry[job.id])

            jobs.append(job_info)

        return jobs

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """
        Zwraca status konkretnego zadania.

        Args:
            job_id: ID zadania

        Returns:
            Słownik ze statusem lub None jeśli zadanie nie istnieje
        """
        job = self.scheduler.get_job(job_id)
        if not job:
            return None

        status = {
            "id": job.id,
            "name": job.name,
            "next_run_time": (
                job.next_run_time.isoformat() if job.next_run_time else None
            ),
        }

        if job_id in self._jobs_registry:
            status.update(self._jobs_registry[job_id])

        return status

    async def pause_all_jobs(self) -> None:
        """Wstrzymuje wszystkie zadania."""
        self.scheduler.pause()
        logger.info("Wszystkie zadania wstrzymane")

        if self.event_broadcaster:
            await self.event_broadcaster.broadcast_event(
                event_type=EventType.SYSTEM_LOG,
                message="All background jobs paused",
                data={"level": "WARNING"},
            )

    async def resume_all_jobs(self) -> None:
        """Wznawia wszystkie zadania."""
        self.scheduler.resume()
        logger.info("Wszystkie zadania wznowione")

        if self.event_broadcaster:
            await self.event_broadcaster.broadcast_event(
                event_type=EventType.SYSTEM_LOG,
                message="All background jobs resumed",
                data={"level": "INFO"},
            )

    def get_status(self) -> dict:
        """
        Zwraca status schedulera.

        Returns:
            Słownik ze statusem
        """
        return {
            "is_running": self.is_running,
            "paused": SETTINGS.VENOM_PAUSE_BACKGROUND_TASKS,
            "jobs_count": len(self.scheduler.get_jobs()),
            "state": str(self.scheduler.state),
        }
