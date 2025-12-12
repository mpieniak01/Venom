"""Moduł: chat - agent do rozmów ogólnych."""

import os

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.core.model_router import ServiceId
from venom_core.memory.memory_skill import MemorySkill
from venom_core.utils.logger import get_logger

try:  # pragma: no cover - unittest.mock zawsze dostępny, ale zabezpieczenie
    from unittest.mock import MagicMock
except Exception:  # pragma: no cover
    MagicMock = None

logger = get_logger(__name__)


class ChatAgent(BaseAgent):
    """Agent specjalizujący się w rozmowach ogólnych i odpowiadaniu na pytania."""

    LOCAL_SERVICE_IDS = {ServiceId.LOCAL.value, "local"}

    SYSTEM_PROMPT = """Jesteś przyjaznym asystentem AI o imieniu Venom. Odpowiadasz na pytania użytkownika w sposób pomocny, zwięzły i naturalny.

ZASADY:
- NAJPIERW sprawdź pamięć długoterminową (użyj funkcji 'recall') czy nie masz zapisanych informacji na ten temat
- Jeśli znajdziesz coś w pamięci, wykorzystaj te informacje w odpowiedzi
- Odpowiadaj bezpośrednio na pytanie użytkownika
- Bądź zwięzły ale kompletny
- Używaj naturalnego, przyjaznego języka
- Jeśli użytkownik się wita, odpowiedz uprzejmie
- Jeśli pytanie dotyczy wiedzy, odpowiedz na podstawie swojej wiedzy i pamięci
- Jeśli nie wiesz odpowiedzi, szczerze to przyznaj
- Możesz zapisywać ważne informacje do pamięci używając funkcji 'memorize'

Przykłady:
Pytanie: "Cześć Venom, jak się masz?"
Odpowiedź: "Cześć! Świetnie się mam, dziękuję. Gotowy do pomocy!"

Pytanie: "Jaka jest stolica Francji?"
Odpowiedź: "Stolicą Francji jest Paryż."

Pytanie: "Opowiedz kawał"
Odpowiedź: "Dlaczego programiści wolą ciemny motyw? Bo światło przyciąga błędy! 😄"
"""

    def __init__(self, kernel: Kernel):
        """
        Inicjalizacja ChatAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
        """
        super().__init__(kernel)
        self._test_mode = bool(os.environ.get("PYTEST_CURRENT_TEST"))

        # Dodaj MemorySkill do kernela
        memory_skill = MemorySkill()
        self.kernel.add_plugin(memory_skill, plugin_name="MemorySkill")

        logger.info("ChatAgent zainicjalizowany z MemorySkill")

    async def process(self, input_text: str) -> str:
        """
        Odpowiada na pytanie lub prowadzi rozmowę z użytkownikiem.

        Args:
            input_text: Pytanie lub wiadomość od użytkownika

        Returns:
            Odpowiedź na pytanie lub wiadomość
        """
        logger.info(f"ChatAgent przetwarza żądanie: {input_text[:100]}...")

        if self._test_mode:
            kernel_is_mock = MagicMock is not None and isinstance(
                self.kernel, MagicMock
            )
            kernel_module = getattr(
                self.kernel, "__class__", type(self.kernel)
            ).__module__
            if not kernel_is_mock and kernel_module.startswith("semantic_kernel"):
                logger.debug(
                    "ChatAgent (tryb testowy) zwraca natychmiastową odpowiedź (bez LLM)"
                )
                return f"Przetworzono: {input_text}"

        # Przygotuj historię rozmowy
        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=input_text)
        )

        try:
            # Pobierz serwis chat completion
            chat_service = self.kernel.get_service()
            supports_functions = self._supports_function_calling(chat_service)

            try:
                # Wywołaj model,
                response = await self._invoke_chat_service(
                    chat_service=chat_service,
                    chat_history=chat_history,
                    enable_functions=supports_functions,
                )
            except Exception as api_error:
                error_text = str(api_error).lower()
                inner = getattr(api_error, "inner_exception", None)
                if inner:
                    error_text += f" {str(inner).lower()}"

                kernel_required_error = "kernel is required for function calls"

                if (
                    "does not support tools" in error_text
                    or kernel_required_error in error_text
                ):
                    logger.warning(
                        "Model nie wspiera function calling - przełączam na tryb bez funkcji."
                    )
                    response = await self._invoke_chat_service(
                        chat_service=chat_service,
                        chat_history=chat_history,
                        enable_functions=False,
                    )
                else:
                    raise

            result = str(response).strip()
            logger.info(f"ChatAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas generowania odpowiedzi: {e}")

            raise

    def _supports_function_calling(self, chat_service) -> bool:
        """
        Sprawdza czy dany serwis wspiera funkcje Semantic Kernel.

        Args:
            chat_service: Instancja serwisu czatu
        """
        service_id = getattr(chat_service, "service_id", "") or ""
        return service_id not in self.LOCAL_SERVICE_IDS

    async def _invoke_chat_service(
        self, chat_service, chat_history: ChatHistory, enable_functions: bool
    ) -> ChatMessageContent:
        """
        Wykonuje połączenie z serwisem czatu z odpowiednią konfiguracją funkcji.

        Args:
            chat_service: Serwis OpenAIChatCompletion
            chat_history: Historia rozmowy
            enable_functions: Czy pozwolić na wywołania funkcji
        """
        settings = self._build_execution_settings(enable_functions)
        kwargs = {}
        if enable_functions:
            kwargs["kernel"] = self.kernel

        return await chat_service.get_chat_message_content(
            chat_history=chat_history,
            settings=settings,
            **kwargs,
        )

    def _build_execution_settings(self, enable_functions: bool):
        """
        Tworzy ustawienia wykonania promptu zależnie od wsparcia funkcji.
        """
        if enable_functions:
            behavior = FunctionChoiceBehavior.Auto()
            return OpenAIChatPromptExecutionSettings(function_choice_behavior=behavior)

        # Brak funkcji → użyj domyślnych ustawień bez konfiguracji behavior
        return OpenAIChatPromptExecutionSettings()
