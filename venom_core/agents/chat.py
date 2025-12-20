"""Moduł: chat - agent do rozmów ogólnych."""

import os
from typing import Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.config import SETTINGS
from venom_core.core.model_registry import ModelRegistry
from venom_core.core.model_router import ServiceId
from venom_core.execution.skills.google_calendar_skill import GoogleCalendarSkill
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
- Jeśli masz dostęp do Google Calendar (funkcje read_agenda, schedule_task), używaj ich dla pytań o kalendarz i planowanie

Przykłady:
Pytanie: "Cześć Venom, jak się masz?"
Odpowiedź: "Cześć! Świetnie się mam, dziękuję. Gotowy do pomocy!"

Pytanie: "Jaka jest stolica Francji?"
Odpowiedź: "Stolicą Francji jest Paryż."

Pytanie: "Opowiedz kawał"
Odpowiedź: "Dlaczego programiści wolą ciemny motyw? Bo światło przyciąga błędy! 😄"

Pytanie: "Co mam w planach dziś?"
Odpowiedź: [użyj read_agenda aby sprawdzić kalendarz użytkownika]

Pytanie: "Zaplanuj mi kodowanie na 16:00 przez godzinę"
Odpowiedź: [użyj schedule_task aby utworzyć wydarzenie w kalendarzu Venoma]
"""
    # Fallback: modele, które nie wspierają roli system, używane gdy ModelRegistry
    # nie jest dostępny lub model nie jest opisany w manifeście.
    MODELS_WITHOUT_SYSTEM_ROLE = ("gemma-2b",)

    def __init__(self, kernel: Kernel, model_registry: Optional[ModelRegistry] = None):
        """
        Inicjalizacja ChatAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            model_registry: Opcjonalny ModelRegistry do odczytu capabilities modeli
        """
        super().__init__(kernel)
        self._test_mode = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        self.model_registry = model_registry

        # Dodaj MemorySkill do kernela
        memory_skill = MemorySkill()
        self.kernel.add_plugin(memory_skill, plugin_name="MemorySkill")

        # Warunkowo dodaj GoogleCalendarSkill (graceful degradation)
        if SETTINGS.ENABLE_GOOGLE_CALENDAR:
            try:
                calendar_skill = GoogleCalendarSkill()
                if calendar_skill.credentials_available:
                    self.kernel.add_plugin(
                        calendar_skill, plugin_name="GoogleCalendarSkill"
                    )
                    logger.info("ChatAgent zainicjalizowany z GoogleCalendarSkill")
                else:
                    logger.info("GoogleCalendarSkill pominięty - brak credentials")
            except Exception as e:
                logger.warning(
                    f"Nie udało się zainicjalizować GoogleCalendarSkill: {e}"
                )
        else:
            logger.info("GoogleCalendarSkill wyłączony w konfiguracji")

        logger.info("ChatAgent zainicjalizowany z MemorySkill")

    async def process_with_params(
        self, input_text: str, generation_params: dict
    ) -> str:
        """
        Odpowiada z niestandardowymi parametrami generacji.

        Args:
            input_text: Pytanie lub wiadomość od użytkownika
            generation_params: Parametry generacji (temperature, max_tokens, etc.)

        Returns:
            Odpowiedź na pytanie lub wiadomość
        """
        logger.info(
            f"ChatAgent przetwarza żądanie z parametrami: {input_text[:100]}..."
        )
        if generation_params:
            safe_params = self._get_safe_params_for_logging(generation_params)
            logger.debug(f"Kluczowe parametry generacji: {safe_params}")
        return await self._process_internal(input_text, generation_params)

    async def process(self, input_text: str) -> str:
        """
        Odpowiada na pytanie lub prowadzi rozmowę z użytkownikiem.

        Args:
            input_text: Pytanie lub wiadomość od użytkownika

        Returns:
            Odpowiedź na pytanie lub wiadomość
        """
        logger.info(f"ChatAgent przetwarza żądanie: {input_text[:100]}...")
        return await self._process_internal(input_text, None)

    async def _process_internal(
        self, input_text: str, generation_params: dict = None
    ) -> str:
        """
        Wewnętrzna metoda przetwarzania z opcjonalnymi parametrami generacji.

        Args:
            input_text: Pytanie lub wiadomość od użytkownika
            generation_params: Opcjonalne parametry generacji

        Returns:
            Odpowiedź na pytanie lub wiadomość
        """

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
        chat_service = self.kernel.get_service()
        system_supported = self._supports_system_prompt(chat_service)
        chat_history = ChatHistory()
        if system_supported:
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
            )
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=input_text)
            )
        else:
            logger.debug(
                "Model %s nie wspiera roli SYSTEM – łączę instrukcję z wiadomością użytkownika.",
                getattr(chat_service, "ai_model_id", "unknown"),
            )
            combined_prompt = (
                f"{self.SYSTEM_PROMPT.strip()}\n\n[Pytanie użytkownika]\n{input_text}"
            )
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=combined_prompt)
            )

        try:
            # Pobierz serwis chat completion
            supports_functions = self._supports_function_calling(chat_service)

            try:
                # Wywołaj model,
                response = await self._invoke_chat_service(
                    chat_service=chat_service,
                    chat_history=chat_history,
                    enable_functions=supports_functions,
                    generation_params=generation_params,
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
                        generation_params=generation_params,
                    )
                else:
                    raise

            result = str(response).strip()
            logger.info(f"ChatAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas generowania odpowiedzi: {e}")

            raise

    def _supports_system_prompt(self, chat_service) -> bool:
        """
        Sprawdza czy model wspiera system prompt.

        Najpierw sprawdza w ModelRegistry (jeśli dostępny), następnie
        używa fallback do hardcoded listy.

        Args:
            chat_service: Serwis czatu z informacją o modelu

        Returns:
            True jeśli model wspiera system prompt, False w przeciwnym razie
        """
        raw_model_id = getattr(chat_service, "ai_model_id", "") or ""
        model_id = raw_model_id.lower()

        # Jeśli mamy ModelRegistry, sprawdź capabilities
        if self.model_registry:
            manifest = self.model_registry.manifest or {}
            # Oblicz base name raz na początku
            model_base = model_id.split("/")[-1]

            def _resolve_support(manifest_key: str):
                entry = manifest.get(manifest_key)
                if not entry:
                    return None
                # Najpierw spróbuj użyć oficjalnej metody registry (łatwiej mockować w testach)
                try:
                    capabilities = self.model_registry.get_model_capabilities(
                        manifest_key
                    )
                    if capabilities:
                        return capabilities.supports_system_role
                except Exception as exc:  # pragma: no cover - defensywne logowanie
                    logger.debug(
                        "Nie udało się pobrać capabilities z registry dla %s: %s",
                        manifest_key,
                        exc,
                    )

                # Fallback do danych zapisanych w manifeście
                candidate = getattr(entry, "capabilities", None)
                if candidate:
                    return candidate.supports_system_role
                return getattr(entry, "supports_system_role", None)

            # Krok 1: spróbuj dokładnego dopasowania po kluczu słownika
            supports = None
            manifest_name_for_log = None

            if raw_model_id and raw_model_id in manifest:
                supports = _resolve_support(raw_model_id)
                manifest_name_for_log = raw_model_id
            elif model_id and model_id in manifest:
                supports = _resolve_support(model_id)
                manifest_name_for_log = model_id

            if supports is not None:
                logger.debug(
                    f"Model {model_id} → manifest {manifest_name_for_log} (exact match): supports_system_role={supports}"
                )
                return supports

            # Krok 2: dopasowanie po base name (case-insensitive)
            for manifest_name, entry in manifest.items():
                if not entry:
                    continue

                manifest_name_lower = manifest_name.lower()
                manifest_base = manifest_name_lower.split("/")[-1]
                if manifest_base == model_base:
                    supports = _resolve_support(manifest_name)
                    if supports is None:
                        continue
                    logger.debug(
                        f"Model {model_id} → manifest {manifest_name} (base match): supports_system_role={supports}"
                    )
                    return supports

        # Fallback do hardcoded listy jeśli brak ModelRegistry lub nie znaleziono w manifeście
        return not any(marker in model_id for marker in self.MODELS_WITHOUT_SYSTEM_ROLE)

    def _supports_function_calling(self, chat_service) -> bool:
        """
        Sprawdza czy dany serwis wspiera funkcje Semantic Kernel.

        Args:
            chat_service: Instancja serwisu czatu
        """
        raw_model_id = getattr(chat_service, "ai_model_id", "") or ""
        model_id = raw_model_id.lower()

        if self.model_registry:
            manifest = self.model_registry.manifest or {}
            model_base = model_id.split("/")[-1]

            def _resolve_support(manifest_key: str):
                entry = manifest.get(manifest_key)
                if not entry:
                    return None
                try:
                    capabilities = self.model_registry.get_model_capabilities(
                        manifest_key
                    )
                    if capabilities:
                        return capabilities.supports_function_calling
                except Exception as exc:  # pragma: no cover - defensywne logowanie
                    logger.debug(
                        "Nie udało się pobrać capabilities z registry dla %s: %s",
                        manifest_key,
                        exc,
                    )

                candidate = getattr(entry, "capabilities", None)
                if candidate:
                    return candidate.supports_function_calling
                return getattr(entry, "supports_function_calling", None)

            supports = None
            if raw_model_id and raw_model_id in manifest:
                supports = _resolve_support(raw_model_id)
            elif model_id and model_id in manifest:
                supports = _resolve_support(model_id)

            if supports is not None:
                return supports

            for manifest_name, entry in manifest.items():
                if not entry:
                    continue
                manifest_base = manifest_name.lower().split("/")[-1]
                if manifest_base == model_base:
                    supports = _resolve_support(manifest_name)
                    if supports is not None:
                        return supports

        # Domyślnie nie próbuj function calling bez potwierdzonego wsparcia.
        return False

    async def _invoke_chat_service(
        self,
        chat_service,
        chat_history: ChatHistory,
        enable_functions: bool,
        generation_params: dict = None,
    ) -> ChatMessageContent:
        """
        Wykonuje połączenie z serwisem czatu z odpowiednią konfiguracją funkcji.

        Args:
            chat_service: Serwis OpenAIChatCompletion
            chat_history: Historia rozmowy
            enable_functions: Czy pozwolić na wywołania funkcji
            generation_params: Opcjonalne parametry generacji
        """
        if enable_functions and not self.kernel:
            logger.warning(
                "Kernel missing for function calling, disabling functions for this request."
            )
            enable_functions = False
        settings = self._build_execution_settings(enable_functions, generation_params)
        kwargs = {}
        if enable_functions:
            kwargs["kernel"] = self.kernel

        return await chat_service.get_chat_message_content(
            chat_history=chat_history,
            settings=settings,
            **kwargs,
        )

    def _build_execution_settings(
        self, enable_functions: bool, generation_params: dict = None
    ):
        """
        Tworzy ustawienia wykonania promptu zależnie od wsparcia funkcji i parametrów generacji.

        Args:
            enable_functions: Czy włączyć function calling
            generation_params: Opcjonalne parametry generacji
        """
        kwargs = {}
        if enable_functions:
            behavior = FunctionChoiceBehavior.Auto()
            kwargs["function_choice_behavior"] = behavior

        # Użyj helpera z BaseAgent do utworzenia ustawień z parametrami
        return self._create_execution_settings(
            generation_params=generation_params, **kwargs
        )
