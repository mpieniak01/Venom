"""Moduł: scheduler - System harmonogramowania zadań w tle (THE_OVERMIND)."""

import os
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from venom_core.api.stream import EventType
from venom_core.config import SETTINGS
from venom_core.core.dream_engine import DreamState
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class BackgroundScheduler:
    """
    System harmonogramowania zadań w tle.
    Wykorzystuje APScheduler do zarządzania zadaniami cyklicznymi i zdarzeniowymi.
    """

    def __init__(
        self, event_broadcaster=None, allow_test_override: Optional[bool] = None
    ):
        """
        Inicjalizacja schedulera.

        Args:
            event_broadcaster: Broadcaster zdarzeń do WebSocket
        """
        self.scheduler = AsyncIOScheduler()
        self.event_broadcaster = event_broadcaster
        self.is_running = False
        self._jobs_registry = {}  # Rejestr zadań: job_id -> metadata
        self._allow_test_override = (
            allow_test_override
            if allow_test_override is not None
            else bool(os.environ.get("PYTEST_CURRENT_TEST"))
        )

        logger.info("BackgroundScheduler zainicjalizowany")

    async def start(self) -> None:
        """Uruchamia scheduler."""
        if self.is_running:
            logger.warning("Scheduler już działa")
            return

        if SETTINGS.VENOM_PAUSE_BACKGROUND_TASKS and not self._allow_test_override:
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
            next_run_attr = getattr(job, "next_run_time", None)
            next_run_time = None
            if callable(next_run_attr):
                try:
                    next_run_time = next_run_attr()
                except Exception:
                    next_run_time = None
            else:
                next_run_time = next_run_attr

            job_info = {
                "id": job.id,
                "next_run_time": (
                    next_run_time.isoformat()
                    if hasattr(next_run_time, "isoformat")
                    else None
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

        next_run_attr = getattr(job, "next_run_time", None)
        next_run_time = None
        if callable(next_run_attr):
            try:
                next_run_time = next_run_attr()
            except Exception:
                next_run_time = None
        else:
            next_run_time = next_run_attr

        status = {
            "id": job.id,
            "name": job.name,
            "next_run_time": (
                next_run_time.isoformat()
                if hasattr(next_run_time, "isoformat")
                else None
            ),
        }

        if job_id in self._jobs_registry:
            status.update(self._jobs_registry[job_id])

        return status

    async def pause_all_jobs(self) -> None:
        """Wstrzymuje wszystkie zadania."""
        if not self.is_running or self.scheduler.state == STATE_STOPPED:
            logger.warning("Nie można wstrzymać - scheduler nie działa")
            return

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
        if not self.is_running or self.scheduler.state == STATE_STOPPED:
            logger.warning("Nie można wznowić - scheduler nie działa")
            return

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
        # Mapowanie stanu APSchedulera na uproszczony string
        aps_state = self.scheduler.state
        if aps_state == STATE_RUNNING:
            state_str = "running"
        elif aps_state == STATE_PAUSED:
            state_str = "paused"
        elif aps_state == STATE_STOPPED:
            state_str = "stopped"
        else:
            state_str = "unknown"

        return {
            "is_running": self.is_running,
            "paused": aps_state == STATE_PAUSED,  # Faktyczny stan paused schedulera
            "jobs_count": len(self.scheduler.get_jobs()),
            "state": state_str,
        }

    def schedule_daily_standup(
        self, executive_agent, hour: int = 9, minute: int = 0
    ) -> str:
        """
        Harmonogramuje codzienne spotkanie statusowe (Daily Standup).

        Args:
            executive_agent: Instancja ExecutiveAgent
            hour: Godzina spotkania (domyślnie 9:00)
            minute: Minuta spotkania

        Returns:
            ID zadania
        """

        # Funkcja do wykonania
        async def daily_standup():
            logger.info("⏰ Rozpoczynam Daily Standup (scheduled)")
            try:
                report = await executive_agent.run_status_meeting()
                logger.info(f"Daily Standup zakończony:\n{report}")

                # Broadcast przez event broadcaster jeśli dostępny
                if self.event_broadcaster:
                    await self.event_broadcaster.broadcast_event(
                        event_type="DAILY_STANDUP",
                        message="Raport z Daily Standup",
                        agent="Executive",
                        data={"report": report},
                    )
            except Exception as e:
                logger.error(f"Błąd podczas Daily Standup: {e}")

        # Cron expression: 0 9 * * * (codziennie o 9:00)
        cron_expr = f"{minute} {hour} * * *"

        job_id = self.add_cron_job(
            func=daily_standup,
            cron_expression=cron_expr,
            job_id="daily_standup",
            description=f"Daily Standup - codziennie o {hour}:{minute:02d}",
        )

        logger.info(f"Zaplanowano Daily Standup na codziennie o {hour}:{minute:02d}")
        return job_id

    def schedule_nightly_dreaming(
        self, dream_engine, start_hour: int = 2, end_hour: int = 6
    ) -> str:
        """
        Harmonogramuje nocne śnienie (nightly REM phase).

        Args:
            dream_engine: Instancja DreamEngine
            start_hour: Godzina rozpoczęcia nocnego śnienia (domyślnie 2:00)
            end_hour: Godzina zakończenia okna nocnego (informacyjna)

        Returns:
            ID zadania
        """

        # Funkcja do wykonania
        async def nightly_dream():
            logger.info(f"🌙 Rozpoczynam nocne śnienie (scheduled {start_hour}:00)")
            try:
                report = await dream_engine.enter_rem_phase()
                logger.info(f"Nocne śnienie zakończone:\n{report}")

                # Broadcast przez event broadcaster jeśli dostępny
                if self.event_broadcaster:
                    await self.event_broadcaster.broadcast_event(
                        event_type="DREAM_SESSION",
                        message="Raport z nocnego śnienia",
                        agent="DreamEngine",
                        data={"report": report},
                    )
            except Exception as e:
                logger.error(f"Błąd podczas nocnego śnienia: {e}")

        # Cron expression: 0 2 * * * (codziennie o 2:00)
        cron_expr = f"0 {start_hour} * * *"

        job_id = self.add_cron_job(
            func=nightly_dream,
            cron_expression=cron_expr,
            job_id="nightly_dreaming",
            description=f"Nightly Dreaming - codziennie o {start_hour}:00-{end_hour}:00",
        )

        logger.info(
            f"Zaplanowano nocne śnienie na codziennie o {start_hour}:00-{end_hour}:00"
        )
        return job_id

    def schedule_idle_dreaming(
        self, dream_engine, check_interval_minutes: int = 5
    ) -> str:
        """
        Harmonogramuje sprawdzanie bezczynności i uruchamianie śnienia.

        Args:
            dream_engine: Instancja DreamEngine
            check_interval_minutes: Interwał sprawdzania bezczynności

        Returns:
            ID zadania
        """

        # Funkcja do wykonania
        async def check_idle_and_dream():
            # Sprawdź czy system bezczynny i czy nie śnimy już
            if (
                dream_engine.energy_manager.is_idle()
                and dream_engine.state == DreamState.IDLE
                and not dream_engine.energy_manager.is_system_busy()
            ):
                logger.info("💤 System bezczynny - rozpoczynam śnienie...")
                try:
                    report = await dream_engine.enter_rem_phase(max_scenarios=3)
                    logger.info(f"Idle dreaming zakończone:\n{report}")

                    # Broadcast przez event broadcaster jeśli dostępny
                    if self.event_broadcaster:
                        await self.event_broadcaster.broadcast_event(
                            event_type="DREAM_SESSION",
                            message="Raport z idle dreaming",
                            agent="DreamEngine",
                            data={"report": report, "trigger": "idle"},
                        )
                except Exception as e:
                    logger.error(f"Błąd podczas idle dreaming: {e}")

        job_id = self.add_interval_job(
            func=check_idle_and_dream,
            minutes=check_interval_minutes,
            job_id="idle_dreaming_check",
            description=f"Idle Dreaming Check - co {check_interval_minutes} minut",
        )

        logger.info(
            f"Zaplanowano sprawdzanie bezczynności co {check_interval_minutes} minut"
        )
        return job_id
