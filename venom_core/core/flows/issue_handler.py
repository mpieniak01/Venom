"""Moduł: issue_handler - Logika obsługi Issue z GitHub (Issue-to-PR Pipeline)."""

from typing import Optional, Protocol, cast

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.flows.base import BaseFlow, EventBroadcaster
from venom_core.core.models import TaskStatus
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class IssueIntegrator(Protocol):
    async def handle_issue(self, issue_number: int) -> str: ...

    async def process(self, context: str) -> str: ...

    async def finalize_issue(
        self,
        *,
        issue_number: int,
        branch_name: str,
        pr_title: str,
        pr_body: str,
    ) -> str: ...


class IssueHandlerFlow(BaseFlow):
    """Logika obsługi Issue z GitHub - pipeline Issue-to-PR."""

    def __init__(
        self,
        state_manager: StateManager,
        task_dispatcher: TaskDispatcher,
        event_broadcaster: Optional[EventBroadcaster] = None,
    ):
        """
        Inicjalizacja IssueHandlerFlow.

        Args:
            state_manager: Menedżer stanu zadań
            task_dispatcher: Dispatcher zadań (dostęp do agentów)
            event_broadcaster: Opcjonalny broadcaster zdarzeń
        """
        super().__init__(event_broadcaster)
        self.state_manager = state_manager
        self.task_dispatcher = task_dispatcher

    async def execute(self, issue_number: int) -> dict:
        """
        Obsługuje Issue z GitHub: pobiera szczegóły, tworzy plan, implementuje fix, tworzy PR.

        Pipeline "Issue-to-PR":
        1. Integrator pobiera szczegóły Issue
        2. Architekt tworzy plan naprawy
        3. Coder + Guardian implementują fix
        4. Integrator tworzy PR i wysyła powiadomienie

        Args:
            issue_number: Numer Issue do obsłużenia

        Returns:
            Dict z wynikiem operacji
        """
        try:
            logger.info(
                f"🚀 Rozpoczynam workflow Issue-to-PR dla Issue #{issue_number}"
            )

            # Utwórz fikcyjne zadanie w StateManager do trackowania postępów
            task = self.state_manager.create_task(
                content=f"Automatyczna obsługa Issue #{issue_number}"
            )
            task_id = task.id

            self.state_manager.add_log(
                task_id, f"Rozpoczęto obsługę Issue #{issue_number}"
            )

            await self._broadcast_event(
                event_type="ISSUE_PROCESSING_STARTED",
                message=f"Rozpoczynam obsługę Issue #{issue_number}",
                agent="Integrator",
                data={"task_id": str(task_id), "issue_number": issue_number},
            )

            # 1. SETUP: Integrator pobiera Issue i tworzy branch
            integrator = self.task_dispatcher.agent_map.get("GIT_OPERATIONS")
            if not integrator:
                error_msg = "❌ IntegratorAgent nie jest dostępny"
                logger.error(error_msg)
                return {"success": False, "message": error_msg}
            integrator_agent = cast(IssueIntegrator, integrator)

            self.state_manager.add_log(task_id, "Pobieranie szczegółów Issue...")
            issue_details = await integrator_agent.handle_issue(issue_number)

            if issue_details.startswith("❌"):
                self.state_manager.add_log(task_id, issue_details)
                return {"success": False, "message": issue_details}

            self.state_manager.add_log(task_id, "✅ Issue pobrane, branch utworzony")

            await self._broadcast_event(
                event_type="AGENT_ACTION",
                message=f"Pobrano Issue #{issue_number}, utworzono branch",
                agent="Integrator",
                data={"task_id": str(task_id), "issue_number": issue_number},
            )

            # 2. PLANNING: Architekt tworzy plan naprawy
            architect = self.task_dispatcher.agent_map.get("COMPLEX_PLANNING")
            if not architect:
                error_msg = "❌ ArchitectAgent nie jest dostępny"
                logger.error(error_msg)
                return {"success": False, "message": error_msg}

            self.state_manager.add_log(task_id, "Tworzenie planu naprawy...")

            planning_context = f"""Na podstawie poniższego Issue, stwórz plan naprawy:

{issue_details}

WAŻNE: Stwórz konkretny plan kroków do naprawy tego problemu."""

            plan_result = await architect.process(planning_context)
            self.state_manager.add_log(task_id, f"Plan naprawy:\n{plan_result}")

            await self._broadcast_event(
                event_type="AGENT_THOUGHT",
                message="Plan naprawy utworzony",
                agent="Architect",
                data={"task_id": str(task_id), "plan": plan_result[:200]},
            )

            # 3. EXECUTION: Coder implementuje fix (uproszczone - w produkcji byłoby bardziej złożone)
            coder = self.task_dispatcher.agent_map.get("CODE_GENERATION")
            if not coder:
                error_msg = "❌ CoderAgent nie jest dostępny"
                logger.error(error_msg)
                return {"success": False, "message": error_msg}

            self.state_manager.add_log(task_id, "Implementacja fix...")

            # Deleguj do Coder z kontekstem Issue
            fix_context = f"""Zaimplementuj naprawę dla następującego Issue:

{issue_details}

Plan naprawy:
{plan_result}"""

            fix_result = await coder.process(fix_context)
            self.state_manager.add_log(task_id, "✅ Fix zaimplementowany")

            await self._broadcast_event(
                event_type="AGENT_ACTION",
                message="Fix zaimplementowany",
                agent="Coder",
                data={"task_id": str(task_id)},
            )

            # 4. DELIVERY: Integrator commituje, pushuje i tworzy PR
            self.state_manager.add_log(task_id, "Tworzenie Pull Request...")

            # Commitnij zmiany
            commit_context = f"Commitnij zmiany dla Issue #{issue_number}"
            commit_result = await integrator_agent.process(commit_context)
            self.state_manager.add_log(task_id, f"Commit: {commit_result}")

            # Finalizuj Issue (PR + komentarz + powiadomienie)
            branch_name = f"issue-{issue_number}"
            pr_title = f"fix: resolve issue #{issue_number}"
            pr_body = (
                f"Automatyczna naprawa Issue #{issue_number}\n\n{fix_result[:500]}"
            )

            finalize_result = await integrator_agent.finalize_issue(
                issue_number=issue_number,
                branch_name=branch_name,
                pr_title=pr_title,
                pr_body=pr_body,
            )

            self.state_manager.add_log(task_id, finalize_result)

            await self._broadcast_event(
                event_type="ISSUE_PROCESSING_COMPLETED",
                message=f"Issue #{issue_number} sfinalizowane - PR utworzony",
                agent="Integrator",
                data={"task_id": str(task_id), "issue_number": issue_number},
            )

            # Oznacz zadanie jako ukończone
            await self.state_manager.update_status(
                task_id, TaskStatus.COMPLETED, result=finalize_result
            )

            logger.info(f"✅ Workflow Issue-to-PR zakończony dla Issue #{issue_number}")

            return {
                "success": True,
                "issue_number": issue_number,
                "message": finalize_result,
                "task_id": str(task_id),
            }

        except Exception as e:
            error_msg = f"❌ Błąd podczas obsługi Issue #{issue_number}: {str(e)}"
            logger.error(error_msg)

            if "task_id" in locals():
                self.state_manager.add_log(task_id, error_msg)
                await self.state_manager.update_status(
                    task_id, TaskStatus.FAILED, result=error_msg
                )

            return {
                "success": False,
                "issue_number": issue_number,
                "message": error_msg,
            }
