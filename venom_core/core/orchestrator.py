"""Moduł: orchestrator - orkiestracja zadań w tle."""

import asyncio
from datetime import datetime
from uuid import UUID

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.intent_manager import IntentManager
from venom_core.core.models import TaskRequest, TaskResponse, TaskStatus
from venom_core.core.state_manager import StateManager
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.perception.eyes import Eyes
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Maksymalna liczba prób naprawy kodu przez pętlę Coder-Critic
MAX_REPAIR_ATTEMPTS = 2

# Maksymalna długość tekstu w promptach (zabezpieczenie przed prompt injection)
MAX_PROMPT_LENGTH = 500


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

        # Inicjalizuj Eyes dla obsługi obrazów
        self.eyes = Eyes()

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

        # Zapisz obrazy w kontekście zadania jeśli istnieją
        if request.images:
            self.state_manager.add_log(
                task.id, f"Zadanie zawiera {len(request.images)} obrazów"
            )

        # Uruchom zadanie w tle (przekaż request zamiast tylko ID)
        asyncio.create_task(self._run_task(task.id, request))

        logger.info(f"Zadanie {task.id} przyjęte do wykonania")

        return TaskResponse(task_id=task.id, status=task.status)

    async def _run_task(self, task_id: UUID, request: TaskRequest) -> None:
        """
        Wykonuje zadanie w tle.

        Args:
            task_id: ID zadania do wykonania
            request: Oryginalne żądanie (z obrazami jeśli są)
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

            # Przygotuj kontekst (treść + analiza obrazów jeśli są)
            context = await self._prepare_context(task_id, request)

            # Klasyfikuj intencję użytkownika
            intent = await self.intent_manager.classify_intent(context)

            # Zaloguj sklasyfikowaną intencję
            self.state_manager.add_log(
                task_id,
                f"Sklasyfikowana intencja: {intent} - {datetime.now().isoformat()}",
            )

            # Jeśli to CODE_GENERATION, użyj pętli Coder-Critic
            if intent == "CODE_GENERATION":
                result = await self._code_generation_with_review(task_id, context)
            # Jeśli to COMPLEX_PLANNING, deleguj do Architekta
            elif intent == "COMPLEX_PLANNING":
                self.state_manager.add_log(
                    task_id,
                    f"Zadanie sklasyfikowane jako COMPLEX_PLANNING - delegacja do Architekta",
                )
                result = await self.task_dispatcher.dispatch(intent, context)
            else:
                # Dla innych intencji (RESEARCH, GENERAL_CHAT, KNOWLEDGE_SEARCH) - standardowy przepływ
                result = await self.task_dispatcher.dispatch(intent, context)

            # Zaloguj które agent przejął zadanie
            agent = self.task_dispatcher.agent_map.get(intent)
            if agent is not None:
                agent_name = agent.__class__.__name__
                self.state_manager.add_log(
                    task_id,
                    f"Agent {agent_name} przetworzył zadanie - {datetime.now().isoformat()}",
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
        self.state_manager.add_log(
            task_id, "Rozpoczynam pętlę Coder-Critic (samonaprawa kodu)"
        )

        # Pobranie agentów
        coder = self.task_dispatcher.coder_agent
        critic = self.task_dispatcher.critic_agent

        generated_code = None
        critic_feedback = None  # Inicjalizacja zmiennej
        attempt = 0

        while attempt <= MAX_REPAIR_ATTEMPTS:
            attempt += 1

            # Krok 1: CoderAgent generuje kod
            if attempt == 1:
                self.state_manager.add_log(
                    task_id, f"Coder: Próba {attempt} - generowanie kodu"
                )
                generated_code = await coder.process(user_request)
            else:
                # Kolejne próby - przekaż feedback od Krytyka
                self.state_manager.add_log(
                    task_id, f"Coder: Próba {attempt} - naprawa na podstawie feedbacku"
                )
                # Ogranicz długość poprzedniego kodu w promptcie dla wydajności
                code_preview = (
                    generated_code[:MAX_PROMPT_LENGTH] + "..."
                    if len(generated_code) > MAX_PROMPT_LENGTH
                    else generated_code
                )
                repair_prompt = f"""FEEDBACK OD KRYTYKA:
{critic_feedback[:MAX_PROMPT_LENGTH]}

ORYGINALNE ŻĄDANIE UŻYTKOWNIKA:
{user_request[:MAX_PROMPT_LENGTH]}

POPRZEDNI KOD (fragment):
{code_preview}

Popraw kod zgodnie z feedbackiem. Wygeneruj poprawioną wersję."""
                generated_code = await coder.process(repair_prompt)

            self.state_manager.add_log(
                task_id, f"Coder wygenerował kod ({len(generated_code)} znaków)"
            )

            # Krok 2: CriticAgent ocenia kod
            self.state_manager.add_log(task_id, "Critic: Ocena kodu...")
            review_input = f"USER_REQUEST: {user_request[:MAX_PROMPT_LENGTH]}\n\nCODE:\n{generated_code}"
            critic_feedback = await critic.process(review_input)

            # Krok 3: Sprawdź czy zaakceptowano
            if "APPROVED" in critic_feedback:
                self.state_manager.add_log(
                    task_id, f"✅ Critic ZAAKCEPTOWAŁ kod po {attempt} próbach"
                )
                logger.info(
                    f"Zadanie {task_id}: Kod zaakceptowany po {attempt} próbach"
                )
                return generated_code

            # Jeśli odrzucono
            self.state_manager.add_log(
                task_id, f"❌ Critic ODRZUCIŁ kod: {critic_feedback[:100]}..."
            )

            # Jeśli to była ostatnia próba
            if attempt > MAX_REPAIR_ATTEMPTS:
                self.state_manager.add_log(
                    task_id,
                    f"⚠️ Wyczerpano limit prób ({MAX_REPAIR_ATTEMPTS}). Zwracam ostatnią wersję z ostrzeżeniem.",
                )
                logger.warning(
                    f"Zadanie {task_id}: Przekroczono limit napraw, zwracam kod z ostrzeżeniem"
                )
                # Ogranicz rozmiar feedbacku w finalnej wiadomości
                feedback_summary = (
                    critic_feedback[:MAX_PROMPT_LENGTH] + "..."
                    if len(critic_feedback) > MAX_PROMPT_LENGTH
                    else critic_feedback
                )
                return f"⚠️ OSTRZEŻENIE: Kod nie został w pełni zaakceptowany po {MAX_REPAIR_ATTEMPTS} próbach.\n\nUWAGI KRYTYKA:\n{feedback_summary}\n\n---\n\n{generated_code}"

        # Nie powinno się tu dostać, ale dla bezpieczeństwa
        return generated_code or "Błąd: nie udało się wygenerować kodu"
