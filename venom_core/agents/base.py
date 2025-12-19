"""Moduł: base - abstrakcyjna klasa bazowa dla agentów Venom."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

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
            f"Agent {self.__class__.__name__} używa domyślnej implementacji process_with_params - "
            "parametry generacji zostaną zignorowane. Nadpisz tę metodę aby ich użyć."
        )
        return await self.process(input_text)

    def _get_safe_params_for_logging(
        self, generation_params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Filtruje parametry generacji do bezpiecznego logowania.

        Zwraca tylko kluczowe parametry, aby nie ujawniać wrażliwej konfiguracji.

        Args:
            generation_params: Pełny słownik parametrów generacji

        Returns:
            Słownik z tylko bezpiecznymi parametrami do logowania
        """
        if not generation_params:
            return {}

        safe_keys = ["temperature", "max_tokens", "top_p", "top_k", "repeat_penalty"]
        return {k: v for k, v in generation_params.items() if k in safe_keys}

    def _create_execution_settings(
        self,
        generation_params: Optional[Dict[str, Any]] = None,
        default_settings: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> OpenAIChatPromptExecutionSettings:
        """
        Tworzy ustawienia wykonania z uwzględnieniem parametrów generacji.

        Args:
            generation_params: Parametry generacji od użytkownika (mają najwyższy priorytet)
            default_settings: Domyślne parametry agenta
            **kwargs: Dodatkowe parametry niegeneracyjne (np. function_choice_behavior)

        Returns:
            Skonfigurowane OpenAIChatPromptExecutionSettings

        Note:
            Kolejność priorytetów: generation_params > default_settings > kwargs
            kwargs powinny zawierać tylko parametry niegeneracyjne
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

        # Najpierw kwargs (parametry niegeneracyjne), potem adapted_params (nadpisują jeśli konflikt)
        # To zapewnia, że generation_params użytkownika mają priorytet nad kwargs
        all_params = {**kwargs, **adapted_params}

        return OpenAIChatPromptExecutionSettings(**all_params)

    def _strip_system_messages(self, chat_history: ChatHistory) -> ChatHistory:
        """
        Zamienia wiadomości SYSTEM na prefiks w pierwszej wiadomości USER.

        Dzięki temu można używać modeli bez wsparcia roli SYSTEM.
        """
        system_messages = []
        non_system_messages = []

        for message in chat_history.messages:
            if message.role == AuthorRole.SYSTEM:
                system_messages.append(message.content)
            else:
                non_system_messages.append(message)

        combined_system = "\n\n".join([text for text in system_messages if text])

        new_history = ChatHistory()
        system_injected = False

        for message in non_system_messages:
            if (
                not system_injected
                and combined_system
                and message.role == AuthorRole.USER
            ):
                combined = (
                    f"{combined_system.strip()}\n\n[Pytanie użytkownika]\n"
                    f"{message.content}"
                )
                new_history.add_message(
                    ChatMessageContent(role=AuthorRole.USER, content=combined)
                )
                system_injected = True
            else:
                new_history.add_message(message)

        if combined_system and not system_injected:
            new_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.USER, content=combined_system.strip()
                )
            )

        return new_history

    async def _invoke_chat_with_fallbacks(
        self,
        chat_service,
        chat_history: ChatHistory,
        settings: OpenAIChatPromptExecutionSettings,
        enable_functions: bool = False,
    ):
        """
        Wywołuje LLM z fallbackami:
        - retry bez roli SYSTEM, jeśli model jej nie wspiera
        - retry bez function calling, jeśli model nie wspiera narzędzi
        """
        system_fallback_used = False
        functions_enabled = enable_functions

        for _ in range(3):
            try:
                kwargs = {
                    "chat_history": chat_history,
                    "settings": settings,
                }
                if functions_enabled:
                    kwargs["kernel"] = self.kernel

                return await chat_service.get_chat_message_content(**kwargs)
            except Exception as api_error:
                error_text = str(api_error).lower()
                inner = getattr(api_error, "inner_exception", None)
                if inner:
                    error_text += f" {str(inner).lower()}"

                handled = False

                if (
                    "system role not supported" in error_text
                    and not system_fallback_used
                ):
                    chat_history = self._strip_system_messages(chat_history)
                    system_fallback_used = True
                    handled = True

                if functions_enabled and (
                    "does not support tools" in error_text
                    or "kernel is required for function calls" in error_text
                ):
                    functions_enabled = False
                    handled = True

                if not handled:
                    raise

        raise RuntimeError("Nie udało się uzyskać odpowiedzi z LLM po fallbackach.")
