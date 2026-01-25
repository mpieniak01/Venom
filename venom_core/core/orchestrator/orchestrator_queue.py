"""Helpers for queue operations in Orchestrator."""

from __future__ import annotations

from uuid import UUID


async def pause_queue(task_manager) -> dict:
    """Wstrzymuje przyjmowanie nowych zadań."""
    return await task_manager.pause()


async def resume_queue(task_manager) -> dict:
    """Wznawia przyjmowanie zadań."""
    return await task_manager.resume()


async def purge_queue(task_manager) -> dict:
    """Usuwa wszystkie zadania o statusie PENDING z kolejki."""
    return await task_manager.purge()


async def abort_task(task_manager, task_id: UUID) -> dict:
    """Przerywa wykonywanie konkretnego zadania."""
    return await task_manager.abort_task(task_id)


async def emergency_stop(task_manager) -> dict:
    """Awaryjne zatrzymanie - przerywa aktywne zadania i czyści kolejkę."""
    return await task_manager.emergency_stop()


def get_queue_status(task_manager) -> dict:
    """Zwraca aktualny status kolejki zadań."""
    return task_manager.get_status()
