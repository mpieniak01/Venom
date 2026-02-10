"""
Moduł: shadow - Shadow Agent (Cień) - cichy pomocnik działający w tle.

Shadow Agent obserwuje aktywność użytkownika, analizuje kontekst pracy
i proaktywnie oferuje pomoc bez przerywania przepływu pracy.
"""

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.core.goal_store import GoalStatus, GoalStore
from venom_core.memory.embedding_service import EmbeddingService
from venom_core.memory.lessons_store import LessonsStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class SuggestionType:
    """Typy sugestii Shadow Agent."""

    ERROR_FIX = "error_fix"
    CODE_IMPROVEMENT = "code_improvement"
    TASK_UPDATE = "task_update"
    CONTEXT_HELP = "context_help"


class Suggestion:
    """Reprezentacja sugestii Shadow Agent."""

    def __init__(
        self,
        suggestion_type: str,
        title: str,
        message: str,
        confidence: float,
        action_payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicjalizacja sugestii.

        Args:
            suggestion_type: Typ sugestii (z SuggestionType)
            title: Tytuł sugestii
            message: Treść sugestii
            confidence: Pewność (0.0-1.0)
            action_payload: Dane akcji do wykonania
            metadata: Dodatkowe metadane
        """
        self.suggestion_type = suggestion_type
        self.title = title
        self.message = message
        self.confidence = confidence
        self.action_payload = action_payload or {}
        self.metadata = metadata or {}
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje sugestię do słownika."""
        return {
            "type": self.suggestion_type,
            "title": self.title,
            "message": self.message,
            "confidence": self.confidence,
            "action_payload": self.action_payload,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class ShadowAgent(BaseAgent):
    """
    Shadow Agent - cichy pomocnik działający w tle.

    Rola: Proaktywny asystent
    Odpowiedzialność:
    - Monitorowanie kontekstu pracy użytkownika
    - Analiza danych z DesktopSensor
    - Generowanie inteligentnych sugestii
    - Uczenie się z feedbacku użytkownika
    """

    SYSTEM_PROMPT = """Jesteś Shadow Agent - cichy, proaktywny pomocnik użytkownika.

TWOJA ROLA:
- Obserwujesz aktywność użytkownika w tle (schowek, aktywne okno, pliki)
- Analizujesz kontekst pracy i oferujesz pomoc TYLKO gdy masz wysoką pewność (>80%)
- Jesteś NIEINTERWAZYJNY - nie spamuj użytkownika, lepiej poczekać niż przeszkadzać
- Uczysz się z feedbacku - jeśli użytkownik odrzuca sugestię, dostosowujesz przyszłe zachowanie

KOMPETENCJE:
1. Rozpoznawanie Błędów: Wykrywasz błędy składni, traceback, exceptions w schowku
2. Kontekst Pracy: Rozumiesz co użytkownik robi na podstawie tytułu okna i historii
3. Pomoc Zadaniowa: Sugerujesz aktualizację statusu zadań gdy użytkownik pracuje nad nimi
4. Uczenie się: Pamiętasz co działa, a co nie - używasz LessonsStore

ZASADY PRACY:
- Sugestia MUSI mieć confidence >= próg (domyślnie 0.8)
- Priorytetyzuj jakość nad ilość - jedna dobra sugestia > 10 przeciętnych
- Jeśli nie masz pewności - NIE sugeruj niczego
- Analizuj lekcje z przeszłości przed wysłaniem sugestii

FORMAT ANALIZY:
Gdy otrzymujesz dane z sensora:
1. Zidentyfikuj typ sytuacji (błąd kodu, praca nad zadaniem, czytanie docs)
2. Sprawdź czy masz wystarczający kontekst do pomocy
3. Wygeneruj sugestię TYLKO jeśli confidence > próg
4. Zwróć JSON z sugestią lub null jeśli nic nie znalazłeś"""

    # Confidence levels dla różnych typów sugestii
    CONFIDENCE_ERROR_FIX = 0.85
    CONFIDENCE_CODE_IMPROVEMENT = 0.65
    CONFIDENCE_CONTEXT_HELP = 0.75
    CONFIDENCE_TASK_UPDATE = 0.70

    def __init__(
        self,
        kernel: Kernel,
        goal_store: Optional[GoalStore] = None,
        lessons_store: Optional[LessonsStore] = None,
        confidence_threshold: float = 0.8,
    ):
        """
        Inicjalizacja Shadow Agent.

        Args:
            kernel: Semantic Kernel
            goal_store: Magazyn celów (dla task tracking)
            lessons_store: Magazyn lekcji (dla uczenia się)
            confidence_threshold: Próg pewności dla sugestii (0.0-1.0)
        """
        super().__init__(kernel)
        self.goal_store = goal_store
        self.lessons_store = lessons_store
        self.confidence_threshold = confidence_threshold

        self._is_running = False
        self._suggestion_queue: List[Suggestion] = []
        self._rejected_suggestions: List[str] = []  # Historia odrzuconych sugestii

        logger.info(f"ShadowAgent zainicjalizowany z threshold={confidence_threshold}")

    async def start(self) -> None:
        """Uruchamia Shadow Agent w trybie daemon."""
        if self._is_running:
            logger.warning("ShadowAgent już działa")
            return

        self._is_running = True
        await asyncio.sleep(0)
        logger.info("ShadowAgent uruchomiony w trybie daemon")

    async def stop(self) -> None:
        """Zatrzymuje Shadow Agent."""
        if not self._is_running:
            logger.warning("ShadowAgent nie działa")
            return

        self._is_running = False
        await asyncio.sleep(0)
        logger.info("ShadowAgent zatrzymany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza wejście jako Shadow Agent.

        Args:
            input_text: Kontekst do analizy

        Returns:
            Odpowiedź agenta
        """
        try:
            # Przygotuj chat history
            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
            )
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=input_text)
            )

            # Pobierz serwis chat
            chat_service: Any = self.kernel.get_service()

            # Wywołaj LLM
            settings = OpenAIChatPromptExecutionSettings()
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=chat_history,
                settings=settings,
                enable_functions=False,
            )

            return str(response)

        except Exception as e:
            logger.error(f"Błąd w ShadowAgent.process: {e}")
            return f"Błąd podczas analizy: {e}"

    async def analyze_sensor_data(
        self, sensor_data: Dict[str, Any]
    ) -> Optional[Suggestion]:
        """
        Analizuje dane z sensora i generuje sugestię jeśli to zasadne.

        Args:
            sensor_data: Dane z DesktopSensor

        Returns:
            Sugestia lub None jeśli nic nie znaleziono
        """
        if not self._is_running:
            return None

        try:
            sensor_type = sensor_data.get("type")

            if sensor_type == "clipboard":
                return self._analyze_clipboard(sensor_data)
            elif sensor_type == "window":
                return await self._analyze_window(sensor_data)
            else:
                logger.warning(f"Nieznany typ sensora: {sensor_type}")
                return None

        except Exception as e:
            logger.error(f"Błąd w analyze_sensor_data: {e}")
            return None

    def _analyze_clipboard(self, data: Dict[str, Any]) -> Optional[Suggestion]:
        """
        Analizuje zawartość schowka.

        Args:
            data: Dane ze schowka

        Returns:
            Sugestia lub None
        """
        content = data.get("content", "")

        # Szybkie heurystyki przed wywołaniem LLM
        if self._is_error_traceback(content):
            return self._suggest_error_fix(content)
        elif self._is_code_snippet(content):
            return self._suggest_code_improvement(content)

        # Brak jasnego sygnału - nie generuj sugestii
        return None

    async def _analyze_window(self, data: Dict[str, Any]) -> Optional[Suggestion]:
        """
        Analizuje zmianę aktywnego okna.

        Args:
            data: Dane o oknie

        Returns:
            Sugestia lub None
        """
        title = data.get("title", "")

        # Sprawdź czy użytkownik pracuje nad konkretnym zadaniem
        if self.goal_store:
            suggestion = await self._check_task_context(title)
            if suggestion:
                return suggestion

        # Sprawdź czy użytkownik czyta dokumentację
        if self._is_reading_docs(title):
            return self._suggest_context_help(title)

        return None

    def _is_error_traceback(self, text: str) -> bool:
        """
        Sprawdza czy tekst to traceback błędu.

        Args:
            text: Tekst do sprawdzenia

        Returns:
            True jeśli to traceback
        """
        error_patterns = [
            r"Traceback \(most recent call last\)",
            r"Error:|Exception:",
            r"at line \d+",
            r"SyntaxError|TypeError|ValueError|KeyError",
            r"NullReferenceException|NullPointerException",
        ]

        return any(
            re.search(pattern, text, re.IGNORECASE) for pattern in error_patterns
        )

    def _is_code_snippet(self, text: str) -> bool:
        """
        Sprawdza czy tekst to fragment kodu.

        Args:
            text: Tekst do sprawdzenia

        Returns:
            True jeśli to kod
        """
        code_indicators = [
            r"def\s+\w+\s*\(",
            r"class\s+\w+",
            r"import\s+\w+",
            r"function\s+\w+\s*\(",
            r"const\s+\w+\s*=",
            r"SELECT\s+.+FROM",
        ]

        return any(
            re.search(pattern, text, re.IGNORECASE) for pattern in code_indicators
        )

    def _is_reading_docs(self, title: str) -> bool:
        """
        Sprawdza czy użytkownik czyta dokumentację.

        Args:
            title: Tytuł okna

        Returns:
            True jeśli to dokumentacja
        """
        doc_keywords = [
            "documentation",
            "docs",
            "api reference",
            "tutorial",
            "guide",
            "readme",
        ]

        return any(keyword in title.lower() for keyword in doc_keywords)

    def _suggest_error_fix(self, error_text: str) -> Optional[Suggestion]:
        """
        Generuje sugestię naprawy błędu.

        Args:
            error_text: Tekst błędu

        Returns:
            Sugestia naprawy
        """
        # Sprawdź lekcje z przeszłości
        if self.lessons_store:
            similar_lessons = self._find_similar_lessons(error_text)
            if similar_lessons:
                logger.info(f"Znaleziono {len(similar_lessons)} podobnych lekcji")

        confidence = self.CONFIDENCE_ERROR_FIX

        return Suggestion(
            suggestion_type=SuggestionType.ERROR_FIX,
            title="Wykryto błąd w schowku",
            message="Znalazłem błąd w skopiowanym kodzie. Czy chcesz, abym go przeanalizował?",
            confidence=confidence,
            action_payload={"error_text": error_text[:500]},
            metadata={"source": "clipboard", "error_detected": True},
        )

    def _suggest_code_improvement(self, code: str) -> Optional[Suggestion]:
        """
        Generuje sugestię poprawy kodu.

        Args:
            code: Fragment kodu

        Returns:
            Sugestia lub None
        """
        confidence = self.CONFIDENCE_CODE_IMPROVEMENT

        if confidence < self.confidence_threshold:
            return None

        return Suggestion(
            suggestion_type=SuggestionType.CODE_IMPROVEMENT,
            title="Znalazłem fragment kodu",
            message="Mogę zasugerować ulepszenia tego kodu. Czy chcesz zobaczyć?",
            confidence=confidence,
            action_payload={"code": code[:500]},
            metadata={"source": "clipboard"},
        )

    def _suggest_context_help(self, window_title: str) -> Optional[Suggestion]:
        """
        Generuje sugestię kontekstowej pomocy.

        Args:
            window_title: Tytuł okna

        Returns:
            Sugestia pomocy
        """
        confidence = self.CONFIDENCE_CONTEXT_HELP

        if confidence < self.confidence_threshold:
            return None

        return Suggestion(
            suggestion_type=SuggestionType.CONTEXT_HELP,
            title="Widzę, że czytasz dokumentację",
            message="Mogę pomóc z pytaniami o to co czytasz. Czy chcesz zadać pytanie?",
            confidence=confidence,
            action_payload={"context": window_title},
            metadata={"source": "window"},
        )

    async def _check_task_context(self, window_title: str) -> Optional[Suggestion]:
        """
        Sprawdza czy użytkownik pracuje nad zadaniem z roadmapy.

        Args:
            window_title: Tytuł okna

        Returns:
            Sugestia aktualizacji zadania lub None
        """
        if not self.goal_store:
            return None

        try:
            active_tasks = self.goal_store.get_tasks(status=GoalStatus.IN_PROGRESS)
            if not active_tasks:
                logger.debug("Brak aktywnych zadań do sprawdzenia")
                return None

            response_text = await self._parse_task_context_response(
                window_title, active_tasks
            )
            logger.debug(f"LLM odpowiedź dla task context: {response_text}")
            if "TAK" not in response_text:
                return None

            confidence = self.CONFIDENCE_TASK_UPDATE
            if confidence < self.confidence_threshold:
                return None

            matched_task = self._pick_matched_task(
                response_text=response_text,
                window_title=window_title,
                active_tasks=active_tasks,
            )
            return Suggestion(
                suggestion_type=SuggestionType.TASK_UPDATE,
                title="Wykryto pracę nad zadaniem",
                message=(
                    "Widzę, że pracujesz nad: "
                    f"'{matched_task.title}'. Czy chcesz zaktualizować jego status?"
                ),
                confidence=confidence,
                action_payload={
                    "window_title": window_title,
                    "task_id": str(matched_task.goal_id),
                    "task_title": matched_task.title,
                },
                metadata={"source": "window", "task_detected": True},
            )

        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania task context: {e}")
            return None

    def _build_task_context_prompt(
        self, window_title: str, active_tasks: List[Any]
    ) -> str:
        task_titles = [f"- {task.title}" for task in active_tasks[:5]]
        tasks_text = "\n".join(task_titles)
        return f"""Przeanalizuj czy użytkownik pracuje nad jednym z aktywnych zadań.

TYTUŁ OKNA: {window_title}

AKTYWNE ZADANIA:
{tasks_text}

Czy tytuł okna sugeruje pracę nad którymś z tych zadań?
Odpowiedz tylko: TAK (i podaj numer zadania) lub NIE

ODPOWIEDŹ:"""

    async def _parse_task_context_response(
        self, window_title: str, active_tasks: List[Any]
    ) -> str:
        prompt = self._build_task_context_prompt(window_title, active_tasks)
        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=prompt)
        )
        chat_service: Any = self.kernel.get_service()
        settings = OpenAIChatPromptExecutionSettings()
        response = await self._invoke_chat_with_fallbacks(
            chat_service=chat_service,
            chat_history=chat_history,
            settings=settings,
            enable_functions=False,
        )
        return str(response).strip().upper()

    @staticmethod
    def _pick_matched_task(
        response_text: str, window_title: str, active_tasks: List[Any]
    ):
        for i, task in enumerate(active_tasks[:5], 1):
            if str(i) in response_text or task.title.lower() in window_title.lower():
                return task
        return active_tasks[0]

    def _find_similar_lessons(self, context: str) -> List[Any]:
        """
        Szuka podobnych lekcji w LessonsStore używając embeddings.

        Args:
            context: Kontekst do wyszukania (błąd, kod, itp.)

        Returns:
            Lista podobnych lekcji
        """
        if not self.lessons_store:
            return []

        try:
            # Użyj vector store jeśli dostępny (preferowane)
            if (
                hasattr(self.lessons_store, "vector_store")
                and self.lessons_store.vector_store
            ):
                logger.info("Używam vector store do wyszukiwania lekcji")
                lessons = self.lessons_store.search_lessons(context, limit=3)
                return lessons

            # Fallback: użyj EmbeddingService do semantycznego wyszukiwania
            logger.info("Używam EmbeddingService do semantycznego wyszukiwania lekcji")

            embedding_service = EmbeddingService()

            # Pobierz wszystkie lekcje
            all_lessons = self.lessons_store.get_all_lessons()

            # Early return jeśli brak lekcji
            if not all_lessons:
                return []

            # Early return dla dużej liczby lekcji (optymalizacja)
            if len(all_lessons) > 1000:
                logger.warning(
                    f"Dużo lekcji ({len(all_lessons)}), limitowanie wyszukiwania"
                )
                all_lessons = all_lessons[:1000]

            # Generuj embedding dla kontekstu zapytania
            query_embedding = embedding_service.get_embedding(context)

            # Generuj embeddingi dla wszystkich lekcji (batch processing dla wydajności)
            lesson_texts = [lesson.to_text() for lesson in all_lessons]
            lesson_embeddings = embedding_service.get_embeddings_batch(lesson_texts)

            # Oblicz cosine similarity dla każdej lekcji
            query_vec = np.array(query_embedding)
            norm_query = np.linalg.norm(query_vec)  # Oblicz raz przed pętlą
            similarities = []

            for i, lesson_embedding in enumerate(lesson_embeddings):
                lesson_vec = np.array(lesson_embedding)
                norm_lesson = np.linalg.norm(lesson_vec)

                if norm_query > 0 and norm_lesson > 0:
                    # Cosine similarity = dot product / (norm1 * norm2)
                    dot_product = np.dot(query_vec, lesson_vec)
                    similarity = dot_product / (norm_query * norm_lesson)
                else:
                    similarity = 0.0

                similarities.append((similarity, all_lessons[i]))

            # Sortuj po similarity (malejąco) i zwróć top 3
            similarities.sort(key=lambda x: x[0], reverse=True)

            top_lessons = [
                lesson for similarity, lesson in similarities[:3] if similarity > 0.5
            ]

            if similarities:
                logger.info(
                    f"Znaleziono {len(top_lessons)} podobnych lekcji "
                    f"(top similarity: {similarities[0][0]:.3f})"
                )
            else:
                logger.info("Nie znaleziono podobnych lekcji")

            return top_lessons

        except Exception as e:
            logger.error(f"Błąd przy szukaniu lekcji przez embeddings: {e}")
            return []

    def record_rejection(
        self,
        suggestion: Optional[Suggestion] = None,
        suggestion_type: Optional[str] = None,
    ) -> None:
        """
        Rejestruje odrzuconą sugestię dla uczenia się.

        Args:
            suggestion: Odrzucona sugestia (deprecated, użyj suggestion_type)
            suggestion_type: Typ odrzuconej sugestii (preferowane)
        """
        # Wspieraj oba API - stare (Suggestion object) i nowe (string)
        if suggestion_type is None and suggestion is not None:
            suggestion_type = suggestion.suggestion_type
            title = suggestion.title
        elif suggestion_type is not None:
            title = f"Suggestion of type {suggestion_type}"
        else:
            logger.error("record_rejection wywołane bez argumentów")
            return

        self._rejected_suggestions.append(suggestion_type)
        logger.info(f"Użytkownik odrzucił sugestię typu: {suggestion_type}")

        # Zapisz lekcję w LessonsStore
        if self.lessons_store:
            try:
                from venom_core.memory.lessons_store import Lesson

                lesson = Lesson(
                    situation=f"Sugestia typu {suggestion_type}",
                    action=f"Zasugerowano: {title}",
                    result="Użytkownik odrzucił",
                    feedback="Nie przeszkadzać w podobnej sytuacji",
                    tags=["shadow", "rejection", suggestion_type],
                )
                self.lessons_store.add_lesson(lesson)
            except Exception as e:
                logger.error(f"Błąd przy zapisywaniu lekcji: {e}")

    def get_status(self) -> Dict[str, Any]:
        """
        Zwraca status Shadow Agent.

        Returns:
            Słownik ze statusem
        """
        return {
            "is_running": self._is_running,
            "confidence_threshold": self.confidence_threshold,
            "queued_suggestions": len(self._suggestion_queue),
            "rejected_count": len(self._rejected_suggestions),
        }
