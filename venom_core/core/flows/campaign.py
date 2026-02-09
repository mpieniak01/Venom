"""Moduł: campaign - Logika trybu kampanii (Campaign Mode)."""

import asyncio
from typing import Awaitable, Callable, Optional, Protocol
from uuid import UUID

from venom_core.core.flows.base import BaseFlow, EventBroadcaster
from venom_core.core.goal_store import GoalStatus
from venom_core.core.models import TaskRequest, TaskResponse, TaskStatus
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class GoalLike(Protocol):
    goal_id: UUID
    title: str
    description: str

    def get_progress(self) -> float: ...


class GoalStoreLike(Protocol):
    def get_next_task(self) -> Optional[GoalLike]: ...

    def get_next_milestone(self) -> Optional[GoalLike]: ...

    def update_progress(
        self,
        goal_id: UUID,
        *,
        status: Optional[GoalStatus] = None,
        task_id: Optional[UUID] = None,
    ) -> object: ...

    def generate_roadmap_report(self) -> str: ...


class CampaignFlow(BaseFlow):
    """Logika trybu kampanii - autonomiczna realizacja roadmapy."""

    def __init__(
        self,
        state_manager: StateManager,
        orchestrator_submit_task: Callable[[TaskRequest], Awaitable[TaskResponse]],
        event_broadcaster: Optional[EventBroadcaster] = None,
    ):
        """
        Inicjalizacja CampaignFlow.

        Args:
            state_manager: Menedżer stanu zadań
            orchestrator_submit_task: Callable do submit_task z orchestratora
            event_broadcaster: Opcjonalny broadcaster zdarzeń
        """
        super().__init__(event_broadcaster)
        self.state_manager = state_manager
        self.orchestrator_submit_task = orchestrator_submit_task

    async def execute(
        self, goal_store: Optional[GoalStoreLike] = None, max_iterations: int = 10
    ) -> dict:
        """
        Tryb Kampanii - autonomiczna realizacja roadmapy.

        System wchodzi w pętlę ciągłą:
        1. Pobierz kolejne zadanie z GoalStore
        2. Wykonaj zadanie
        3. Zweryfikuj (Guardian)
        4. Zaktualizuj postęp
        5. Czy cel osiągnięty? Jeśli NIE, wróć do 1.

        Args:
            goal_store: Magazyn celów (GoalStore)
            max_iterations: Maksymalna liczba iteracji (zabezpieczenie)

        Returns:
            Dict z wynikami kampanii
        """
        if not goal_store:
            return {
                "success": False,
                "message": "GoalStore nie został przekazany",
            }

        logger.info("🚀 Rozpoczynam Tryb Kampanii (Autonomous Campaign Mode)")
        task_id = await self._start_campaign(max_iterations)

        iteration = 0
        tasks_completed = 0
        tasks_failed = 0

        try:
            while iteration < max_iterations:
                iteration += 1
                self.state_manager.add_log(
                    task_id, f"📍 Iteracja {iteration}/{max_iterations}"
                )
                next_task = goal_store.get_next_task()
                if not next_task:
                    should_continue = self._handle_missing_campaign_task(
                        goal_store, task_id
                    )
                    if should_continue:
                        continue
                    break

                await self._mark_campaign_task_started(
                    task_id, iteration, next_task, goal_store
                )
                task_response = await self.orchestrator_submit_task(
                    TaskRequest(content=next_task.description)
                )
                sub_task = await self._wait_for_sub_task(task_response.task_id)
                if sub_task is None:
                    self._mark_missing_subtask(
                        task_id, task_response.task_id, next_task, goal_store
                    )
                    tasks_failed += 1
                    break

                was_success = await self._finalize_campaign_task(
                    task_id, next_task, sub_task, goal_store
                )
                if was_success:
                    tasks_completed += 1
                else:
                    tasks_failed += 1

                if self._should_pause_for_milestone(goal_store, task_id):
                    break

            summary = f"""
=== KAMPANIA ZAKOŃCZONA ===

Iteracje: {iteration}/{max_iterations}
Zadania ukończone: {tasks_completed}
Zadania nieudane: {tasks_failed}

Status roadmapy:
{goal_store.generate_roadmap_report()}
"""

            self.state_manager.add_log(task_id, summary)

            await self.state_manager.update_status(
                task_id, TaskStatus.COMPLETED, result=summary
            )

            await self._broadcast_event(
                event_type="CAMPAIGN_COMPLETED",
                message="Kampania zakończona",
                agent="Executive",
                data={
                    "tasks_completed": tasks_completed,
                    "tasks_failed": tasks_failed,
                    "iterations": iteration,
                },
            )

            return {
                "success": True,
                "iterations": iteration,
                "tasks_completed": tasks_completed,
                "tasks_failed": tasks_failed,
                "summary": summary,
            }

        except Exception as e:
            error_msg = f"❌ Błąd podczas Kampanii: {str(e)}"
            logger.error(error_msg)
            self.state_manager.add_log(task_id, error_msg)

            await self.state_manager.update_status(
                task_id, TaskStatus.FAILED, result=error_msg
            )

            return {
                "success": False,
                "error": str(e),
                "iterations": iteration,
                "tasks_completed": tasks_completed,
            }

    async def _start_campaign(self, max_iterations: int) -> UUID:
        task = self.state_manager.create_task(
            content="Autonomiczna Kampania - realizacja roadmapy"
        )
        task_id = task.id
        self.state_manager.add_log(
            task_id, "🚀 CAMPAIGN MODE: Rozpoczęcie autonomicznej realizacji celów"
        )
        await self._broadcast_event(
            event_type="CAMPAIGN_STARTED",
            message="Rozpoczęto Tryb Kampanii",
            agent="Executive",
            data={"task_id": str(task_id), "max_iterations": max_iterations},
        )
        return task_id

    def _handle_missing_campaign_task(
        self, goal_store: GoalStoreLike, task_id: UUID
    ) -> bool:
        current_milestone = goal_store.get_next_milestone()
        if not current_milestone:
            self.state_manager.add_log(
                task_id, "✅ Brak kolejnych zadań - roadmapa ukończona!"
            )
            return False
        if current_milestone.get_progress() < 100:
            self.state_manager.add_log(task_id, "⚠️ Brak zadań w obecnym Milestone")
            return False

        goal_store.update_progress(
            current_milestone.goal_id, status=GoalStatus.COMPLETED
        )
        self.state_manager.add_log(
            task_id, f"✅ Milestone ukończony: {current_milestone.title}"
        )
        next_milestone = goal_store.get_next_milestone()
        if not next_milestone:
            self.state_manager.add_log(
                task_id, "🎉 Wszystkie Milestones ukończone! Kampania zakończona."
            )
            return False
        return True

    async def _mark_campaign_task_started(
        self,
        task_id: UUID,
        iteration: int,
        next_task: GoalLike,
        goal_store: GoalStoreLike,
    ) -> None:
        goal_store.update_progress(next_task.goal_id, status=GoalStatus.IN_PROGRESS)
        self.state_manager.add_log(task_id, f"🎯 Rozpoczynam: {next_task.title}")
        await self._broadcast_event(
            event_type="CAMPAIGN_TASK_STARTED",
            message=f"Kampania: rozpoczęto zadanie {next_task.title}",
            agent="Executive",
            data={
                "task_id": str(task_id),
                "goal_id": str(next_task.goal_id),
                "iteration": iteration,
            },
        )

    async def _wait_for_sub_task(self, sub_task_id: UUID):
        wait_time = 0
        max_wait = 300
        while wait_time < max_wait:
            sub_task = self.state_manager.get_task(sub_task_id)
            if sub_task is None or sub_task.status in [
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
            ]:
                break
            await asyncio.sleep(5)
            wait_time += 5
        return self.state_manager.get_task(sub_task_id)

    def _mark_missing_subtask(
        self,
        task_id: UUID,
        sub_task_id: UUID,
        next_task: GoalLike,
        goal_store: GoalStoreLike,
    ) -> None:
        error_msg = f"❌ Nie znaleziono sub-task w StateManager (task_id={sub_task_id})"
        logger.error(error_msg)
        self.state_manager.add_log(task_id, error_msg)
        goal_store.update_progress(next_task.goal_id, status=GoalStatus.BLOCKED)

    async def _finalize_campaign_task(
        self, task_id: UUID, next_task: GoalLike, sub_task, goal_store: GoalStoreLike
    ) -> bool:
        if sub_task.status == TaskStatus.COMPLETED:
            goal_store.update_progress(
                next_task.goal_id, status=GoalStatus.COMPLETED, task_id=sub_task.id
            )
            self.state_manager.add_log(task_id, f"✅ Ukończono: {next_task.title}")
            await self._broadcast_event(
                event_type="CAMPAIGN_TASK_COMPLETED",
                message=f"Zadanie ukończone: {next_task.title}",
                agent="Executive",
                data={"goal_id": str(next_task.goal_id)},
            )
            return True

        goal_store.update_progress(next_task.goal_id, status=GoalStatus.BLOCKED)
        self.state_manager.add_log(task_id, f"❌ Nie udało się: {next_task.title}")
        await self._broadcast_event(
            event_type="CAMPAIGN_TASK_FAILED",
            message=f"Zadanie nie powiodło się: {next_task.title}",
            agent="Executive",
            data={"goal_id": str(next_task.goal_id)},
        )
        return False

    def _should_pause_for_milestone(
        self, goal_store: GoalStoreLike, task_id: UUID
    ) -> bool:
        current_milestone = goal_store.get_next_milestone()
        if not current_milestone or current_milestone.get_progress() < 100:
            return False
        self.state_manager.add_log(
            task_id,
            f"🏁 Milestone ukończony: {current_milestone.title}. "
            "Pauza dla akceptacji użytkownika.",
        )
        return True
