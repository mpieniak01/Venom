"""Moduł: base - abstrakcyjna klasa bazowa dla agentów Venom."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings

from venom_core.core.generation_params_adapter import GenerationParamsAdapter
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


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

    async def process_with_params(
        self, input_text: str, generation_params: Dict[str, Any]
    ) -> str:
        """
        Przetwarza wejście z niestandardowymi parametrami generacji.

        Domyślna implementacja deleguje do process(), ale podklasy mogą
        to nadpisać aby wykorzystać generation_params.

        Args:
            input_text: Treść zadania do przetworzenia
            generation_params: Parametry generacji (temperature, max_tokens, etc.)

        Returns:
            Wynik przetwarzania zadania
        """
        logger.debug(
            f"Agent {self.__class__.__name__} otrzymał parametry generacji, ale nie są one jeszcze obsługiwane"
        )
        return await self.process(input_text)

    def _create_execution_settings(
        self,
        generation_params: Optional[Dict[str, Any]] = None,
        default_settings: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> OpenAIChatPromptExecutionSettings:
        """
        Tworzy ustawienia wykonania z uwzględnieniem parametrów generacji.

        Args:
            generation_params: Parametry generacji od użytkownika
            default_settings: Domyślne parametry agenta
            **kwargs: Dodatkowe parametry (np. function_choice_behavior)

        Returns:
            Skonfigurowane OpenAIChatPromptExecutionSettings
        """
        # Wykryj aktywny provider
        runtime_info = get_active_llm_runtime()
        provider = runtime_info.provider

        # Połącz parametry użytkownika z domyślnymi
        merged_params = GenerationParamsAdapter.merge_with_defaults(
            generation_params, default_settings
        )

        # Adaptuj parametry do formatu providera
        adapted_params = GenerationParamsAdapter.adapt_params(merged_params, provider)

        if adapted_params:
            logger.debug(
                f"Utworzono ustawienia wykonania z parametrami: {adapted_params}"
            )

        # Połącz z dodatkowymi kwargs (np. function_choice_behavior)
        all_params = {**adapted_params, **kwargs}

        return OpenAIChatPromptExecutionSettings(**all_params)
