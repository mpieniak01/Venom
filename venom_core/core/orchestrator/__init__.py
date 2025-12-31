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

from .orchestrator_core import Orchestrator

# Re-export dla backward compatibility
from .constants import (
    COUNCIL_COLLABORATION_KEYWORDS,
    COUNCIL_TASK_THRESHOLD,
    ENABLE_COUNCIL_MODE,
    MAX_CONTEXT_CHARS,
    MAX_HIDDEN_PROMPTS_IN_CONTEXT,
    MAX_LESSONS_IN_CONTEXT,
    MAX_REPAIR_ATTEMPTS,
    SESSION_HISTORY_LIMIT,
)

__all__ = [
    "Orchestrator",
    "MAX_LESSONS_IN_CONTEXT",
    "MAX_HIDDEN_PROMPTS_IN_CONTEXT",
    "MAX_CONTEXT_CHARS",
    "MAX_REPAIR_ATTEMPTS",
    "COUNCIL_COLLABORATION_KEYWORDS",
    "COUNCIL_TASK_THRESHOLD",
    "ENABLE_COUNCIL_MODE",
    "SESSION_HISTORY_LIMIT",
]
