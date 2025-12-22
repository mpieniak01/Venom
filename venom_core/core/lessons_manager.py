"""Moduł: lessons_manager - zarządzanie meta-uczeniem (lessons)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from venom_core.config import SETTINGS
from venom_core.core import metrics as metrics_module
from venom_core.core.models import TaskRequest
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Ustawienia dla meta-uczenia
MAX_LESSONS_IN_CONTEXT = 3
LEARNING_LOG_PATH = Path("./data/learning/requests.jsonl")
MAX_LEARNING_SNIPPET = 1200

# Intencje które nie wymagają uczenia
NON_LEARNING_INTENTS = {
    "TIME_REQUEST",
    "INFRA_STATUS",
}


class LessonsManager:
    """Manager do zarządzania lekcjami meta-uczenia."""

    def __init__(
        self,
        state_manager,
        lessons_store=None,
        event_broadcaster=None,
    ):
        """
        Inicjalizacja LessonsManager.

        Args:
            state_manager: Menedżer stanu zadań
            lessons_store: Magazyn lekcji
            event_broadcaster: Opcjonalny broadcaster do WebSocket
        """
        self.state_manager = state_manager
        self.lessons_store = lessons_store
        self.event_broadcaster = event_broadcaster

    def should_store_lesson(
        self,
        request: TaskRequest,
        intent: str = "",
        agent=None,
    ) -> bool:
        """
        Sprawdza czy należy zapisać lekcję dla danego zadania.

        Args:
            request: Oryginalne żądanie zadania
            intent: Sklasyfikowana intencja
            agent: Opcjonalny agent

        Returns:
            True jeśli lekcja powinna być zapisana
        """
        if not (request.store_knowledge and SETTINGS.ENABLE_META_LEARNING):
            return False

        if intent in NON_LEARNING_INTENTS:
            return False

        if agent and getattr(agent, "disable_learning", False):
            return False

        return True

    def should_log_learning(
        self,
        request: TaskRequest,
        intent: str,
        tool_required: bool,
        agent=None,
    ) -> bool:
        """
        Zwraca True jeśli należy zapisać wpis procesu nauki dla LLM-only.

        Args:
            request: Żądanie zadania
            intent: Intencja
            tool_required: Czy wymagane jest narzędzie
            agent: Opcjonalny agent

        Returns:
            True jeśli należy logować
        """
        if not request.store_knowledge:
            return False
        if tool_required:
            return False
        if intent in NON_LEARNING_INTENTS:
            return False
        if agent and getattr(agent, "disable_learning", False):
            return False
        return True

    async def add_lessons_to_context(self, task_id: UUID, context: str) -> str:
        """
        Pre-flight check: Dodaje relevantne lekcje z przeszłości do kontekstu.

        Args:
            task_id: ID zadania
            context: Oryginalny kontekst

        Returns:
            Kontekst wzbogacony o lekcje
        """
        if not SETTINGS.ENABLE_META_LEARNING or not self.lessons_store:
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
            if self.event_broadcaster:
                await self.event_broadcaster.broadcast_event(
                    event_type="AGENT_THOUGHT",
                    message=f"Znalazłem {len(lessons)} relevantnych lekcji z przeszłości",
                    data={"task_id": str(task_id), "lessons_count": len(lessons)},
                )

            # Dołącz lekcje na początku kontekstu
            return lessons_text + "\n\n" + context

        except Exception as e:
            logger.warning(f"Błąd podczas dodawania lekcji do kontekstu: {e}")
            return context

    async def save_task_lesson(
        self,
        task_id: UUID,
        context: str,
        intent: str,
        result: str,
        success: bool,
        error: str = None,
        agent: Optional[object] = None,
        request: Optional[TaskRequest] = None,
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
            agent: Opcjonalny agent
            request: Opcjonalne żądanie
        """
        if not SETTINGS.ENABLE_META_LEARNING or not self.lessons_store:
            return

        try:
            # Przygotuj dane lekcji
            situation = f"[{intent}] {context[:200]}..."  # Skrócony opis sytuacji

            if success:
                # Lekcja o sukcesie - zapisuj tylko jeśli coś ciekawego
                task_logs = self.state_manager.get_task(task_id)
                if not task_logs or len(task_logs.logs) <= 5:
                    # Proste zadanie, nie ma co zapisywać
                    logger.debug("Proste zadanie, pomijam zapis lekcji")
                    return
                # Było dużo iteracji, warto zapisać
                action = f"Zadanie wykonane pomyślnie po {len(task_logs.logs)} krokach"
                lesson_result = "SUKCES"
                feedback = f"Zadanie typu {intent} wymaga dokładnego planowania. Wynik: {result[:100]}..."
                tags = [intent, "sukces", "nauka"]
                reason = "success_multi_step"
            else:
                # Lekcja o błędzie - zawsze zapisuj
                action = f"Próba wykonania zadania typu {intent}"
                error_msg = error if error else "Unknown error"
                lesson_result = f"BŁĄD: {error_msg[:200]}"
                feedback = f"Unikaj powtórzenia tego błędu. Błąd: {error_msg[:300]}"
                tags = [intent, "błąd", "ostrzeżenie"]
                reason = "error"

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
                    "intent": intent,
                    "agent": agent.__class__.__name__ if agent else None,
                    "success": success,
                    "reason": reason,
                    "source": "orchestrator",
                    "store_knowledge": request.store_knowledge if request else None,
                    "learning_enabled": SETTINGS.ENABLE_META_LEARNING,
                },
            )

            self.state_manager.add_log(
                task_id, f"💡 Zapisano lekcję: {lesson.lesson_id}"
            )

            # Broadcast informacji o nowej lekcji
            if self.event_broadcaster:
                await self.event_broadcaster.broadcast_event(
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

    def append_learning_log(
        self,
        task_id: UUID,
        intent: str,
        prompt: str,
        result: str,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """
        Zapisuje wpis procesu nauki dla LLM-only do lokalnego JSONL.

        Args:
            task_id: ID zadania
            intent: Intencja
            prompt: Prompt użytkownika
            result: Rezultat
            success: Czy sukces
            error: Opcjonalny błąd
        """
        entry = {
            "task_id": str(task_id),
            "timestamp": datetime.now().isoformat(),
            "intent": intent,
            "tool_required": False,
            "success": success,
            "need": (prompt or "")[:MAX_LEARNING_SNIPPET],
            "outcome": (result or "")[:MAX_LEARNING_SNIPPET],
            "error": (error or "")[:MAX_LEARNING_SNIPPET],
            "fast_path_hint": "",
            "tags": [intent, "llm_only", "success" if success else "failure"],
        }

        try:
            LEARNING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LEARNING_LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self.state_manager.add_log(
                task_id, f"🧠 Zapisano wpis nauki do {LEARNING_LOG_PATH}"
            )
            collector = metrics_module.metrics_collector
            if collector:
                collector.increment_learning_logged()
        except Exception as exc:
            logger.warning(f"Nie udało się zapisać wpisu nauki: {exc}")
