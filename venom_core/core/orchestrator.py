"""
Moduł: orchestrator - orkiestracja zadań w tle.

Ten moduł został zrefaktoryzowany i przeniesiony do pakietu orchestrator/.
Ten plik zachowany dla kompatybilności wstecznej - re-exportuje wszystko z pakietu.

Nowa struktura:
- venom_core/core/orchestrator/__init__.py - główny punkt wejścia pakietu
- venom_core/core/orchestrator/orchestrator_core.py - główna logika orkiestracji
- venom_core/core/orchestrator/constants.py - stałe konfiguracyjne
- venom_core/core/orchestrator/session_handler.py - zarządzanie sesją i kontekstem
- venom_core/core/orchestrator/learning_handler.py - meta-uczenie i logowanie lekcji
- venom_core/core/orchestrator/middleware.py - obsługa błędów i zdarzeń
- venom_core/core/orchestrator/flow_coordinator.py - koordynacja przepływów pracy
- venom_core/core/orchestrator/kernel_manager.py - zarządzanie kernelem LLM
"""

# Re-export everything from the package for backward compatibility
# Import from package __init__.py, not from self
from venom_core.core.orchestrator import (
    COUNCIL_COLLABORATION_KEYWORDS,
    COUNCIL_TASK_THRESHOLD,
    ENABLE_COUNCIL_MODE,
    MAX_CONTEXT_CHARS,
    MAX_HIDDEN_PROMPTS_IN_CONTEXT,
    MAX_LESSONS_IN_CONTEXT,
    MAX_REPAIR_ATTEMPTS,
    SESSION_HISTORY_LIMIT,
    Orchestrator,
)

# These aliases are for backward compatibility with older code
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
