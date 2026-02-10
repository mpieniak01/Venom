"""Moduł: base - abstrakcyjna klasa bazowa dla agentów Venom."""

import re
from abc import ABC, abstractmethod
from contextvars import ContextVar, Token
from typing import Any, Callable, Dict, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.config import SETTINGS
from venom_core.core.generation_params_adapter import GenerationParamsAdapter
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

_llm_stream_callback: ContextVar[Optional[Callable[[str], None]]] = ContextVar(
    "llm_stream_callback", default=None
)


def set_llm_stream_callback(callback: Optional[Callable[[str], None]]) -> Token:
    return _llm_stream_callback.set(callback)


def reset_llm_stream_callback(token: Token) -> None:
    _llm_stream_callback.reset(token)


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
    async def process(self, input_text: str) -> str:  # pragma: no cover
        """
        Przetwarza wejście i zwraca wynik.

        Args:
            input_text: Treść zadania do przetworzenia

        Returns:
            Wynik przetwarzania zadania
        """
        raise NotImplementedError("Subclasses must implement process() method")

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

        # Lokalny endpoint (vLLM/Ollama) nie obsługuje stabilnie tools/function-calling – wyłącz.
        if provider in ("vllm", "ollama", "local"):
            if "function_choice_behavior" in kwargs:
                kwargs.pop("function_choice_behavior", None)

        # Uwzględnij override parametrów per runtime/model
        overrides = GenerationParamsAdapter.get_overrides(
            runtime_info.provider, runtime_info.model_name
        )
        defaults_with_overrides = GenerationParamsAdapter.merge_with_defaults(
            overrides, default_settings
        )

        # Połącz parametry użytkownika z domyślnymi + override
        merged_params = GenerationParamsAdapter.merge_with_defaults(
            generation_params, defaults_with_overrides
        )

        # Ogranicz max_tokens dla vLLM, aby nie przekraczać małego kontekstu.
        if provider == "vllm":
            max_ctx = getattr(SETTINGS, "VLLM_MAX_MODEL_LEN", 0) or 0
            if max_ctx > 0:
                safe_cap = max(64, max_ctx // 4)
                current = merged_params.get("max_tokens")
                if current is None or current > safe_cap:
                    merged_params["max_tokens"] = safe_cap

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

        for attempt in range(1, 4):
            logger.debug(
                "LLM fallback attempt %s/3 (functions=%s, system_fallback_used=%s)",
                attempt,
                functions_enabled,
                system_fallback_used,
            )
            try:
                return await self._invoke_chat_once(
                    chat_service=chat_service,
                    chat_history=chat_history,
                    settings=settings,
                    functions_enabled=functions_enabled,
                )
            except Exception as api_error:
                (
                    handled,
                    chat_history,
                    functions_enabled,
                    system_fallback_used,
                ) = self._handle_chat_api_error(
                    api_error=api_error,
                    chat_history=chat_history,
                    settings=settings,
                    functions_enabled=functions_enabled,
                    system_fallback_used=system_fallback_used,
                )
                if not handled:
                    raise

        raise RuntimeError("Nie udało się uzyskać odpowiedzi z LLM po fallbackach.")

    async def _invoke_chat_once(
        self,
        *,
        chat_service,
        chat_history: ChatHistory,
        settings: OpenAIChatPromptExecutionSettings,
        functions_enabled: bool,
    ):
        kwargs = {"chat_history": chat_history, "settings": settings}
        if functions_enabled:
            kwargs["kernel"] = self.kernel

        stream_callback = _llm_stream_callback.get()
        if (
            stream_callback
            and not functions_enabled
            and hasattr(chat_service, "get_streaming_chat_message_contents")
        ):
            return await self._invoke_chat_streaming(
                chat_service, stream_callback, **kwargs
            )

        return await chat_service.get_chat_message_content(**kwargs)

    def _handle_chat_api_error(
        self,
        *,
        api_error: Exception,
        chat_history: ChatHistory,
        settings: OpenAIChatPromptExecutionSettings,
        functions_enabled: bool,
        system_fallback_used: bool,
    ) -> tuple[bool, ChatHistory, bool, bool]:
        error_text = self._build_error_text(api_error)
        handled = self._apply_context_window_fallback(error_text, settings)

        if self._should_apply_system_fallback(error_text, system_fallback_used):
            chat_history = self._strip_system_messages(chat_history)
            system_fallback_used = True
            handled = True

        if functions_enabled and self._should_disable_functions(error_text):
            functions_enabled = False
            self._disable_function_choice_behavior(settings, error_text)
            handled = True

        return handled, chat_history, functions_enabled, system_fallback_used

    def _build_error_text(self, api_error: Exception) -> str:
        error_text = str(api_error).lower()
        inner = getattr(api_error, "inner_exception", None)
        if inner:
            error_text += f" {str(inner).lower()}"
        return error_text

    def _apply_context_window_fallback(
        self,
        error_text: str,
        settings: OpenAIChatPromptExecutionSettings,
    ) -> bool:
        token_match = re.search(
            r"maximum context length is (\d+) tokens.*request has (\d+) input tokens",
            error_text,
        )
        if not token_match:
            return False
        try:
            max_ctx = int(token_match.group(1))
            input_tokens = int(token_match.group(2))
            safe_max = max(16, max_ctx - input_tokens - 8)
            if safe_max <= 0:
                return False
            settings.max_tokens = safe_max
            logger.warning(
                "Zmniejszam max_tokens do %s (max_ctx=%s, input=%s).",
                safe_max,
                max_ctx,
                input_tokens,
            )
            return True
        except Exception:
            logger.debug(
                "Nie udało się ustawić max_tokens w settings po błędzie kontekstu."
            )
            return False

    def _should_apply_system_fallback(
        self,
        error_text: str,
        system_fallback_used: bool,
    ) -> bool:
        return "system role not supported" in error_text and not system_fallback_used

    def _should_disable_functions(self, error_text: str) -> bool:
        return any(
            marker in error_text
            for marker in (
                "does not support tools",
                "kernel is required for function calls",
                'auto" tool choice requires',
                "auto tool choice requires",
            )
        )

    def _disable_function_choice_behavior(
        self,
        settings: OpenAIChatPromptExecutionSettings,
        error_text: str,
    ) -> None:
        if not hasattr(settings, "function_choice_behavior"):
            return
        try:
            settings.function_choice_behavior = None
        except Exception:
            if "auto tool choice requires" in error_text:
                logger.debug(
                    "Nie udało się wyłączyć function_choice_behavior po błędzie auto tool choice."
                )
            else:
                logger.debug(
                    "Nie udało się wyłączyć function_choice_behavior w settings."
                )

    async def _invoke_chat_streaming(self, chat_service, stream_callback, **kwargs):
        """
        Wywołuje LLM w trybie streaming i zwraca złożoną odpowiedź.

        stream_callback jest wywoływany dla każdego fragmentu tekstu.
        """
        collected = []
        stream_callback_enabled = True
        async for chunk_list in chat_service.get_streaming_chat_message_contents(
            **kwargs
        ):
            for chunk in chunk_list:
                text = getattr(chunk, "content", None) or ""
                if not text:
                    continue
                collected.append(text)
                if stream_callback_enabled:
                    try:
                        stream_callback(text)
                    except Exception:
                        logger.debug(
                            "stream_callback zakończył się błędem, pomijam dalsze wywołania."
                        )
                        stream_callback_enabled = False

        return ChatMessageContent(role=AuthorRole.ASSISTANT, content="".join(collected))
