"""Moduł: time_assistant - Agent do obsługi zapytań o aktualną godzinę."""

from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.assistant_skill import AssistantSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class TimeAssistantAgent(BaseAgent):
    """Agent zwracający aktualny czas bez użycia LLM."""

    disable_learning = True
    SHORT_HINTS = ("krótko", "tylko godzina", "hh:mm", "krócej")

    def __init__(self, kernel: Kernel):
        super().__init__(kernel)
        self.assistant_skill = AssistantSkill()

    async def process(self, input_text: str) -> str:
        normalized = (input_text or "").lower()
        format_type = (
            "short" if any(hint in normalized for hint in self.SHORT_HINTS) else "full"
        )
        try:
            return await self.assistant_skill.get_current_time(format_type=format_type)
        except Exception as exc:
            logger.error(f"Błąd w TimeAssistantAgent: {exc}")
            return f"✗ Błąd podczas pobierania czasu: {exc}"
