"""
Orchestrator package - zrefaktoryzowany moduł orkiestracji zadań.

Ten moduł został zdekomponowany na mniejsze, spójne komponenty:
- constants.py: Stałe konfiguracyjne
- session_handler.py: Zarządzanie sesją i kontekstem
- learning_handler.py: Meta-uczenie i logowanie lekcji
- middleware.py: Obsługa błędów i zdarzeń
- flow_coordinator.py: Koordynacja przepływów pracy
- kernel_manager.py: Zarządzanie kernelem LLM
- orchestrator_core.py: Główna logika orkiestracji

Eksportujemy główną klasę Orchestrator dla zachowania kompatybilności wstecznej.
"""

# Re-export dla backward compatibility
from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.intent_manager import IntentManager

from .constants import (
    COUNCIL_COLLABORATION_KEYWORDS,
    COUNCIL_TASK_THRESHOLD,
    ENABLE_COUNCIL_MODE,
    LEARNING_LOG_PATH,
    MAX_CONTEXT_CHARS,
    MAX_HIDDEN_PROMPTS_IN_CONTEXT,
    MAX_LESSONS_IN_CONTEXT,
    MAX_REPAIR_ATTEMPTS,
    SESSION_HISTORY_LIMIT,
)
from .orchestrator_core import Orchestrator, metrics_module

__all__ = [
    "Orchestrator",
    "IntentManager",
    "TaskDispatcher",
    "metrics_module",
    "LEARNING_LOG_PATH",
    "MAX_LESSONS_IN_CONTEXT",
    "MAX_HIDDEN_PROMPTS_IN_CONTEXT",
    "MAX_CONTEXT_CHARS",
    "MAX_REPAIR_ATTEMPTS",
    "COUNCIL_COLLABORATION_KEYWORDS",
    "COUNCIL_TASK_THRESHOLD",
    "ENABLE_COUNCIL_MODE",
    "SESSION_HISTORY_LIMIT",
]
