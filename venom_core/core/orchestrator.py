"""Moduł: orchestrator - orkiestracja zadań w tle."""

import asyncio
from datetime import datetime
from uuid import UUID

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.intent_manager import IntentManager
from venom_core.core.models import TaskRequest, TaskResponse, TaskStatus
from venom_core.core.state_manager import StateManager
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class Orchestrator:
    """Orkiestrator zadań - zarządzanie wykonywaniem zadań w tle."""

    def __init__(
        self,
        state_manager: StateManager,
        intent_manager: IntentManager = None,
        task_dispatcher: TaskDispatcher = None,
    ):
        """
        Inicjalizacja Orchestrator.

        Args:
            state_manager: Menedżer stanu zadań
            intent_manager: Opcjonalny menedżer klasyfikacji intencji (jeśli None, zostanie utworzony)
            task_dispatcher: Opcjonalny dispatcher zadań (jeśli None, zostanie utworzony)
        """
        self.state_manager = state_manager
        self.intent_manager = intent_manager or IntentManager()

        # Inicjalizuj dispatcher jeśli nie został przekazany
        if task_dispatcher is None:
            kernel_builder = KernelBuilder()
            kernel = kernel_builder.build_kernel()
            task_dispatcher = TaskDispatcher(kernel)

        self.task_dispatcher = task_dispatcher

    async def submit_task(self, request: TaskRequest) -> TaskResponse:
        """
        Przyjmuje nowe zadanie do wykonania.

        Args:
            request: Żądanie z treścią zadania

        Returns:
            Odpowiedź z ID zadania i statusem
        """
        # Utwórz zadanie przez StateManager
        task = self.state_manager.create_task(content=request.content)

        # Zaloguj event
        log_message = f"Zadanie uruchomione: {datetime.now().isoformat()}"
        self.state_manager.add_log(task.id, log_message)

        # Uruchom zadanie w tle
        asyncio.create_task(self._run_task(task.id))

        logger.info(f"Zadanie {task.id} przyjęte do wykonania")

        return TaskResponse(task_id=task.id, status=task.status)

    async def _run_task(self, task_id: UUID) -> None:
        """
        Wykonuje zadanie w tle.

        Args:
            task_id: ID zadania do wykonania
        """
        try:
            # Pobierz zadanie
            task = self.state_manager.get_task(task_id)
            if task is None:
                logger.error(f"Zadanie {task_id} nie istnieje")
                return

            # Ustaw status PROCESSING
            await self.state_manager.update_status(task_id, TaskStatus.PROCESSING)
            self.state_manager.add_log(
                task_id, f"Rozpoczęto przetwarzanie: {datetime.now().isoformat()}"
            )

            logger.info(f"Rozpoczynam przetwarzanie zadania {task_id}")

            # Klasyfikuj intencję użytkownika
            intent = await self.intent_manager.classify_intent(task.content)

            # Zaloguj sklasyfikowaną intencję
            self.state_manager.add_log(
                task_id,
                f"Sklasyfikowana intencja: {intent} - {datetime.now().isoformat()}",
            )

            # Przekaż zadanie do dispatchera
            result = await self.task_dispatcher.dispatch(intent, task.content)

            # Zaloguj które agent przejął zadanie
            agent_name = self.task_dispatcher.agent_map[intent].__class__.__name__
            self.state_manager.add_log(
                task_id,
                f"Agent {agent_name} przetworzył zadanie - {datetime.now().isoformat()}",
            )

            # Ustaw status COMPLETED i wynik
            await self.state_manager.update_status(
                task_id, TaskStatus.COMPLETED, result=result
            )
            self.state_manager.add_log(
                task_id, f"Zakończono przetwarzanie: {datetime.now().isoformat()}"
            )

            logger.info(f"Zadanie {task_id} zakończone sukcesem")

        except Exception as e:
            # Obsługa błędów - ustaw status FAILED
            logger.error(f"Błąd podczas przetwarzania zadania {task_id}: {e}")

            try:
                await self.state_manager.update_status(
                    task_id, TaskStatus.FAILED, result=f"Błąd: {str(e)}"
                )
                self.state_manager.add_log(
                    task_id,
                    f"Błąd przetwarzania: {str(e)} - {datetime.now().isoformat()}",
                )
            except Exception as log_error:
                logger.error(
                    f"Nie udało się zapisać błędu zadania {task_id}: {log_error}"
                )
