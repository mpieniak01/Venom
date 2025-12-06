"""Moduł: base - abstrakcyjna klasa bazowa dla agentów Venom."""

from abc import ABC, abstractmethod

from semantic_kernel import Kernel


class BaseAgent(ABC):
    """Abstrakcyjna klasa bazowa dla wszystkich agentów Venom."""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja agenta.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        self.kernel = kernel

    @abstractmethod
    async def process(self, input_text: str) -> str:
        """
        Przetwarza wejście i zwraca wynik.

        Args:
            input_text: Treść zadania do przetworzenia

        Returns:
            Wynik przetwarzania zadania
        """
        pass
