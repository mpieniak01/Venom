"""Moduł: base - abstrakcyjna klasa bazowa dla agentów Venom."""

from abc import ABC, abstractmethod

from semantic_kernel import Kernel


class BaseAgent(ABC):
    """Abstrakcyjna klasa bazowa dla wszystkich agentów Venom."""

    def __init__(self, kernel: Kernel, role: str | None = None):
        """
        Inicjalizacja agenta.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            role: Opcjonalna nazwa roli agenta (wykorzystywana m.in. w promptach)
        """
        self.kernel = kernel
        self.role = role or self.__class__.__name__

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
