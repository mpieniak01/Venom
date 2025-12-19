"""Moduł: orchestrator - orkiestracja zadań w tle."""

import asyncio
from datetime import datetime
from typing import Optional
from uuid import UUID

from venom_core.config import SETTINGS
from venom_core.core import metrics as metrics_module
from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.flows.campaign import CampaignFlow
from venom_core.core.flows.code_review import (
    MAX_REPAIR_ATTEMPTS as CODE_REVIEW_MAX_REPAIR_ATTEMPTS,
)
from venom_core.core.flows.code_review import CodeReviewLoop
from venom_core.core.flows.council import (
    COUNCIL_COLLABORATION_KEYWORDS as COUNCIL_KEYWORDS,
)
from venom_core.core.flows.council import COUNCIL_TASK_THRESHOLD as COUNCIL_THRESHOLD
from venom_core.core.flows.council import ENABLE_COUNCIL_MODE as COUNCIL_ENABLE_FLAG
from venom_core.core.flows.council import CouncilFlow
from venom_core.core.flows.forge import ForgeFlow
from venom_core.core.flows.healing import HealingFlow
from venom_core.core.flows.issue_handler import IssueHandlerFlow
from venom_core.core.intent_manager import IntentManager
from venom_core.core.models import TaskRequest, TaskResponse, TaskStatus
from venom_core.core.queue_manager import QueueManager
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer, TraceStatus
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.perception.eyes import Eyes
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Ustawienia dla pętli meta-uczenia
ENABLE_META_LEARNING = True  # Flaga do włączania/wyłączania meta-uczenia
MAX_LESSONS_IN_CONTEXT = 3  # Maksymalna liczba lekcji dołączanych do promptu
# Alias dla kompatybilności z testami i innymi modułami
MAX_REPAIR_ATTEMPTS = CODE_REVIEW_MAX_REPAIR_ATTEMPTS
COUNCIL_COLLABORATION_KEYWORDS = COUNCIL_KEYWORDS
COUNCIL_TASK_THRESHOLD = COUNCIL_THRESHOLD
ENABLE_COUNCIL_MODE = COUNCIL_ENABLE_FLAG


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
        self._council_config = None
        self._forge_flow = None
        self._campaign_flow = None
        self._healing_flow = None
        self._issue_handler_flow = None

        # Tracking ostatniej aktywności dla idle mode
        self.last_activity: Optional[datetime] = None

        # Queue Manager (Dashboard v2.3) - delegacja zarządzania kolejką
        self.queue_manager = QueueManager(
            state_manager=state_manager, event_broadcaster=event_broadcaster
        )

    @property
    def is_paused(self) -> bool:
        """Zwraca, czy kolejka jest wstrzymana (delegacja do queue_manager)."""
        return self.queue_manager.is_paused

    @property
    def active_tasks(self) -> dict:
        """Zwraca słownik aktywnych zadań (delegacja do queue_manager)."""
        return self.queue_manager.active_tasks

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

        runtime_info = get_active_llm_runtime()
        runtime_context = runtime_info.to_payload()
        runtime_context["status"] = "ready"
        self.state_manager.update_context(task.id, {"llm_runtime": runtime_context})

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
            self.request_tracer.set_llm_metadata(
                task.id, metadata=runtime_context.copy()
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
        if self.queue_manager.is_paused:
            self.state_manager.add_log(
                task.id, "⏸️ System w trybie pauzy - zadanie czeka w kolejce"
            )
            await self._broadcast_event(
                event_type="TASK_QUEUED",
                message=f"Zadanie {task.id} oczekuje - system wstrzymany",
                data={"task_id": str(task.id)},
            )
            logger.info(f"Zadanie {task.id} zakolejkowane - system w pauzie")
            return TaskResponse(
                task_id=task.id,
                status=task.status,
                llm_provider=runtime_info.provider,
                llm_model=runtime_info.model_name,
                llm_endpoint=runtime_info.endpoint,
            )

        # Sprawdź limit współbieżności
        if SETTINGS.ENABLE_QUEUE_LIMITS:
            has_capacity, active_count = await self.queue_manager.check_capacity()
            if not has_capacity:
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
                return TaskResponse(
                    task_id=task.id,
                    status=task.status,
                    llm_provider=runtime_info.provider,
                    llm_model=runtime_info.model_name,
                    llm_endpoint=runtime_info.endpoint,
                )

        # Uruchom zadanie w tle (przekaż request zamiast tylko ID)
        asyncio.create_task(self._run_task_with_queue(task.id, request))

        logger.info(f"Zadanie {task.id} przyjęte do wykonania")

        return TaskResponse(
            task_id=task.id,
            status=task.status,
            llm_provider=runtime_info.provider,
            llm_model=runtime_info.model_name,
            llm_endpoint=runtime_info.endpoint,
        )

    async def _run_task_with_queue(self, task_id: UUID, request: TaskRequest) -> None:
        """
        Wrapper dla _run_task z obsługą kolejki i limitów współbieżności.

        Args:
            task_id: ID zadania do wykonania
            request: Oryginalne żądanie
        """
        # Czekaj na dostępny slot jeśli potrzeba
        while True:
            # Sprawdź pauzę
            if self.queue_manager.is_paused:
                # Pauza aktywna, czekaj
                await asyncio.sleep(0.5)
                continue

            # Sprawdź limit
            has_capacity, _ = await self.queue_manager.check_capacity()
            if has_capacity:
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
                await self.queue_manager.register_task(task_id, task_handle)
                break

            # Czekaj na zwolnienie slotu
            await asyncio.sleep(0.5)

        try:
            # Wykonaj zadanie
            await self._run_task(task_id, request)
        finally:
            # Usuń z active tasks
            await self.queue_manager.unregister_task(task_id)

    async def pause_queue(self) -> dict:
        """
        Wstrzymuje przyjmowanie nowych zadań do wykonania.

        Returns:
            Dict z wynikiem operacji
        """
        return await self.queue_manager.pause()

    async def resume_queue(self) -> dict:
        """
        Wznawia przyjmowanie zadań.

        Returns:
            Dict z wynikiem operacji
        """
        return await self.queue_manager.resume()

    async def purge_queue(self) -> dict:
        """
        Usuwa wszystkie zadania o statusie PENDING z kolejki.

        Returns:
            Dict z wynikiem operacji (liczba usuniętych zadań)
        """
        return await self.queue_manager.purge()

    async def abort_task(self, task_id: UUID) -> dict:
        """
        Przerywa wykonywanie konkretnego zadania.

        Args:
            task_id: ID zadania do przerwania

        Returns:
            Dict z wynikiem operacji
        """
        return await self.queue_manager.abort_task(task_id)

    async def emergency_stop(self) -> dict:
        """
        Awaryjne zatrzymanie - przerywa wszystkie aktywne zadania i czyści kolejkę.

        Returns:
            Dict z wynikiem operacji
        """
        return await self.queue_manager.emergency_stop()

    def get_queue_status(self) -> dict:
        """
        Zwraca aktualny status kolejki zadań.

        Returns:
            Dict ze statusem kolejki
        """
        return self.queue_manager.get_status()

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

    NON_LEARNING_INTENTS = {
        "TIME_REQUEST",
        "INFRA_STATUS",
    }

    NON_LLM_INTENTS = {
        "TIME_REQUEST",
        "INFRA_STATUS",
        "UNSUPPORTED_TASK",
    }

    def _should_store_lesson(
        self,
        request: TaskRequest,
        intent: str = "",
        agent=None,
    ) -> bool:
        """
        Sprawdza czy należy zapisać lekcję dla danego zadania.

        Args:
            request: Oryginalne żądanie zadania

        Returns:
            True jeśli lekcja powinna być zapisana
        """
        if not (request.store_knowledge and ENABLE_META_LEARNING):
            return False

        if intent in self.NON_LEARNING_INTENTS:
            return False

        if agent and getattr(agent, "disable_learning", False):
            return False

        return True

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

            # Zapisz generation_params w kontekście zadania jeśli zostały przekazane
            if request.generation_params:
                self.state_manager.update_context(
                    task_id, {"generation_params": request.generation_params}
                )
                logger.info(
                    f"Zapisano parametry generacji dla zadania {task_id}: {request.generation_params}"
                )

            # Jeśli to zadanie testu wydajności, zakończ je natychmiast (bez LLM)
            if self._is_perf_test_prompt(context):
                await self._complete_perf_test_task(task_id)
                return

            # Klasyfikuj intencję użytkownika (bez domieszek z lekcji)
            intent = await self.intent_manager.classify_intent(context)
            intent_debug = getattr(self.intent_manager, "last_intent_debug", {})
            if intent_debug:
                self.state_manager.update_context(
                    task_id, {"intent_debug": intent_debug}
                )
                if self.request_tracer:
                    try:
                        import json

                        details = json.dumps(intent_debug, ensure_ascii=False)
                    except Exception:
                        details = str(intent_debug)
                    self.request_tracer.add_step(
                        task_id,
                        "DecisionGate",
                        "intent_debug",
                        status="ok",
                        details=details,
                    )

            if (
                self.request_tracer
                and intent in self.NON_LLM_INTENTS
                and intent_debug.get("source") != "llm"
            ):
                self.request_tracer.set_llm_metadata(
                    task_id, provider=None, model=None, endpoint=None
                )
                self.state_manager.update_context(
                    task_id,
                    {
                        "llm_runtime": {
                            "status": "skipped",
                            "error": None,
                            "last_success_at": None,
                        }
                    },
                )

            # PRE-FLIGHT CHECK: Sprawdź czy są lekcje z przeszłości (tylko gdy ma to sens)
            if intent not in self.NON_LEARNING_INTENTS:
                context = await self._add_lessons_to_context(task_id, context)

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
                # Lazy init CampaignFlow
                if self._campaign_flow is None:
                    self._campaign_flow = CampaignFlow(
                        state_manager=self.state_manager,
                        orchestrator_submit_task=self.submit_task,
                        event_broadcaster=self.event_broadcaster,
                    )
                campaign_result = await self._campaign_flow.execute(
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
                result = await self.task_dispatcher.dispatch(
                    intent, context, generation_params=request.generation_params
                )
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
                result = await self.task_dispatcher.dispatch(
                    intent, context, generation_params=request.generation_params
                )

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
                collector = metrics_module.metrics_collector
                if collector:
                    collector.increment_agent_usage(agent_name)

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
            self.state_manager.update_context(
                task_id,
                {
                    "llm_runtime": {
                        "status": "ready",
                        "error": None,
                        "last_success_at": datetime.now().isoformat(),
                    }
                },
            )

            # Aktualizuj tracer
            if self.request_tracer:
                self.request_tracer.update_status(task_id, TraceStatus.COMPLETED)
                self.request_tracer.add_step(
                    task_id, "System", "complete", status="ok", details="Response sent"
                )

            # REFLEKSJA: Zapisz lekcję o sukcesie (jeśli meta-uczenie włączone i store_knowledge=True)
            if self._should_store_lesson(request, intent=intent, agent=agent):
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
            collector = metrics_module.metrics_collector
            if collector:
                collector.increment_task_completed()

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
            self.state_manager.update_context(
                task_id,
                {
                    "llm_runtime": {
                        "status": "error",
                        "error": str(e),
                        "last_error_at": datetime.now().isoformat(),
                    }
                },
            )

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
            agent = self.task_dispatcher.agent_map.get(intent)
            if self._should_store_lesson(request, intent=intent, agent=agent):
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
            collector = metrics_module.metrics_collector
            if collector:
                collector.increment_task_failed()

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

    def _is_perf_test_prompt(self, content: str) -> bool:
        """Sprawdź, czy treść zadania pochodzi z testów wydajności."""
        keywords = getattr(IntentManager, "PERF_TEST_KEYWORDS", ())
        normalized = (content or "").lower()
        return any(keyword in normalized for keyword in keywords)

    async def _complete_perf_test_task(self, task_id: UUID) -> None:
        """Zakończ zadanie testu wydajności bez uruchamiania pełnego pipeline'u."""
        result_text = "✅ Backend perf pipeline OK"
        self.state_manager.add_log(
            task_id,
            "⚡ Wykryto prompt testu wydajności – pomijam kosztowne agentów i zamykam zadanie natychmiast.",
        )
        await self.state_manager.update_status(
            task_id, TaskStatus.COMPLETED, result=result_text
        )
        self.state_manager.add_log(
            task_id, f"Zakończono test wydajności: {datetime.now().isoformat()}"
        )

        if self.request_tracer:
            self.request_tracer.update_status(task_id, TraceStatus.COMPLETED)
            self.request_tracer.add_step(
                task_id,
                "System",
                "perf_test_shortcut",
                status="ok",
                details="Perf test zakończony bez agentów",
            )

        collector = metrics_module.metrics_collector
        if collector:
            collector.increment_task_completed()

        await self._broadcast_event(
            event_type="TASK_COMPLETED",
            message=f"Zadanie {task_id} zakończone (perf test)",
            data={"task_id": str(task_id), "result_length": len(result_text)},
        )

        logger.info(f"Zadanie {task_id} zakończone w trybie perf-test")

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
        coder = getattr(self.task_dispatcher, "coder_agent", None)
        critic = getattr(self.task_dispatcher, "critic_agent", None)

        if coder is None or critic is None:
            logger.warning(
                "TaskDispatcher nie ma zainicjalizowanych agentów coder/critic - używam prostego dispatch"
            )
            return await self.task_dispatcher.dispatch("CODE_GENERATION", user_request)

        # Lazy init CodeReviewLoop
        if self._code_review_loop is None:
            self._code_review_loop = CodeReviewLoop(
                state_manager=self.state_manager,
                coder_agent=coder,
                critic_agent=critic,
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
        self.state_manager.add_log(
            task_id, "🏛️ THE COUNCIL: Rozpoczynam tryb Group Chat (Swarm Intelligence)"
        )

        await self._broadcast_event(
            event_type="COUNCIL_STARTED",
            message="The Council rozpoczyna dyskusję nad zadaniem",
            data={"task_id": str(task_id)},
        )

        try:
            if self._council_config is None:
                from venom_core.agents.guardian import GuardianAgent
                from venom_core.core.council import (
                    CouncilConfig,
                    create_local_llm_config,
                )

                coder = getattr(self.task_dispatcher, "coder_agent", None)
                critic = getattr(self.task_dispatcher, "critic_agent", None)
                architect = getattr(self.task_dispatcher, "architect_agent", None)

                guardian = GuardianAgent(kernel=self.task_dispatcher.kernel)
                llm_config = create_local_llm_config()

                self._council_config = CouncilConfig(
                    coder_agent=coder,
                    critic_agent=critic,
                    architect_agent=architect,
                    guardian_agent=guardian,
                    llm_config=llm_config,
                )

            from venom_core.core.council import CouncilSession

            council_tuple = self._council_config.create_council()
            user_proxy, group_chat, manager = self._normalize_council_tuple(
                council_tuple
            )

            session = CouncilSession(user_proxy, group_chat, manager)

            members = []
            if group_chat is not None and getattr(group_chat, "agents", None):
                members = [
                    getattr(agent, "name", str(agent)) for agent in group_chat.agents
                ]

            await self._broadcast_event(
                event_type="COUNCIL_MEMBERS",
                message=f"Council składa się z {len(members)} członków",
                data={"task_id": str(task_id), "members": members},
            )

            result = await session.run(context)

            get_message_count = getattr(session, "get_message_count", lambda: 0)
            get_speakers = getattr(session, "get_speakers", lambda: members)
            message_count = get_message_count()
            speakers = get_speakers() or members

            self.state_manager.add_log(
                task_id,
                f"🏛️ THE COUNCIL: Dyskusja zakończona - {message_count} wiadomości, "
                f"uczestnicy: {', '.join(speakers)}",
            )

            await self._broadcast_event(
                event_type="COUNCIL_COMPLETED",
                message=f"Council zakończył dyskusję po {message_count} wiadomościach",
                data={
                    "task_id": str(task_id),
                    "message_count": message_count,
                    "speakers": speakers,
                },
            )

            logger.info(f"Council zakończył zadanie {task_id}")
            return result

        except Exception as e:
            error_msg = f"❌ Błąd podczas działania Council: {e}"
            logger.error(error_msg)

            self.state_manager.add_log(task_id, error_msg)

            await self._broadcast_event(
                event_type="COUNCIL_ERROR",
                message=error_msg,
                data={"task_id": str(task_id), "error": str(e)},
            )

            logger.warning("Council zawiódł - powrót do standardowego flow")
            return f"Council mode nie powiódł się: {e}"

    def _normalize_council_tuple(self, council_result):
        """Zapewnia że create_council zwraca krotkę (user_proxy, group_chat, manager)."""

        if isinstance(council_result, tuple):
            padded = list(council_result) + [None] * (3 - len(council_result))
            return tuple(padded[:3])

        user_proxy = getattr(council_result, "user_proxy", None)
        group_chat = getattr(council_result, "group_chat", None)
        manager = getattr(council_result, "manager", None)
        return user_proxy, group_chat, manager

    async def execute_healing_cycle(self, task_id: UUID, test_path: str = ".") -> dict:
        """
        Pętla samonaprawy (Test-Diagnose-Fix-Apply).

        Delegowane do HealingFlow.

        Args:
            task_id: ID zadania
            test_path: Ścieżka do testów

        Returns:
            Słownik z wynikami (success, iterations, final_report)
        """
        # Lazy init HealingFlow
        if self._healing_flow is None:
            self._healing_flow = HealingFlow(
                state_manager=self.state_manager,
                task_dispatcher=self.task_dispatcher,
                event_broadcaster=self.event_broadcaster,
            )

        return await self._healing_flow.execute(task_id, test_path)

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

        Delegowane do IssueHandlerFlow.

        Args:
            issue_number: Numer Issue do obsłużenia

        Returns:
            Dict z wynikiem operacji
        """
        # Lazy init IssueHandlerFlow
        if self._issue_handler_flow is None:
            self._issue_handler_flow = IssueHandlerFlow(
                state_manager=self.state_manager,
                task_dispatcher=self.task_dispatcher,
                event_broadcaster=self.event_broadcaster,
            )

        return await self._issue_handler_flow.execute(issue_number)

    async def execute_campaign_mode(
        self, goal_store=None, max_iterations: int = 10
    ) -> dict:
        """
        Tryb Kampanii - autonomiczna realizacja roadmapy.

        Delegowane do CampaignFlow.

        Args:
            goal_store: Magazyn celów (GoalStore)
            max_iterations: Maksymalna liczba iteracji (zabezpieczenie)

        Returns:
            Dict z wynikami kampanii
        """
        # Ta metoda już jest wywoływana przez _campaign_flow w _run_task
        # ale zostawiamy ją dla kompatybilności wstecznej
        if self._campaign_flow is None:
            self._campaign_flow = CampaignFlow(
                state_manager=self.state_manager,
                orchestrator_submit_task=self.submit_task,
                event_broadcaster=self.event_broadcaster,
            )

        return await self._campaign_flow.execute(goal_store, max_iterations)

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
