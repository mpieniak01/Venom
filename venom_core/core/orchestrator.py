"""Moduł: orchestrator - orkiestracja zadań w tle."""

import asyncio
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from venom_core.config import SETTINGS
from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.flows.code_review import CodeReviewLoop
from venom_core.core.flows.council import CouncilFlow
from venom_core.core.flows.forge import ForgeFlow
from venom_core.core.goal_store import GoalStatus
from venom_core.core.intent_manager import IntentManager
from venom_core.core.metrics import metrics_collector
from venom_core.core.models import TaskRequest, TaskResponse, TaskStatus
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer, TraceStatus
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.perception.eyes import Eyes
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Ustawienia dla pętli meta-uczenia
ENABLE_META_LEARNING = True  # Flaga do włączania/wyłączania meta-uczenia
MAX_LESSONS_IN_CONTEXT = 3  # Maksymalna liczba lekcji dołączanych do promptu


class Orchestrator:
    """Orkiestrator zadań - zarządzanie wykonywaniem zadań w tle."""

    def __init__(
        self,
        state_manager: StateManager,
        intent_manager: IntentManager = None,
        task_dispatcher: TaskDispatcher = None,
        event_broadcaster=None,
        lessons_store=None,
        node_manager=None,
        request_tracer: RequestTracer = None,
    ):
        """
        Inicjalizacja Orchestrator.

        Args:
            state_manager: Menedżer stanu zadań
            intent_manager: Opcjonalny menedżer klasyfikacji intencji (jeśli None, zostanie utworzony)
            task_dispatcher: Opcjonalny dispatcher zadań (jeśli None, zostanie utworzony)
            event_broadcaster: Opcjonalny broadcaster zdarzeń do WebSocket
            lessons_store: Opcjonalny magazyn lekcji (dla meta-uczenia)
            node_manager: Opcjonalny menedżer węzłów (dla distributed execution)
            request_tracer: Opcjonalny tracer do śledzenia przepływu zadań
        """
        self.state_manager = state_manager
        self.intent_manager = intent_manager or IntentManager()
        self.event_broadcaster = event_broadcaster
        self.lessons_store = lessons_store  # Magazyn lekcji dla meta-uczenia
        self.node_manager = node_manager  # Menedżer węzłów dla distributed execution
        self.request_tracer = request_tracer  # Tracer do śledzenia przepływu

        # Inicjalizuj dispatcher jeśli nie został przekazany
        if task_dispatcher is None:
            kernel_builder = KernelBuilder()
            kernel = kernel_builder.build_kernel()
            task_dispatcher = TaskDispatcher(
                kernel, event_broadcaster=event_broadcaster, node_manager=node_manager
            )

        self.task_dispatcher = task_dispatcher

        # Inicjalizuj Eyes dla obsługi obrazów
        self.eyes = Eyes()

        # Inicjalizuj flows (delegowane logiki biznesowe)
        self._code_review_loop = None
        self._council_flow = None
        self._forge_flow = None

        # Tracking ostatniej aktywności dla idle mode
        self.last_activity: Optional[datetime] = None

        # Queue Governance (Dashboard v2.3)
        self.is_paused: bool = False  # Globalna pauza dla kolejki
        self.active_tasks: Dict[UUID, asyncio.Task] = {}  # Tracking aktywnych zadań
        self._queue_lock = asyncio.Lock()  # Lock dla operacji kolejki

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

    async def submit_task(self, request: TaskRequest) -> TaskResponse:
        """
        Przyjmuje nowe zadanie do wykonania.

        Args:
            request: Żądanie z treścią zadania

        Returns:
            Odpowiedź z ID zadania i statusem
        """
        # Zaktualizuj czas ostatniej aktywności
        self.last_activity = datetime.now()

        # Utwórz zadanie przez StateManager
        task = self.state_manager.create_task(content=request.content)

        # Utwórz trace dla zadania jeśli tracer jest dostępny
        if self.request_tracer:
            self.request_tracer.create_trace(task.id, request.content)
            self.request_tracer.add_step(
                task.id,
                "User",
                "submit_request",
                status="ok",
                details="Request received",
            )

        # Zaloguj event
        log_message = f"Zadanie uruchomione: {datetime.now().isoformat()}"
        self.state_manager.add_log(task.id, log_message)

        # Broadcast zdarzenia utworzenia zadania
        await self._broadcast_event(
            event_type="TASK_CREATED",
            message=f"Utworzono nowe zadanie: {request.content[:100]}...",
            data={"task_id": str(task.id), "content": request.content},
        )

        # Zapisz obrazy w kontekście zadania jeśli istnieją
        if request.images:
            self.state_manager.add_log(
                task.id, f"Zadanie zawiera {len(request.images)} obrazów"
            )

        # Sprawdź czy system jest w trybie pauzy
        if self.is_paused:
            self.state_manager.add_log(
                task.id, "⏸️ System w trybie pauzy - zadanie czeka w kolejce"
            )
            await self._broadcast_event(
                event_type="TASK_QUEUED",
                message=f"Zadanie {task.id} oczekuje - system wstrzymany",
                data={"task_id": str(task.id)},
            )
            logger.info(f"Zadanie {task.id} zakolejkowane - system w pauzie")
            return TaskResponse(task_id=task.id, status=task.status)

        # Sprawdź limit współbieżności
        if SETTINGS.ENABLE_QUEUE_LIMITS:
            async with self._queue_lock:
                active_count = len(self.active_tasks)
                if active_count >= SETTINGS.MAX_CONCURRENT_TASKS:
                    self.state_manager.add_log(
                        task.id,
                        f"⏳ Osiągnięto limit współbieżności ({active_count}/{SETTINGS.MAX_CONCURRENT_TASKS}) - zadanie czeka",
                    )
                    await self._broadcast_event(
                        event_type="TASK_QUEUED",
                        message=f"Zadanie {task.id} oczekuje - limit zadań równoległych",
                        data={
                            "task_id": str(task.id),
                            "active": active_count,
                            "limit": SETTINGS.MAX_CONCURRENT_TASKS,
                        },
                    )
                    logger.info(
                        f"Zadanie {task.id} czeka - limit współbieżności ({active_count}/{SETTINGS.MAX_CONCURRENT_TASKS})"
                    )
                    # Zadanie czeka - uruchom w tle ale będzie oczekiwać
                    asyncio.create_task(self._run_task_with_queue(task.id, request))
                    return TaskResponse(task_id=task.id, status=task.status)

        # Uruchom zadanie w tle (przekaż request zamiast tylko ID)
        asyncio.create_task(self._run_task_with_queue(task.id, request))

        logger.info(f"Zadanie {task.id} przyjęte do wykonania")

        return TaskResponse(task_id=task.id, status=task.status)

    async def _run_task_with_queue(self, task_id: UUID, request: TaskRequest) -> None:
        """
        Wrapper dla _run_task z obsługą kolejki i limitów współbieżności.

        Args:
            task_id: ID zadania do wykonania
            request: Oryginalne żądanie
        """
        # Czekaj na dostępny slot jeśli potrzeba
        while True:
            # Sprawdź pauzę i limit atomowo pod lockiem
            async with self._queue_lock:
                # Sprawdź pauzę
                if self.is_paused:
                    # Pauza aktywna, zwolnij lock i czekaj
                    pass
                else:
                    # Sprawdź limit
                    active_count = len(self.active_tasks)
                    if (
                        not SETTINGS.ENABLE_QUEUE_LIMITS
                        or active_count < SETTINGS.MAX_CONCURRENT_TASKS
                    ):
                        # Utwórz task handle
                        task_handle = asyncio.current_task()
                        if task_handle is None:
                            logger.error(f"Nie można uzyskać task handle dla {task_id}")
                            # Oznacz zadanie jako FAILED aby nie pozostało w PENDING
                            await self.state_manager.update_status(
                                task_id,
                                TaskStatus.FAILED,
                                result="Błąd systemu: nie można uzyskać task handle",
                            )
                            return
                        self.active_tasks[task_id] = task_handle
                        break

            # Czekaj na zwolnienie slotu lub zakończenie pauzy
            await asyncio.sleep(0.5)

        try:
            # Wykonaj zadanie
            await self._run_task(task_id, request)
        finally:
            # Usuń z active tasks
            async with self._queue_lock:
                self.active_tasks.pop(task_id, None)

    async def pause_queue(self) -> dict:
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

    async def resume_queue(self) -> dict:
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

    async def purge_queue(self) -> dict:
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
        purge_result = await self.purge_queue()

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

    def get_queue_status(self) -> dict:
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

    def get_token_economist(self):
        """
        Zwraca instancję TokenEconomist z task_dispatcher.

        Returns:
            TokenEconomist lub None jeśli nie jest dostępny

        Raises:
            NotImplementedError: Funkcja nie jest jeszcze w pełni zaimplementowana
        """
        raise NotImplementedError(
            "get_token_economist niezaimplementowane - dodać getter w KernelBuilder"
        )

    def _should_store_lesson(self, request: TaskRequest) -> bool:
        """
        Sprawdza czy należy zapisać lekcję dla danego zadania.

        Args:
            request: Oryginalne żądanie zadania

        Returns:
            True jeśli lekcja powinna być zapisana
        """
        return request.store_knowledge and ENABLE_META_LEARNING

    async def _run_task(self, task_id: UUID, request: TaskRequest) -> None:
        """
        Wykonuje zadanie w tle.

        Args:
            task_id: ID zadania do wykonania
            request: Oryginalne żądanie (z obrazami jeśli są)
        """
        # Inicjalizuj zmienne dla error handling
        context = request.content
        intent = "UNKNOWN"
        result = ""

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

            # Aktualizuj tracer
            if self.request_tracer:
                self.request_tracer.update_status(task_id, TraceStatus.PROCESSING)
                self.request_tracer.add_step(
                    task_id, "Orchestrator", "start_processing", status="ok"
                )

            # Broadcast rozpoczęcia zadania
            await self._broadcast_event(
                event_type="TASK_STARTED",
                message=f"Rozpoczynam przetwarzanie zadania {task_id}",
                data={"task_id": str(task_id)},
            )

            logger.info(f"Rozpoczynam przetwarzanie zadania {task_id}")

            # Przygotuj kontekst (treść + analiza obrazów jeśli są)
            context = await self._prepare_context(task_id, request)

            # PRE-FLIGHT CHECK: Sprawdź czy są lekcje z przeszłości
            context = await self._add_lessons_to_context(task_id, context)

            # Klasyfikuj intencję użytkownika
            intent = await self.intent_manager.classify_intent(context)

            # Zaloguj sklasyfikowaną intencję
            self.state_manager.add_log(
                task_id,
                f"Sklasyfikowana intencja: {intent} - {datetime.now().isoformat()}",
            )

            # Dodaj krok do tracera
            if self.request_tracer:
                self.request_tracer.add_step(
                    task_id,
                    "Orchestrator",
                    "classify_intent",
                    status="ok",
                    details=f"Intent: {intent}",
                )

            # Broadcast intencji
            await self._broadcast_event(
                event_type="AGENT_THOUGHT",
                message=f"Rozpoznano intencję: {intent}",
                data={"task_id": str(task_id), "intent": intent},
            )

            # SPECJALNE PRZYPADKI: START_CAMPAIGN
            if intent == "START_CAMPAIGN":
                # Uruchom tryb kampanii
                self.state_manager.add_log(
                    task_id, "🚀 Uruchamiam Tryb Kampanii (Campaign Mode)"
                )
                # Decision Gate: START_CAMPAIGN
                if self.request_tracer:
                    self.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "route_campaign",
                        status="ok",
                        details="🚀 Routing to Campaign Mode",
                    )
                campaign_result = await self.execute_campaign_mode(
                    goal_store=self.task_dispatcher.goal_store
                )
                result = campaign_result.get("summary", str(campaign_result))

            # SPECJALNE PRZYPADKI: HELP_REQUEST
            elif intent == "HELP_REQUEST":
                # Wygeneruj dynamiczną odpowiedź pomocy
                self.state_manager.add_log(task_id, "❓ Generuję informacje pomocy")
                # Decision Gate: HELP_REQUEST
                if self.request_tracer:
                    self.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "route_help",
                        status="ok",
                        details="❓ Routing to Help System",
                    )
                result = await self._generate_help_response(task_id)

            # DECYZJA: Council mode vs Standard mode
            elif self._should_use_council(context, intent):
                # Tryb Council - autonomiczna dyskusja agentów
                self.state_manager.add_log(
                    task_id,
                    "🏛️ Zadanie wymaga współpracy - aktywuję The Council",
                )
                # Decision Gate: Council mode
                if self.request_tracer:
                    self.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "select_council_mode",
                        status="ok",
                        details=f"🏛️ Complex task detected (intent={intent}) -> Council Mode",
                    )
                result = await self.run_council(task_id, context)
            elif intent == "CODE_GENERATION":
                # Standardowy tryb - pętla Coder-Critic
                # Decision Gate: Code Generation with Review Loop
                if self.request_tracer:
                    self.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "select_code_review_loop",
                        status="ok",
                        details="💻 Routing to Coder-Critic Review Loop",
                    )
                result = await self._code_generation_with_review(task_id, context)
            elif intent == "COMPLEX_PLANNING":
                # Standardowy tryb - delegacja do Architekta
                self.state_manager.add_log(
                    task_id,
                    "Zadanie sklasyfikowane jako COMPLEX_PLANNING - delegacja do Architekta",
                )
                # Decision Gate: Complex Planning -> Architect
                if self.request_tracer:
                    self.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "route_to_architect",
                        status="ok",
                        details="🏗️ Routing to Architect for Complex Planning",
                    )
                await self._broadcast_event(
                    event_type="AGENT_ACTION",
                    message="Przekazuję zadanie do Architekta (Complex Planning)",
                    agent="Architect",
                    data={"task_id": str(task_id)},
                )
                result = await self.task_dispatcher.dispatch(intent, context)
            else:
                # Dla pozostałych intencji (RESEARCH, GENERAL_CHAT, KNOWLEDGE_SEARCH, itp.) - standardowy przepływ
                # Decision Gate: Standard dispatch
                if self.request_tracer:
                    agent = self.task_dispatcher.agent_map.get(intent)
                    agent_name = agent.__class__.__name__ if agent else "UnknownAgent"
                    self.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "route_to_agent",
                        status="ok",
                        details=f"📤 Routing to {agent_name} (intent={intent})",
                    )
                result = await self.task_dispatcher.dispatch(intent, context)

            # Zaloguj które agent przejął zadanie
            agent = self.task_dispatcher.agent_map.get(intent)
            if agent is not None:
                agent_name = agent.__class__.__name__
                self.state_manager.add_log(
                    task_id,
                    f"Agent {agent_name} przetworzył zadanie - {datetime.now().isoformat()}",
                )
                # Dodaj krok do tracera
                if self.request_tracer:
                    self.request_tracer.add_step(
                        task_id,
                        agent_name,
                        "process_task",
                        status="ok",
                        details="Task processed successfully",
                    )
                # Inkrementuj licznik użycia agenta
                if metrics_collector:
                    metrics_collector.increment_agent_usage(agent_name)

                # Wyślij odpowiedź agenta do dashboardu (np. ChatAgent)
                formatted_result = ""
                if isinstance(result, (dict, list)):
                    import json

                    try:
                        formatted_result = json.dumps(
                            result, ensure_ascii=False, indent=2
                        )
                    except Exception:
                        formatted_result = str(result)
                else:
                    formatted_result = str(result)

                if formatted_result.strip():
                    await self._broadcast_event(
                        event_type="AGENT_ACTION",
                        message=formatted_result,
                        agent=agent_name,
                        data={
                            "task_id": str(task_id),
                            "intent": intent,
                        },
                    )
            else:
                logger.error(
                    f"Nie znaleziono agenta dla intencji '{intent}' podczas logowania zadania {task_id}"
                )

            # Ustaw status COMPLETED i wynik
            await self.state_manager.update_status(
                task_id, TaskStatus.COMPLETED, result=result
            )
            self.state_manager.add_log(
                task_id, f"Zakończono przetwarzanie: {datetime.now().isoformat()}"
            )

            # Aktualizuj tracer
            if self.request_tracer:
                self.request_tracer.update_status(task_id, TraceStatus.COMPLETED)
                self.request_tracer.add_step(
                    task_id, "System", "complete", status="ok", details="Response sent"
                )

            # REFLEKSJA: Zapisz lekcję o sukcesie (jeśli meta-uczenie włączone i store_knowledge=True)
            if self._should_store_lesson(request):
                await self._save_task_lesson(
                    task_id=task_id,
                    context=context,
                    intent=intent,
                    result=result,
                    success=True,
                )
            else:
                logger.info(
                    f"Skipping lesson save for task {task_id} (Knowledge Storage Disabled)"
                )

            # Inkrementuj licznik ukończonych zadań
            if metrics_collector:
                metrics_collector.increment_task_completed()

            # Broadcast ukończenia zadania
            await self._broadcast_event(
                event_type="TASK_COMPLETED",
                message=f"Zadanie {task_id} zakończone sukcesem",
                data={"task_id": str(task_id), "result_length": len(result)},
            )

            logger.info(f"Zadanie {task_id} zakończone sukcesem")

        except Exception as e:
            # Obsługa błędów - ustaw status FAILED
            logger.error(f"Błąd podczas przetwarzania zadania {task_id}: {e}")

            # Aktualizuj tracer
            if self.request_tracer:
                self.request_tracer.update_status(task_id, TraceStatus.FAILED)
                self.request_tracer.add_step(
                    task_id,
                    "System",
                    "error",
                    status="error",
                    details=f"Error: {str(e)}",
                )

            # REFLEKSJA: Zapisz lekcję o błędzie (jeśli meta-uczenie włączone i store_knowledge=True)
            if self._should_store_lesson(request):
                await self._save_task_lesson(
                    task_id=task_id,
                    context=context,
                    intent=intent,
                    result=f"Błąd: {str(e)}",
                    success=False,
                    error=str(e),
                )
            else:
                logger.info(
                    f"Skipping lesson save for task {task_id} (Knowledge Storage Disabled)"
                )

            # Inkrementuj licznik nieudanych zadań
            if metrics_collector:
                metrics_collector.increment_task_failed()

            # Broadcast błędu
            await self._broadcast_event(
                event_type="TASK_FAILED",
                message=f"Zadanie {task_id} nie powiodło się: {str(e)}",
                data={"task_id": str(task_id), "error": str(e)},
            )

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

    async def _prepare_context(self, task_id: UUID, request: TaskRequest) -> str:
        """
        Przygotowuje kontekst zadania (treść + analiza obrazów).

        Args:
            task_id: ID zadania
            request: Żądanie z treścią i opcjonalnymi obrazami

        Returns:
            Pełny kontekst do przetworzenia
        """
        context = request.content

        # Jeśli są obrazy, przeanalizuj je
        if request.images:
            self.state_manager.add_log(
                task_id, f"Analizuję {len(request.images)} obrazów..."
            )

            for i, image in enumerate(request.images, 1):
                try:
                    description = await self.eyes.analyze_image(
                        image,
                        prompt="Opisz szczegółowo co widzisz na tym obrazie, szczególnie zwróć uwagę na tekst, błędy lub problemy.",
                    )
                    context += f"\n\n[OBRAZ {i}]: {description}"
                    self.state_manager.add_log(
                        task_id, f"Obraz {i} przeanalizowany pomyślnie"
                    )
                except Exception as e:
                    logger.error(f"Błąd podczas analizy obrazu {i}: {e}")
                    self.state_manager.add_log(
                        task_id, f"Nie udało się przeanalizować obrazu {i}: {e}"
                    )

        return context

    async def _code_generation_with_review(
        self, task_id: UUID, user_request: str
    ) -> str:
        """
        Pętla generowania kodu z oceną przez CriticAgent.

        Args:
            task_id: ID zadania
            user_request: Żądanie użytkownika

        Returns:
            Zaakceptowany kod lub kod po naprawach
        """
        # Lazy init CodeReviewLoop
        if self._code_review_loop is None:
            self._code_review_loop = CodeReviewLoop(
                state_manager=self.state_manager,
                coder_agent=self.task_dispatcher.coder_agent,
                critic_agent=self.task_dispatcher.critic_agent,
            )

        # Deleguj do CodeReviewLoop
        return await self._code_review_loop.execute(task_id, user_request)

    async def _add_lessons_to_context(self, task_id: UUID, context: str) -> str:
        """
        Pre-flight check: Dodaje relevantne lekcje z przeszłości do kontekstu.

        Args:
            task_id: ID zadania
            context: Oryginalny kontekst

        Returns:
            Kontekst wzbogacony o lekcje
        """
        if not ENABLE_META_LEARNING or not self.lessons_store:
            return context

        try:
            # Wyszukaj relevantne lekcje
            lessons = self.lessons_store.search_lessons(
                query=context[:500],  # Użyj fragmentu kontekstu do wyszukania
                limit=MAX_LESSONS_IN_CONTEXT,
            )

            if not lessons:
                logger.debug("Brak relevantnych lekcji dla tego zadania")
                return context

            # Sformatuj lekcje do dołączenia
            lessons_text = "\n\n📚 LEKCJE Z PRZESZŁOŚCI (Nauczyłem się wcześniej):\n"
            for i, lesson in enumerate(lessons, 1):
                lessons_text += f"\n[Lekcja {i}]\n"
                lessons_text += f"Sytuacja: {lesson.situation}\n"
                lessons_text += f"Co poszło nie tak: {lesson.result}\n"
                lessons_text += f"Wniosek: {lesson.feedback}\n"

            self.state_manager.add_log(
                task_id, f"Dołączono {len(lessons)} lekcji z przeszłości do kontekstu"
            )

            # Broadcast informacji o lekcjach
            await self._broadcast_event(
                event_type="AGENT_THOUGHT",
                message=f"Znalazłem {len(lessons)} relevantnych lekcji z przeszłości",
                data={"task_id": str(task_id), "lessons_count": len(lessons)},
            )

            # Dołącz lekcje na początku kontekstu
            return lessons_text + "\n\n" + context

        except Exception as e:
            logger.warning(f"Błąd podczas dodawania lekcji do kontekstu: {e}")
            return context

    async def _save_task_lesson(
        self,
        task_id: UUID,
        context: str,
        intent: str,
        result: str,
        success: bool,
        error: str = None,
    ) -> None:
        """
        Zapisuje lekcję z wykonanego zadania (refleksja).

        Args:
            task_id: ID zadania
            context: Kontekst zadania
            intent: Sklasyfikowana intencja
            result: Rezultat zadania
            success: Czy zadanie zakończyło się sukcesem
            error: Opcjonalny opis błędu
        """
        if not ENABLE_META_LEARNING or not self.lessons_store:
            return

        try:
            # Przygotuj dane lekcji
            situation = f"[{intent}] {context[:200]}..."  # Skrócony opis sytuacji

            if success:
                # Lekcja o sukcesie - zapisuj tylko jeśli coś ciekawego
                # (np. jeśli było więcej niż 1 próba w Coder-Critic)
                task_logs = self.state_manager.get_task(task_id)
                if task_logs and len(task_logs.logs) > 5:
                    # Było dużo iteracji, warto zapisać
                    action = (
                        f"Zadanie wykonane pomyślnie po {len(task_logs.logs)} krokach"
                    )
                    lesson_result = "SUKCES"
                    feedback = f"Zadanie typu {intent} wymaga dokładnego planowania. Wynik: {result[:100]}..."
                    tags = [intent, "sukces", "nauka"]
                else:
                    # Proste zadanie, nie ma co zapisywać
                    logger.debug("Proste zadanie, pomijam zapis lekcji")
                    return
            else:
                # Lekcja o błędzie - zawsze zapisuj
                action = f"Próba wykonania zadania typu {intent}"
                error_msg = error if error else "Unknown error"
                lesson_result = f"BŁĄD: {error_msg[:200]}"
                feedback = f"Unikaj powtórzenia tego błędu. Błąd: {error_msg[:300]}"
                tags = [intent, "błąd", "ostrzeżenie"]

            # Zapisz lekcję
            lesson = self.lessons_store.add_lesson(
                situation=situation,
                action=action,
                result=lesson_result,
                feedback=feedback,
                tags=tags,
                metadata={
                    "task_id": str(task_id),
                    "timestamp": datetime.now().isoformat(),
                },
            )

            self.state_manager.add_log(
                task_id, f"💡 Zapisano lekcję: {lesson.lesson_id}"
            )

            # Broadcast informacji o nowej lekcji
            await self._broadcast_event(
                event_type="LESSON_LEARNED",
                message=f"Nauczyłem się czegoś nowego: {feedback[:100]}",
                data={
                    "task_id": str(task_id),
                    "lesson_id": lesson.lesson_id,
                    "success": success,
                },
            )

            logger.info(f"Zapisano lekcję z zadania {task_id}: {lesson.lesson_id}")

        except Exception as e:
            logger.error(f"Błąd podczas zapisywania lekcji: {e}")

    def _should_use_council(self, context: str, intent: str) -> bool:
        """
        Decyduje czy użyć trybu Council dla danego zadania.

        Args:
            context: Kontekst zadania
            intent: Sklasyfikowana intencja

        Returns:
            True jeśli należy użyć Council, False dla standardowego flow
        """
        # Lazy init CouncilFlow
        if self._council_flow is None:
            self._council_flow = CouncilFlow(
                state_manager=self.state_manager,
                task_dispatcher=self.task_dispatcher,
                event_broadcaster=self.event_broadcaster,
            )

        # Deleguj decyzję do CouncilFlow
        return self._council_flow.should_use_council(context, intent)

    async def run_council(self, task_id: UUID, context: str) -> str:
        """
        Uruchamia tryb Council (AutoGen Group Chat) dla złożonych zadań.

        W tym trybie agenci prowadzą autonomiczną dyskusję:
        - Architect planuje
        - Coder implementuje
        - Critic sprawdza
        - Guardian weryfikuje testy

        Args:
            task_id: ID zadania
            context: Kontekst zadania

        Returns:
            Wynik dyskusji Council
        """
        # Lazy init CouncilFlow
        if self._council_flow is None:
            self._council_flow = CouncilFlow(
                state_manager=self.state_manager,
                task_dispatcher=self.task_dispatcher,
                event_broadcaster=self.event_broadcaster,
            )

        # Deleguj do CouncilFlow
        return await self._council_flow.run(task_id, context)

    async def execute_healing_cycle(self, task_id: UUID, test_path: str = ".") -> dict:
        """
        Pętla samonaprawy (Test-Diagnose-Fix-Apply).

        Algorytm:
        1. CHECK: Uruchom testy
        2. DIAGNOSE: Przeanalizuj błędy (Guardian)
        3. FIX: Wygeneruj poprawkę (Coder)
        4. APPLY: Zapisz poprawkę (FileSkill)
        5. LOOP: Wróć do punktu 1 (max 3 iteracje)

        Args:
            task_id: ID zadania
            test_path: Ścieżka do testów

        Returns:
            Słownik z wynikami:
            - success: bool - czy testy przeszły
            - iterations: int - liczba iteracji
            - final_report: str - ostatni raport z testów
        """
        from venom_core.agents.guardian import GuardianAgent
        from venom_core.execution.skills.test_skill import TestSkill
        from venom_core.infrastructure.docker_habitat import DockerHabitat

        MAX_HEALING_ITERATIONS = 3

        try:
            # Inicjalizuj komponenty
            habitat = DockerHabitat()
            test_skill = TestSkill(habitat=habitat)

            # Pobierz agentów
            guardian = GuardianAgent(
                kernel=self.task_dispatcher.kernel, test_skill=test_skill
            )
            coder = self.task_dispatcher.coder_agent

            self.state_manager.add_log(
                task_id,
                f"🔄 Rozpoczynam pętlę samonaprawy (max {MAX_HEALING_ITERATIONS} iteracji)",
            )

            await self._broadcast_event(
                event_type="HEALING_STARTED",
                message="Rozpoczynam automatyczne testy i naprawy",
                data={
                    "task_id": str(task_id),
                    "max_iterations": MAX_HEALING_ITERATIONS,
                },
            )

            # Przygotuj środowisko - zainstaluj zależności
            self.state_manager.add_log(task_id, "📦 Przygotowuję środowisko testowe...")
            exit_code, output = habitat.execute(
                "pip install -r requirements.txt 2>&1 || echo 'No requirements.txt'",
                timeout=120,
            )

            iteration = 0
            last_test_report = ""

            while iteration < MAX_HEALING_ITERATIONS:
                iteration += 1

                # PHASE 1: CHECK - Uruchom testy
                self.state_manager.add_log(
                    task_id,
                    f"🔍 Iteracja {iteration}/{MAX_HEALING_ITERATIONS} - PHASE 1: Uruchamiam testy",
                )

                await self._broadcast_event(
                    event_type="TEST_RUNNING",
                    message=f"Próba {iteration}/{MAX_HEALING_ITERATIONS}: Uruchamiam testy",
                    agent="Guardian",
                    data={"task_id": str(task_id), "iteration": iteration},
                )

                test_report = await test_skill.run_pytest(
                    test_path=test_path, timeout=60
                )
                last_test_report = test_report

                # Sprawdź czy testy przeszły - używamy wielokrotnych sprawdzeń dla niezawodności
                test_passed = (
                    "PRZESZŁY POMYŚLNIE" in test_report
                    or "PASSED" in test_report.upper()
                    or (
                        "exit_code: 0" in test_report.lower()
                        and "failed: 0" in test_report.lower()
                    )
                )

                if test_passed:
                    self.state_manager.add_log(
                        task_id,
                        f"✅ Testy przeszły pomyślnie po {iteration} iteracji!",
                    )

                    await self._broadcast_event(
                        event_type="TEST_RESULT",
                        message="✅ Testy przeszły pomyślnie!",
                        agent="Guardian",
                        data={
                            "task_id": str(task_id),
                            "success": True,
                            "iterations": iteration,
                        },
                    )

                    return {
                        "success": True,
                        "iterations": iteration,
                        "final_report": test_report,
                    }

                # Testy nie przeszły - diagnozuj
                self.state_manager.add_log(
                    task_id, "❌ Testy nie przeszły. Rozpoczynam diagnostykę..."
                )

                await self._broadcast_event(
                    event_type="TEST_RESULT",
                    message="❌ Testy nie przeszły - analizuję błędy",
                    agent="Guardian",
                    data={
                        "task_id": str(task_id),
                        "success": False,
                        "iteration": iteration,
                    },
                )

                # PHASE 2: DIAGNOSE - Guardian analizuje błędy
                self.state_manager.add_log(
                    task_id,
                    "🔬 PHASE 2: Guardian analizuje błędy (traceback)",
                )

                diagnosis_prompt = f"""Przeanalizuj wyniki testów i stwórz precyzyjny ticket naprawczy.

WYNIKI TESTÓW:
{test_report}

Zidentyfikuj:
1. Który plik wymaga naprawy
2. Jaka jest przyczyna błędu
3. Co dokładnie trzeba poprawić

Odpowiedz w formacie ticketu naprawczego.
"""

                repair_ticket = await guardian.process(diagnosis_prompt)

                self.state_manager.add_log(
                    task_id,
                    f"📋 Ticket naprawczy:\n{repair_ticket[:300]}...",
                )

                await self._broadcast_event(
                    event_type="AGENT_THOUGHT",
                    message="Zdiagnozowałem problem - tworzę ticket naprawczy",
                    agent="Guardian",
                    data={
                        "task_id": str(task_id),
                        "ticket_preview": repair_ticket[:100],
                    },
                )

                # PHASE 3: FIX - Coder generuje poprawkę
                self.state_manager.add_log(
                    task_id,
                    "🛠️ PHASE 3: Coder generuje poprawkę",
                )

                fix_prompt = f"""TICKET NAPRAWCZY OD GUARDIANA:
{repair_ticket}

WYNIKI TESTÓW:
{test_report[:500]}

Twoim zadaniem jest naprawić kod zgodnie z ticketem.
WAŻNE: Użyj funkcji write_file aby zapisać poprawiony kod do pliku.
"""

                await self._broadcast_event(
                    event_type="AGENT_ACTION",
                    message="Coder naprawia kod",
                    agent="Coder",
                    data={"task_id": str(task_id), "iteration": iteration},
                )

                fix_result = await coder.process(fix_prompt)

                self.state_manager.add_log(
                    task_id,
                    f"✏️ Coder zastosował poprawkę: {fix_result[:200]}...",
                )

                # PHASE 4 jest zintegrowana - Coder powinien użyć write_file
                # Zapisanie odbywa się automatycznie przez funkcje kernela

                self.state_manager.add_log(
                    task_id,
                    "💾 PHASE 4: Poprawka zastosowana, wracam do testów",
                )

                # Jeśli to ostatnia iteracja
                if iteration >= MAX_HEALING_ITERATIONS:
                    self.state_manager.add_log(
                        task_id,
                        f"⚠️ Osiągnięto limit iteracji ({MAX_HEALING_ITERATIONS}). Testy nadal nie przechodzą.",
                    )

                    await self._broadcast_event(
                        event_type="HEALING_FAILED",
                        message=f"Nie udało się naprawić kodu w {MAX_HEALING_ITERATIONS} iteracjach",
                        data={
                            "task_id": str(task_id),
                            "iterations": iteration,
                            "final_report": last_test_report[:500],
                        },
                    )

                    return {
                        "success": False,
                        "iterations": iteration,
                        "final_report": last_test_report,
                        "message": f"⚠️ FAIL FAST: Nie udało się naprawić kodu po {MAX_HEALING_ITERATIONS} próbach. Wymagana interwencja ręczna.",
                    }

            # Nie powinno się tu dostać, ale dla bezpieczeństwa
            return {
                "success": False,
                "iterations": iteration,
                "final_report": last_test_report,
                "message": "Nieoczekiwane zakończenie pętli naprawczej",
            }

        except Exception as e:
            error_msg = f"❌ Błąd podczas pętli samonaprawy: {str(e)}"
            logger.error(error_msg)
            self.state_manager.add_log(task_id, error_msg)

            await self._broadcast_event(
                event_type="HEALING_ERROR",
                message=error_msg,
                data={"task_id": str(task_id), "error": str(e)},
            )

            return {
                "success": False,
                "iterations": 0,
                "final_report": "",
                "message": error_msg,
            }

    async def execute_forge_workflow(
        self, task_id: UUID, tool_specification: str, tool_name: str
    ) -> dict:
        """
        Wykonuje workflow "The Forge" - tworzenie nowego narzędzia.

        Algorytm:
        1. CRAFT: Toolmaker generuje kod narzędzia
        2. TEST: Toolmaker generuje test jednostkowy
        3. VERIFY: Guardian testuje narzędzie w Dockerze
        4. LOAD: SkillManager ładuje narzędzie do Kernela

        Args:
            task_id: ID zadania
            tool_specification: Specyfikacja narzędzia (co ma robić)
            tool_name: Nazwa narzędzia (snake_case, bez .py)

        Returns:
            Słownik z wynikami:
            - success: bool - czy narzędzie zostało stworzone i załadowane
            - tool_name: str - nazwa narzędzia
            - message: str - opis wyniku
            - code: str - wygenerowany kod (jeśli sukces)
        """
        # Lazy init ForgeFlow
        if self._forge_flow is None:
            self._forge_flow = ForgeFlow(
                state_manager=self.state_manager,
                task_dispatcher=self.task_dispatcher,
                event_broadcaster=self.event_broadcaster,
            )

        # Deleguj do ForgeFlow
        return await self._forge_flow.execute(task_id, tool_specification, tool_name)

    async def handle_remote_issue(self, issue_number: int) -> dict:
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

            self.state_manager.add_log(task_id, "Pobieranie szczegółów Issue...")
            issue_details = await integrator.handle_issue(issue_number)

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
            commit_result = await integrator.process(commit_context)
            self.state_manager.add_log(task_id, f"Commit: {commit_result}")

            # Finalizuj Issue (PR + komentarz + powiadomienie)
            branch_name = f"issue-{issue_number}"
            pr_title = f"fix: resolve issue #{issue_number}"
            pr_body = (
                f"Automatyczna naprawa Issue #{issue_number}\n\n{fix_result[:500]}"
            )

            finalize_result = await integrator.finalize_issue(
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

    async def execute_campaign_mode(
        self, goal_store=None, max_iterations: int = 10
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
                task_response = await self.submit_task(task_request)

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

    async def _generate_help_response(self, task_id: UUID) -> str:
        """
        Generuje dynamiczną odpowiedź pomocy z informacjami o dostępnych umiejętnościach.

        Args:
            task_id: ID zadania

        Returns:
            Sformatowana odpowiedź pomocy w formacie Markdown
        """
        try:
            # Pobierz informacje o dostępnych agentach z dispatcher
            agent_map = self.task_dispatcher.agent_map

            # Pobierz informacje o umiejętnościach z kernela
            kernel = self.task_dispatcher.kernel
            plugins = getattr(kernel, "plugins", None)

            # Buduj odpowiedź pomocy
            help_text = """# 🕷️ Venom - System Pomocy

## Dostępne Możliwości

Jestem Venom - wieloagentowy system AI wspierający rozwój oprogramowania. Oto co mogę dla Ciebie zrobić:

### 🤖 Dostępni Agenci

"""

            # Dodaj informacje o agentach
            agent_descriptions = {
                "CODE_GENERATION": "💻 **Coder** - Generowanie, refaktoryzacja i naprawa kodu",
                "RESEARCH": "🔍 **Researcher** - Wyszukiwanie aktualnych informacji w Internecie",
                "KNOWLEDGE_SEARCH": "📚 **Professor** - Odpowiedzi na pytania o wiedzę i technologie",
                "COMPLEX_PLANNING": "🏗️ **Architect** - Projektowanie złożonych systemów i aplikacji",
                "VERSION_CONTROL": "🌿 **Git Master** - Zarządzanie gałęziami, commitami i synchronizacją",
                "E2E_TESTING": "🧪 **Tester** - Testowanie aplikacji webowych end-to-end",
                "DOCUMENTATION": "📖 **Publisher** - Generowanie i publikacja dokumentacji",
                "RELEASE_PROJECT": "🚀 **Release Manager** - Zarządzanie wydaniami i changelog",
                "STATUS_REPORT": "📊 **Executive** - Raportowanie statusu i postępu projektu",
                "GENERAL_CHAT": "💬 **Assistant** - Ogólna konwersacja i wsparcie",
            }

            for intent, description in agent_descriptions.items():
                if intent in agent_map:
                    help_text += f"- {description}\n"

            # Dodaj informacje o trybach pracy
            help_text += """
### 🎯 Tryby Pracy

- **🏛️ The Council** - Autonomiczna współpraca agentów dla złożonych projektów
- **🚀 Tryb Kampanii** - Automatyczna realizacja roadmapy projektu
- **🔄 Pętla Samonaprawy** - Automatyczne testowanie i naprawianie kodu

### 🛠️ Umiejętności (Skills)

"""

            # Dodaj listę dostępnych pluginów
            if plugins is not None:
                skill_count = 0
                for plugin_name in plugins:
                    # Filtruj wewnętrzne pluginy
                    if self._is_public_plugin(plugin_name):
                        skill_count += 1
                        help_text += f"- **{plugin_name}**\n"

                if skill_count == 0:
                    help_text += "- Trwa ładowanie umiejętności...\n"
            else:
                help_text += "- Podstawowe umiejętności: manipulacja plikami, Git, shell, research, renderowanie\n"

            # Dodaj przykłady użycia
            help_text += """
### 💡 Przykłady Użycia

**Generowanie kodu:**
```
Napisz funkcję w Pythonie do sortowania listy
```

**Research:**
```
Znajdź najnowsze informacje o FastAPI 0.100
```

**Projekt aplikacji:**
```
Stwórz aplikację webową z FastAPI i React
```

**Git:**
```
Utwórz nowy branch feat/new-feature
```

**Dokumentacja:**
```
Wygeneruj dokumentację projektu
```

### ℹ️ Dodatkowe Informacje

- Wspieramy lokalne modele (Ollama) oraz API chmurowe (OpenAI, Azure)
- Automatyczne zarządzanie pamięcią i uczenie się z błędów
- Integracja z GitHub, Docker i systemami CI/CD
- Voice interface (gdy włączony)
- Distributed execution (tryb Nexus)

**Potrzebujesz pomocy?** Zapytaj o konkretną funkcjonalność lub wyślij zadanie do wykonania!
"""

            # Broadcast zdarzenia renderowania widgetu pomocy
            if self.event_broadcaster:
                await self._broadcast_event(
                    event_type="RENDER_WIDGET",
                    message="Wyświetlam system pomocy",
                    data={
                        "widget": {
                            "id": f"help-{task_id}",
                            "type": "markdown",
                            "data": {"content": help_text},
                        }
                    },
                )

            return help_text

        except Exception as e:
            logger.error(f"Błąd podczas generowania pomocy: {e}")
            return "Wystąpił błąd podczas generowania pomocy. Spróbuj ponownie lub skontaktuj się z administratorem."

    def _is_public_plugin(self, plugin_name: str) -> bool:
        """
        Sprawdza czy plugin jest publiczny (nie wewnętrzny).

        Args:
            plugin_name: Nazwa pluginu

        Returns:
            True jeśli plugin jest publiczny
        """
        # Filtruj wewnętrzne pluginy (zaczynające się od _ lub zawierające 'internal')
        return not (plugin_name.startswith("_") or "internal" in plugin_name.lower())
