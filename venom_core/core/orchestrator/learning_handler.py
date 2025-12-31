"""Obsługa procesu meta-uczenia i logowania lekcji."""

import json
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from venom_core.core import metrics as metrics_module
from venom_core.core.models import TaskRequest
from venom_core.utils.logger import get_logger

from .constants import LEARNING_LOG_PATH, MAX_LEARNING_SNIPPET

if TYPE_CHECKING:
    from venom_core.core.lessons_manager import LessonsManager
    from venom_core.core.state_manager import StateManager

logger = get_logger(__name__)


class LearningHandler:
    """Zarządza procesem meta-uczenia i logowaniem lekcji."""

    NON_LEARNING_INTENTS = {
        "TIME_REQUEST",
        "INFRA_STATUS",
    }

    def __init__(
        self, state_manager: "StateManager", lessons_manager: "LessonsManager"
    ):
        """
        Inicjalizacja LearningHandler.

        Args:
            state_manager: Menedżer stanu zadań
            lessons_manager: Menedżer lekcji
        """
        self.state_manager = state_manager
        self.lessons_manager = lessons_manager

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
        # Deleguj do LessonsManager
        return self.lessons_manager.should_store_lesson(request, intent, agent)

    def should_log_learning(
        self,
        request: TaskRequest,
        intent: str,
        tool_required: bool,
        agent=None,
    ) -> bool:
        """
        Sprawdza czy należy zapisać wpis procesu nauki (LLM-only).

        Zachowane dla kompatybilności z testami.
        """
        if not request.store_knowledge:
            return False
        if tool_required:
            return False
        if intent in self.NON_LEARNING_INTENTS:
            return False
        if agent and getattr(agent, "disable_learning", False):
            return False
        return True

    def append_learning_log(
        self,
        task_id: UUID,
        intent: str,
        prompt: str,
        result: str,
        success: bool,
        error: str = "",
    ) -> None:
        """
        Zapisuje wpis procesu nauki do JSONL.

        Zachowane dla kompatybilności z testami.
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
