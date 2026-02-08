"""Moduł: unsupported - agent zwracający informację o braku obsługi."""

import asyncio

from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class UnsupportedAgent(BaseAgent):
    """Agent dla zadań poza zakresem narzędzi lub intencji."""

    disable_learning = True

    def __init__(self, kernel: Kernel):
        super().__init__(kernel)

    async def process(self, input_text: str) -> str:
        # Oddaj kontrolę pętli zdarzeń: metoda logicznie synchroniczna implementuje interfejs async
        await asyncio.sleep(0)

        logger.info("UnsupportedAgent obsługuje zapytanie bez dopasowania.")
        return (
            "Nie mam jeszcze umiejętności do tego zadania. "
            "Możesz doprecyzować cel albo wybrać jedną z dostępnych funkcji?"
        )
