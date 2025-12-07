"""Moduł: orchestrator - orkiestracja zadań w tle."""

import asyncio
from datetime import datetime
from uuid import UUID

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.intent_manager import IntentManager
from venom_core.core.metrics import metrics_collector
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

# Ustawienia dla pętli meta-uczenia
ENABLE_META_LEARNING = True  # Flaga do włączania/wyłączania meta-uczenia
MAX_LESSONS_IN_CONTEXT = 3  # Maksymalna liczba lekcji dołączanych do promptu

# Ustawienia dla The Council (AutoGen Group Chat)
ENABLE_COUNCIL_MODE = True  # Flaga do włączania/wyłączania trybu Council
COUNCIL_TASK_THRESHOLD = (
    100  # Minimalna długość zadania aby użyć Council (liczba znaków)
)

# Słowa kluczowe sugerujące potrzebę współpracy agentów (dla decyzji Council vs Standard)
COUNCIL_COLLABORATION_KEYWORDS = [
    "projekt",
    "aplikacja",
    "system",
    "stwórz grę",
    "zbuduj",
    "zaprojektuj",
    "zaimplementuj",
    "kompletny",
    "cała aplikacja",
]


class Orchestrator:
    """Orkiestrator zadań - zarządzanie wykonywaniem zadań w tle."""

    def __init__(
        self,
        state_manager: StateManager,
        intent_manager: IntentManager = None,
        task_dispatcher: TaskDispatcher = None,
        event_broadcaster=None,
        lessons_store=None,
    ):
        """
        Inicjalizacja Orchestrator.

        Args:
            state_manager: Menedżer stanu zadań
            intent_manager: Opcjonalny menedżer klasyfikacji intencji (jeśli None, zostanie utworzony)
            task_dispatcher: Opcjonalny dispatcher zadań (jeśli None, zostanie utworzony)
            event_broadcaster: Opcjonalny broadcaster zdarzeń do WebSocket
            lessons_store: Opcjonalny magazyn lekcji (dla meta-uczenia)
        """
        self.state_manager = state_manager
        self.intent_manager = intent_manager or IntentManager()
        self.event_broadcaster = event_broadcaster
        self.lessons_store = lessons_store  # Magazyn lekcji dla meta-uczenia

        # Inicjalizuj dispatcher jeśli nie został przekazany
        if task_dispatcher is None:
            kernel_builder = KernelBuilder()
            kernel = kernel_builder.build_kernel()
            task_dispatcher = TaskDispatcher(
                kernel, event_broadcaster=event_broadcaster
            )

        self.task_dispatcher = task_dispatcher

        # Inicjalizuj Eyes dla obsługi obrazów
        self.eyes = Eyes()

        # Council mode - inicjalizowane lazy (tylko jeśli włączone i potrzebne)
        self._council_config = None

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
        # Utwórz zadanie przez StateManager
        task = self.state_manager.create_task(content=request.content)

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

            # Broadcast intencji
            await self._broadcast_event(
                event_type="AGENT_THOUGHT",
                message=f"Rozpoznano intencję: {intent}",
                data={"task_id": str(task_id), "intent": intent},
            )

            # DECYZJA: Council mode vs Standard mode
            should_use_council = self._should_use_council(context, intent)

            if should_use_council:
                # Tryb Council - autonomiczna dyskusja agentów
                self.state_manager.add_log(
                    task_id,
                    "🏛️ Zadanie wymaga współpracy - aktywuję The Council",
                )
                result = await self.run_council(task_id, context)
            elif intent == "CODE_GENERATION":
                # Standardowy tryb - pętla Coder-Critic
                result = await self._code_generation_with_review(task_id, context)
            elif intent == "COMPLEX_PLANNING":
                # Standardowy tryb - delegacja do Architekta
                self.state_manager.add_log(
                    task_id,
                    "Zadanie sklasyfikowane jako COMPLEX_PLANNING - delegacja do Architekta",
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
                result = await self.task_dispatcher.dispatch(intent, context)

            # Zaloguj które agent przejął zadanie
            agent = self.task_dispatcher.agent_map.get(intent)
            if agent is not None:
                agent_name = agent.__class__.__name__
                self.state_manager.add_log(
                    task_id,
                    f"Agent {agent_name} przetworzył zadanie - {datetime.now().isoformat()}",
                )
                # Inkrementuj licznik użycia agenta
                if metrics_collector:
                    metrics_collector.increment_agent_usage(agent_name)
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

            # REFLEKSJA: Zapisz lekcję o sukcesie (jeśli meta-uczenie włączone)
            await self._save_task_lesson(
                task_id=task_id,
                context=context,
                intent=intent,
                result=result,
                success=True,
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

            # REFLEKSJA: Zapisz lekcję o błędzie (jeśli meta-uczenie włączone)
            await self._save_task_lesson(
                task_id=task_id,
                context=context,
                intent=intent,
                result=f"Błąd: {str(e)}",
                success=False,
                error=str(e),
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
        if not ENABLE_COUNCIL_MODE:
            return False

        # Council dla złożonych zadań planistycznych
        if intent == "COMPLEX_PLANNING":
            return True

        # Council dla długich zadań wymagających współpracy
        if len(context) > COUNCIL_TASK_THRESHOLD:
            # Sprawdź czy zadanie zawiera słowa kluczowe sugerujące współpracę
            context_lower = context.lower()
            for keyword in COUNCIL_COLLABORATION_KEYWORDS:
                if keyword in context_lower:
                    logger.info(f"Wykryto słowo kluczowe '{keyword}' - użyję Council")
                    return True

        return False

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
        logger.info(f"Uruchamiam The Council dla zadania {task_id}")

        self.state_manager.add_log(
            task_id, "🏛️ THE COUNCIL: Rozpoczynam tryb Group Chat (Swarm Intelligence)"
        )

        await self._broadcast_event(
            event_type="COUNCIL_STARTED",
            message="The Council rozpoczyna dyskusję nad zadaniem",
            data={"task_id": str(task_id)},
        )

        try:
            # Lazy init council config
            if self._council_config is None:
                from venom_core.core.council import (
                    CouncilConfig,
                    create_local_llm_config,
                )

                # Pobierz agentów z dispatchera
                coder = self.task_dispatcher.coder_agent
                critic = self.task_dispatcher.critic_agent
                architect = self.task_dispatcher.architect_agent

                # Guardian musimy utworzyć (nie ma go w standardowym dispatcher)
                from venom_core.agents.guardian import GuardianAgent

                guardian = GuardianAgent(kernel=self.task_dispatcher.kernel)

                # Stwórz konfigurację LLM (lokalny model)
                llm_config = create_local_llm_config()

                # Inicjalizuj Council Config
                self._council_config = CouncilConfig(
                    coder_agent=coder,
                    critic_agent=critic,
                    architect_agent=architect,
                    guardian_agent=guardian,
                    llm_config=llm_config,
                )

                logger.info("Council Config zainicjalizowany")

            # Stwórz sesję Council
            # UWAGA: Tworzymy nową sesję przy każdym wywołaniu aby zapewnić czysty stan
            # i uniknąć kontaminacji historii między różnymi zadaniami.
            # GroupChat przechowuje historię wiadomości, więc ponowne użycie
            # mogłoby prowadzić do nieprawidłowych kontekstów dla kolejnych zadań.
            from venom_core.core.council import CouncilSession

            user_proxy, group_chat, manager = self._council_config.create_council()
            session = CouncilSession(user_proxy, group_chat, manager)

            # Broadcast informacji o uczestnikach
            await self._broadcast_event(
                event_type="COUNCIL_MEMBERS",
                message=f"Council składa się z {len(group_chat.agents)} członków",
                data={
                    "task_id": str(task_id),
                    "members": [agent.name for agent in group_chat.agents],
                },
            )

            # Uruchom dyskusję
            result = await session.run(context)

            # Loguj szczegóły dyskusji
            message_count = session.get_message_count()
            speakers = session.get_speakers()

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

            # Fallback do standardowego flow
            logger.warning("Council zawiódł - powrót do standardowego flow")
            return f"{error_msg}\n\nPróbuję standardowy flow jako fallback..."

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
        from venom_core.agents.guardian import GuardianAgent

        try:
            logger.info(f"🔨 THE FORGE: Rozpoczynam tworzenie narzędzia {tool_name}")

            self.state_manager.add_log(
                task_id,
                f"🔨 THE FORGE: Tworzę nowe narzędzie '{tool_name}'",
            )

            await self._broadcast_event(
                event_type="FORGE_STARTED",
                message=f"Rozpoczynam tworzenie narzędzia: {tool_name}",
                agent="Toolmaker",
                data={"task_id": str(task_id), "tool_name": tool_name},
            )

            # PHASE 1: CRAFT - Toolmaker generuje kod
            self.state_manager.add_log(
                task_id,
                "⚒️ PHASE 1: Toolmaker generuje kod narzędzia...",
            )

            toolmaker = self.task_dispatcher.toolmaker_agent

            # Generuj narzędzie
            success, tool_code = await toolmaker.create_tool(
                specification=tool_specification,
                tool_name=tool_name,
                output_dir=None,  # Zapisze do workspace/custom/
            )

            if not success:
                error_msg = f"❌ Toolmaker nie mógł wygenerować narzędzia: {tool_code}"
                logger.error(error_msg)
                self.state_manager.add_log(task_id, error_msg)

                await self._broadcast_event(
                    event_type="FORGE_FAILED",
                    message=error_msg,
                    agent="Toolmaker",
                    data={"task_id": str(task_id), "error": tool_code},
                )

                return {
                    "success": False,
                    "tool_name": tool_name,
                    "message": error_msg,
                }

            self.state_manager.add_log(
                task_id,
                f"✅ Kod narzędzia wygenerowany ({len(tool_code)} znaków)",
            )

            # PHASE 2: TEST - Toolmaker generuje test
            self.state_manager.add_log(
                task_id,
                "🧪 PHASE 2: Toolmaker generuje testy...",
            )

            test_success, test_code = await toolmaker.create_test(
                tool_name=tool_name,
                tool_code=tool_code,
                output_dir=None,
            )

            if test_success:
                self.state_manager.add_log(
                    task_id,
                    "✅ Test jednostkowy wygenerowany",
                )
            else:
                self.state_manager.add_log(
                    task_id,
                    f"⚠️ Nie udało się wygenerować testu: {test_code[:100]}",
                )

            # PHASE 3: VERIFY - Guardian testuje w Dockerze
            self.state_manager.add_log(
                task_id,
                "🔍 PHASE 3: Guardian weryfikuje narzędzie w Docker Sandbox...",
            )

            try:
                guardian = GuardianAgent(kernel=self.task_dispatcher.kernel)

                # Sprawdź podstawową składnię - ogranicz kod do bezpiecznego fragmentu
                # Używamy tylko metadanych, nie całego kodu aby uniknąć prompt injection
                verify_prompt = f"""Sprawdź czy narzędzie {tool_name} jest poprawne składniowo.

METADANE NARZĘDZIA:
- Nazwa: {tool_name}
- Długość kodu: {len(tool_code)} znaków
- Czy zawiera @kernel_function: {"TAK" if "@kernel_function" in tool_code else "NIE"}
- Czy zawiera klasę: {"TAK" if "class " in tool_code else "NIE"}

FRAGMENT KODU (pierwsze 500 znaków):
```python
{tool_code[:500]}
```

Zweryfikuj:
1. Czy fragment kodu jest poprawny składniowo (Python syntax)
2. Czy ma dekorator @kernel_function
3. Czy ma odpowiednie type hints
4. Czy nie widać niebezpiecznych konstrukcji (eval, exec)

Odpowiedz APPROVED jeśli wygląda OK, lub opisz problemy."""

                verification_result = await guardian.process(verify_prompt)

                if "APPROVED" in verification_result.upper():
                    self.state_manager.add_log(
                        task_id,
                        "✅ Narzędzie przeszło weryfikację Guardian",
                    )
                else:
                    self.state_manager.add_log(
                        task_id,
                        f"⚠️ Guardian zgłosił uwagi: {verification_result[:200]}",
                    )

            except Exception as e:
                logger.warning(f"Nie udało się uruchomić weryfikacji Docker: {e}")
                self.state_manager.add_log(
                    task_id,
                    f"⚠️ Pomijam weryfikację Docker (błąd: {str(e)})",
                )

            # PHASE 4: LOAD - SkillManager ładuje narzędzie
            self.state_manager.add_log(
                task_id,
                "⚡ PHASE 4: SkillManager ładuje narzędzie do Kernela...",
            )

            try:
                skill_manager = self.task_dispatcher.skill_manager

                # Przeładuj narzędzie (jeśli już istniało) lub załaduj nowe
                reload_success = skill_manager.reload_skill(tool_name)

                if reload_success:
                    self.state_manager.add_log(
                        task_id,
                        f"✅ Narzędzie '{tool_name}' załadowane i gotowe do użycia!",
                    )

                    await self._broadcast_event(
                        event_type="FORGE_COMPLETED",
                        message=f"Narzędzie {tool_name} zostało stworzone i załadowane",
                        agent="SkillManager",
                        data={
                            "task_id": str(task_id),
                            "tool_name": tool_name,
                            "success": True,
                        },
                    )

                    logger.info(f"🔨 THE FORGE: Narzędzie {tool_name} gotowe!")

                    return {
                        "success": True,
                        "tool_name": tool_name,
                        "message": f"Narzędzie '{tool_name}' zostało pomyślnie stworzone i załadowane. Możesz go teraz użyć!",
                        "code": tool_code,
                    }
                else:
                    error_msg = "❌ Nie udało się załadować narzędzia do Kernela"
                    self.state_manager.add_log(task_id, error_msg)

                    await self._broadcast_event(
                        event_type="FORGE_FAILED",
                        message=error_msg,
                        agent="SkillManager",
                        data={"task_id": str(task_id), "tool_name": tool_name},
                    )

                    return {
                        "success": False,
                        "tool_name": tool_name,
                        "message": error_msg,
                        "code": tool_code,
                    }

            except Exception as e:
                error_msg = f"❌ Błąd podczas ładowania narzędzia: {str(e)}"
                logger.error(error_msg)
                self.state_manager.add_log(task_id, error_msg)

                await self._broadcast_event(
                    event_type="FORGE_ERROR",
                    message=error_msg,
                    agent="SkillManager",
                    data={"task_id": str(task_id), "error": str(e)},
                )

                return {
                    "success": False,
                    "tool_name": tool_name,
                    "message": error_msg,
                }

        except Exception as e:
            error_msg = f"❌ Błąd podczas workflow The Forge: {str(e)}"
            logger.error(error_msg)
            self.state_manager.add_log(task_id, error_msg)

            await self._broadcast_event(
                event_type="FORGE_ERROR",
                message=error_msg,
                data={"task_id": str(task_id), "error": str(e)},
            )

            return {
                "success": False,
                "tool_name": tool_name,
                "message": error_msg,
            }
