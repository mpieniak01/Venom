"""Stałe konfiguracyjne dla modułu Orchestrator."""

from pathlib import Path

from venom_core.core.flows.code_review import (
    MAX_REPAIR_ATTEMPTS as CODE_REVIEW_MAX_REPAIR_ATTEMPTS,
)
from venom_core.core.flows.council import (
    COUNCIL_COLLABORATION_KEYWORDS as COUNCIL_KEYWORDS,
)
from venom_core.core.flows.council import COUNCIL_TASK_THRESHOLD as COUNCIL_THRESHOLD
from venom_core.core.flows.council import ENABLE_COUNCIL_MODE as COUNCIL_ENABLE_FLAG

# Ustawienia dla pętli meta-uczenia
MAX_LESSONS_IN_CONTEXT = 3  # Maksymalna liczba lekcji dołączanych do promptu
LEARNING_LOG_PATH = Path("./data/learning/requests.jsonl")
MAX_LEARNING_SNIPPET = 1200
MAX_HIDDEN_PROMPTS_IN_CONTEXT = 2
SESSION_HISTORY_LIMIT = 12  # Maksymalna liczba wpisów historii sesji
MAX_CONTEXT_CHARS = 8000  # Przybliżony budżet znaków dla promptu
HISTORY_SUMMARY_TRIGGER_MSGS = 20
HISTORY_SUMMARY_TRIGGER_CHARS = 5000
SUMMARY_MAX_CHARS = 1000
LONG_BLOCK_THRESHOLD = 1200
DEFAULT_USER_ID = "user_default"
SUMMARY_MODEL_MAX_TOKENS = 400
SUMMARY_STRATEGY_DEFAULT = "llm_with_fallback"  # lub "heuristic_only"

# Alias dla kompatybilności z testami i innymi modułami
MAX_REPAIR_ATTEMPTS = CODE_REVIEW_MAX_REPAIR_ATTEMPTS
COUNCIL_COLLABORATION_KEYWORDS = COUNCIL_KEYWORDS
COUNCIL_TASK_THRESHOLD = COUNCIL_THRESHOLD
ENABLE_COUNCIL_MODE = COUNCIL_ENABLE_FLAG
