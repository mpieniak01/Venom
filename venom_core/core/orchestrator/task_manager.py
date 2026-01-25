"""Moduł: task_manager - zarządzanie kolejką i cyklem życia zadań."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from venom_core.core.queue_manager import QueueManager


class TaskManager:
    """Wrapper nad QueueManager z ujednoliconym API dla Orchestratora."""

    def __init__(self, queue_manager: QueueManager):
        self._queue_manager = queue_manager

    @property
    def is_paused(self) -> bool:
        return self._queue_manager.is_paused

    @property
    def active_tasks(self) -> dict:
        return self._queue_manager.active_tasks

    async def check_capacity(self) -> tuple[bool, int]:
        return await self._queue_manager.check_capacity()

    async def register_task(self, task_id: UUID, task_handle: Any) -> None:
        await self._queue_manager.register_task(task_id, task_handle)

    async def unregister_task(self, task_id: UUID) -> None:
        await self._queue_manager.unregister_task(task_id)

    async def pause(self) -> dict:
        return await self._queue_manager.pause()

    async def resume(self) -> dict:
        return await self._queue_manager.resume()

    async def purge(self) -> dict:
        return await self._queue_manager.purge()

    async def abort_task(self, task_id: UUID) -> dict:
        return await self._queue_manager.abort_task(task_id)

    async def emergency_stop(self) -> dict:
        return await self._queue_manager.emergency_stop()

    def get_status(self) -> dict:
        return self._queue_manager.get_status()
