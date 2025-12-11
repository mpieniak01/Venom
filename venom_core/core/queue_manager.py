"""Moduł: queue_manager - Zarządzanie kolejką zadań."""

import asyncio
from typing import Callable, Dict, Optional
from uuid import UUID

from venom_core.config import SETTINGS
from venom_core.core.models import TaskStatus
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class QueueManager:
    """Menedżer kolejki zadań - zarządzanie pauzą, limitami współbieżności i operacjami."""

    def __init__(
        self,
        state_manager: StateManager,
        event_broadcaster: Optional[Callable] = None,
    ):
        """
        Inicjalizacja QueueManager.

        Args:
            state_manager: Menedżer stanu zadań
            event_broadcaster: Opcjonalny broadcaster zdarzeń
        """
        self.state_manager = state_manager
        self.event_broadcaster = event_broadcaster

        # Stan kolejki
        self.is_paused: bool = False
        self.active_tasks: Dict[UUID, asyncio.Task] = {}
        self._queue_lock = asyncio.Lock()

    async def _broadcast_event(
        self, event_type: str, message: str, agent: str = None, data: dict = None
    ):
        """
        Wysyła zdarzenie do WebSocket (jeśli broadcaster jest dostępny).

        Args:
            event_type: Typ zdarzenia
            message: Treść wiadomości
            agent: Opcjonalna nazwa agenta
            data: Opcjonalne dodatkowe dane
        """
        if self.event_broadcaster:
            await self.event_broadcaster.broadcast_event(
                event_type=event_type, message=message, agent=agent, data=data
            )

    async def pause(self) -> dict:
        """
        Wstrzymuje przyjmowanie nowych zadań do wykonania.

        Returns:
            Dict z wynikiem operacji
        """
        self.is_paused = True
        logger.warning("⏸️ Kolejka zadań wstrzymana (PAUSE)")

        await self._broadcast_event(
            event_type="QUEUE_PAUSED",
            message="Kolejka zadań wstrzymana - nowe zadania czekają",
            data={"active_tasks": len(self.active_tasks)},
        )

        return {
            "success": True,
            "paused": True,
            "active_tasks": len(self.active_tasks),
            "message": "Kolejka wstrzymana. Aktywne zadania kontynuują pracę.",
        }

    async def resume(self) -> dict:
        """
        Wznawia przyjmowanie zadań.

        Returns:
            Dict z wynikiem operacji
        """
        self.is_paused = False
        logger.info("▶️ Kolejka zadań wznowiona (RESUME)")

        # Policz pending tasks
        pending_count = sum(
            1
            for task in self.state_manager.get_all_tasks()
            if task.status == TaskStatus.PENDING
        )

        await self._broadcast_event(
            event_type="QUEUE_RESUMED",
            message="Kolejka zadań wznowiona - przetwarzanie kontynuowane",
            data={"pending_tasks": pending_count},
        )

        return {
            "success": True,
            "paused": False,
            "pending_tasks": pending_count,
            "message": "Kolejka wznowiona. Oczekujące zadania zostaną przetworzone.",
        }

    async def purge(self) -> dict:
        """
        Usuwa wszystkie zadania o statusie PENDING z kolejki.

        Returns:
            Dict z wynikiem operacji (liczba usuniętych zadań)
        """
        removed_count = 0
        all_tasks = self.state_manager.get_all_tasks()

        for task in all_tasks:
            if task.status == TaskStatus.PENDING:
                # Zmień status na FAILED z informacją o purge
                await self.state_manager.update_status(
                    task.id, TaskStatus.FAILED, result="🗑️ Zadanie usunięte przez Purge"
                )
                self.state_manager.add_log(
                    task.id, "Zadanie usunięte z kolejki (Queue Purge)"
                )
                removed_count += 1

        logger.warning(f"🗑️ Purge Queue: Usunięto {removed_count} oczekujących zadań")

        await self._broadcast_event(
            event_type="QUEUE_PURGED",
            message=f"Kolejka wyczyszczona - usunięto {removed_count} zadań",
            data={"removed": removed_count, "active": len(self.active_tasks)},
        )

        return {
            "success": True,
            "removed": removed_count,
            "active_tasks": len(self.active_tasks),
            "message": f"Usunięto {removed_count} oczekujących zadań. Aktywne zadania kontynuują pracę.",
        }

    async def abort_task(self, task_id: UUID) -> dict:
        """
        Przerywa wykonywanie konkretnego zadania.

        Args:
            task_id: ID zadania do przerwania

        Returns:
            Dict z wynikiem operacji
        """
        # Sprawdź czy zadanie istnieje
        task = self.state_manager.get_task(task_id)
        if task is None:
            return {"success": False, "message": f"Zadanie {task_id} nie istnieje"}

        # Sprawdź czy zadanie jest aktywne
        if task.status != TaskStatus.PROCESSING:
            return {
                "success": False,
                "message": f"Zadanie {task_id} nie jest aktywne (status: {task.status})",
            }

        # Pobierz task handle
        async with self._queue_lock:
            task_handle = self.active_tasks.get(task_id)

        if task_handle is None:
            # Zadanie mogło się już zakończyć
            return {
                "success": False,
                "message": f"Zadanie {task_id} nie jest już aktywne",
            }

        # Anuluj task
        task_handle.cancel()

        # Oznacz jako FAILED
        await self.state_manager.update_status(
            task_id, TaskStatus.FAILED, result="⛔ Zadanie przerwane przez użytkownika"
        )
        self.state_manager.add_log(task_id, "Zadanie przerwane przez operatora (ABORT)")

        # Usuń z active tasks
        async with self._queue_lock:
            self.active_tasks.pop(task_id, None)

        logger.warning(f"⛔ Zadanie {task_id} przerwane przez użytkownika")

        await self._broadcast_event(
            event_type="TASK_ABORTED",
            message=f"Zadanie {task_id} zostało przerwane",
            data={"task_id": str(task_id)},
        )

        return {
            "success": True,
            "task_id": str(task_id),
            "message": "Zadanie zostało przerwane",
        }

    async def emergency_stop(self) -> dict:
        """
        Awaryjne zatrzymanie - przerywa wszystkie aktywne zadania i czyści kolejkę.

        Returns:
            Dict z wynikiem operacji
        """
        logger.error("🚨 EMERGENCY STOP - zatrzymuję wszystkie zadania!")

        # Wstrzymaj kolejkę
        self.is_paused = True

        # Anuluj wszystkie aktywne zadania
        tasks_cancelled = 0
        async with self._queue_lock:
            for task_id, task_handle in list(self.active_tasks.items()):
                task_handle.cancel()
                await self.state_manager.update_status(
                    task_id,
                    TaskStatus.FAILED,
                    result="🚨 Zadanie przerwane przez Emergency Stop",
                )
                tasks_cancelled += 1
            self.active_tasks.clear()

        # Purge pending
        purge_result = await self.purge()

        await self._broadcast_event(
            event_type="EMERGENCY_STOP",
            message="🚨 Emergency Stop - wszystkie zadania zatrzymane",
            data={
                "cancelled": tasks_cancelled,
                "purged": purge_result.get("removed", 0),
            },
        )

        return {
            "success": True,
            "cancelled": tasks_cancelled,
            "purged": purge_result.get("removed", 0),
            "paused": True,
            "message": "Emergency Stop wykonany. System wstrzymany.",
        }

    def get_status(self) -> dict:
        """
        Zwraca aktualny status kolejki zadań.

        Returns:
            Dict ze statusem kolejki
        """
        all_tasks = self.state_manager.get_all_tasks()
        pending = sum(1 for t in all_tasks if t.status == TaskStatus.PENDING)
        processing = sum(1 for t in all_tasks if t.status == TaskStatus.PROCESSING)

        return {
            "paused": self.is_paused,
            "pending": pending,
            "active": len(self.active_tasks),
            "processing": processing,  # Z state managera (może się różnić)
            "limit": (
                SETTINGS.MAX_CONCURRENT_TASKS if SETTINGS.ENABLE_QUEUE_LIMITS else None
            ),
        }
