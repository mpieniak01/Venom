"""Moduł: campaign - Logika trybu kampanii (Campaign Mode)."""

import asyncio
from typing import Callable, Optional

from venom_core.core.goal_store import GoalStatus
from venom_core.core.models import TaskRequest, TaskStatus
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CampaignFlow:
    """Logika trybu kampanii - autonomiczna realizacja roadmapy."""

    def __init__(
        self,
        state_manager: StateManager,
        orchestrator_submit_task: Callable,
        event_broadcaster: Optional[Callable] = None,
    ):
        """
        Inicjalizacja CampaignFlow.

        Args:
            state_manager: Menedżer stanu zadań
            orchestrator_submit_task: Callable do submit_task z orchestratora
            event_broadcaster: Opcjonalny broadcaster zdarzeń
        """
        self.state_manager = state_manager
        self.orchestrator_submit_task = orchestrator_submit_task
        self.event_broadcaster = event_broadcaster

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

    async def execute(self, goal_store=None, max_iterations: int = 10) -> dict:
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

        # Utwórz zadanie trackingowe
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

        iteration = 0
        tasks_completed = 0
        tasks_failed = 0

        try:
            while iteration < max_iterations:
                iteration += 1

                self.state_manager.add_log(
                    task_id, f"📍 Iteracja {iteration}/{max_iterations}"
                )

                # 1. Pobierz kolejne zadanie
                next_task = goal_store.get_next_task()

                if not next_task:
                    # Sprawdź czy obecny milestone jest ukończony
                    current_milestone = goal_store.get_next_milestone()
                    if not current_milestone:
                        self.state_manager.add_log(
                            task_id, "✅ Brak kolejnych zadań - roadmapa ukończona!"
                        )
                        break

                    # Milestone ukończony, przejdź do kolejnego
                    if current_milestone.get_progress() >= 100:
                        goal_store.update_progress(
                            current_milestone.goal_id, status=GoalStatus.COMPLETED
                        )
                        self.state_manager.add_log(
                            task_id,
                            f"✅ Milestone ukończony: {current_milestone.title}",
                        )

                        # Sprawdź kolejny milestone
                        next_milestone = goal_store.get_next_milestone()
                        if not next_milestone:
                            self.state_manager.add_log(
                                task_id,
                                "🎉 Wszystkie Milestones ukończone! Kampania zakończona.",
                            )
                            break

                        continue
                    else:
                        self.state_manager.add_log(
                            task_id, "⚠️ Brak zadań w obecnym Milestone"
                        )
                        break

                # 2. Oznacz zadanie jako w trakcie
                goal_store.update_progress(
                    next_task.goal_id, status=GoalStatus.IN_PROGRESS
                )
                self.state_manager.add_log(
                    task_id, f"🎯 Rozpoczynam: {next_task.title}"
                )

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

                # 3. Wykonaj zadanie - utwórz sub-task w orchestratorze
                task_request = TaskRequest(content=next_task.description)
                task_response = await self.orchestrator_submit_task(task_request)

                # Poczekaj na ukończenie sub-task (z timeout)
                wait_time = 0
                max_wait = 300  # 5 minut
                while wait_time < max_wait:
                    sub_task = self.state_manager.get_task(task_response.task_id)
                    if sub_task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                        break
                    await asyncio.sleep(5)
                    wait_time += 5

                sub_task = self.state_manager.get_task(task_response.task_id)

                # 4. Zaktualizuj postęp w GoalStore
                if sub_task.status == TaskStatus.COMPLETED:
                    goal_store.update_progress(
                        next_task.goal_id,
                        status=GoalStatus.COMPLETED,
                        task_id=sub_task.id,
                    )
                    tasks_completed += 1

                    self.state_manager.add_log(
                        task_id, f"✅ Ukończono: {next_task.title}"
                    )

                    await self._broadcast_event(
                        event_type="CAMPAIGN_TASK_COMPLETED",
                        message=f"Zadanie ukończone: {next_task.title}",
                        agent="Executive",
                        data={"goal_id": str(next_task.goal_id)},
                    )
                else:
                    goal_store.update_progress(
                        next_task.goal_id, status=GoalStatus.BLOCKED
                    )
                    tasks_failed += 1

                    self.state_manager.add_log(
                        task_id, f"❌ Nie udało się: {next_task.title}"
                    )

                    await self._broadcast_event(
                        event_type="CAMPAIGN_TASK_FAILED",
                        message=f"Zadanie nie powiodło się: {next_task.title}",
                        agent="Executive",
                        data={"goal_id": str(next_task.goal_id)},
                    )

                # 5. Human-in-the-loop checkpoint - co milestone
                current_milestone = goal_store.get_next_milestone()
                if current_milestone and current_milestone.get_progress() >= 100:
                    self.state_manager.add_log(
                        task_id,
                        f"🏁 Milestone ukończony: {current_milestone.title}. "
                        "Pauza dla akceptacji użytkownika.",
                    )
                    break  # Zatrzymaj się i czekaj na akceptację

            # Podsumowanie
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
