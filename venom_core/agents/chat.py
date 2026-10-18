"""Moduł: chat - agent do rozmów ogólnych."""

from typing import Any, Optional

from venom_core.agents.base import BaseAgent
from venom_core.config import SETTINGS
from venom_core.core.model_registry import ModelRegistry
from venom_core.core.model_router import ServiceId
from venom_core.execution.agent_contracts import ConversationHistory as ChatHistory
from venom_core.execution.agent_contracts import (
    ConversationMessage as ChatMessageContent,
)
from venom_core.execution.agent_contracts import MessageRole as AuthorRole
from venom_core.execution.agent_contracts import ToolPolicy as FunctionChoiceBehavior
from venom_core.execution.maf_runtime import AgentRuntime as Kernel
from venom_core.execution.skills.google_calendar_skill import GoogleCalendarSkill
from venom_core.memory.memory_skill import MemorySkill
from venom_core.utils.llm_runtime import get_active_llm_runtime
from venom_core.utils.logger import get_logger

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
    LOCAL_SYSTEM_PROMPT = """Jesteś asystentem AI o imieniu Venom.

Zasady:
- Odpowiadaj krótko i rzeczowo po polsku.
- Jeśli nie wiesz, przyznaj to.
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
        self, input_text: str, generation_params: dict[str, Any]
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
        self, input_text: str, generation_params: Optional[dict[str, Any]] = None
    ) -> str:
        """
        Wewnętrzna metoda przetwarzania z opcjonalnymi parametrami generacji.

        Args:
            input_text: Pytanie lub wiadomość od użytkownika
            generation_params: Opcjonalne parametry generacji

        Returns:
            Odpowiedź na pytanie lub wiadomość
        """

        chat_service: Any = self.kernel.get_service()
        chat_history = self._build_chat_history_for_runtime(input_text, chat_service)

        try:
            allow_functions = self._resolve_function_call_policy(
                chat_service=chat_service, user_input=input_text
            )
            response = await self._invoke_with_tool_fallback(
                chat_service=chat_service,
                chat_history=chat_history,
                allow_functions=allow_functions,
                generation_params=generation_params,
            )
            result = self._extract_response_text(response)
            logger.info(f"ChatAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas generowania odpowiedzi: {e}")

            raise

    def _build_chat_history_for_runtime(
        self, input_text: str, chat_service: Any
    ) -> ChatHistory:
        runtime = get_active_llm_runtime()
        use_compact = (
            runtime.provider in ("vllm", "ollama", "local")
            and SETTINGS.VLLM_MAX_MODEL_LEN
            and SETTINGS.VLLM_MAX_MODEL_LEN <= 512
        )
        system_prompt = self.LOCAL_SYSTEM_PROMPT if use_compact else self.SYSTEM_PROMPT
        system_supported = self._supports_system_prompt(chat_service)

        chat_history = ChatHistory()
        if system_supported:
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.SYSTEM, content=system_prompt)
            )
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=input_text)
            )
            return chat_history

        logger.debug(
            "Model %s nie wspiera roli SYSTEM – łączę instrukcję z wiadomością użytkownika.",
            getattr(chat_service, "ai_model_id", "unknown"),
        )
        combined_prompt = (
            f"{system_prompt.strip()}\n\n[Pytanie użytkownika]\n{input_text}"
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=combined_prompt)
        )
        return chat_history

    def _resolve_function_call_policy(
        self, *, chat_service: Any, user_input: str
    ) -> bool:
        supports_functions = self._supports_function_calling(chat_service)
        return supports_functions and self._should_use_functions(user_input)

    async def _invoke_with_tool_fallback(
        self,
        *,
        chat_service: Any,
        chat_history: ChatHistory,
        allow_functions: bool,
        generation_params: Optional[dict[str, Any]],
    ):
        try:
            return await self._invoke_chat_service(
                chat_service=chat_service,
                chat_history=chat_history,
                enable_functions=allow_functions,
                generation_params=generation_params,
            )
        except Exception as api_error:
            error_text = self._build_error_text(api_error)
            kernel_required_error = "kernel is required for function calls"
            if (
                "does not support tools" in error_text
                or kernel_required_error in error_text
            ):
                logger.warning(
                    "Model nie wspiera function calling - przełączam na tryb bez funkcji."
                )
                return await self._invoke_chat_service(
                    chat_service=chat_service,
                    chat_history=chat_history,
                    enable_functions=False,
                    generation_params=generation_params,
                )
            raise

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        return str(response).strip()

    def _should_use_functions(self, user_input: str) -> bool:
        """
        Włącz funkcje tylko gdy pytanie wyraźnie dotyczy plików/repo/struktury.
        """
        if not user_input:
            return False
        lowered = user_input.lower()
        keywords = [
            "plik",
            "pliki",
            "folder",
            "katalog",
            "repo",
            "repozytorium",
            "git",
            "branch",
            "commit",
            "diff",
            "path",
            "directory",
            "file",
            "files",
            "tree",
            "list files",
            "lista plik",
            "struktura",
            "zawartosc",
        ]
        return any(keyword in lowered for keyword in keywords)

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
        raw_model_id, model_id = self._get_model_ids(chat_service)
        supports, source = self._resolve_model_capability(
            raw_model_id=raw_model_id,
            model_id=model_id,
            capability_attr="supports_system_role",
        )
        if supports is not None:
            logger.debug(
                "Model %s → manifest %s: supports_system_role=%s",
                model_id,
                source,
                supports,
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
        # Lokalny endpoint (Ollama/vLLM) nie ma jeszcze stabilnego wsparcia function-calling
        # w naszej konfiguracji – wymuszenie tools="auto" generuje błąd 400.
        from venom_core.config import SETTINGS

        if SETTINGS.LLM_SERVICE_TYPE == "local":
            return False

        raw_model_id, model_id = self._get_model_ids(chat_service)
        supports, _ = self._resolve_model_capability(
            raw_model_id=raw_model_id,
            model_id=model_id,
            capability_attr="supports_function_calling",
        )
        if supports is not None:
            return supports

        # Domyślnie nie próbuj function calling bez potwierdzonego wsparcia.
        return False

    def _get_model_ids(self, chat_service) -> tuple[str, str]:
        raw_model_id = getattr(chat_service, "ai_model_id", "") or ""
        return raw_model_id, raw_model_id.lower()

    def _resolve_model_capability(
        self,
        *,
        raw_model_id: str,
        model_id: str,
        capability_attr: str,
    ) -> tuple[Optional[bool], Optional[str]]:
        model_registry = self.model_registry
        if not model_registry:
            return None, None

        manifest = model_registry.manifest or {}
        exact_keys = [
            key for key in (raw_model_id, model_id) if key and key in manifest
        ]
        for key in exact_keys:
            support = self._resolve_manifest_capability(
                model_registry=model_registry,
                manifest=manifest,
                manifest_key=key,
                capability_attr=capability_attr,
            )
            if support is not None:
                return support, f"{key} (exact match)"

        model_base = model_id.split("/")[-1]
        for manifest_name, entry in manifest.items():
            if not entry:
                continue
            if manifest_name.lower().split("/")[-1] != model_base:
                continue
            support = self._resolve_manifest_capability(
                model_registry=model_registry,
                manifest=manifest,
                manifest_key=manifest_name,
                capability_attr=capability_attr,
            )
            if support is not None:
                return support, f"{manifest_name} (base match)"

        return None, None

    def _resolve_manifest_capability(
        self,
        *,
        model_registry,
        manifest: dict[str, Any],
        manifest_key: str,
        capability_attr: str,
    ) -> Optional[bool]:
        entry = manifest.get(manifest_key)
        if not entry:
            return None
        try:
            capabilities = model_registry.get_model_capabilities(manifest_key)
            if capabilities:
                return getattr(capabilities, capability_attr, None)
        except Exception as exc:  # pragma: no cover - defensywne logowanie
            logger.debug(
                "Nie udało się pobrać capabilities z registry dla %s: %s",
                manifest_key,
                exc,
            )

        candidate = getattr(entry, "capabilities", None)
        if candidate:
            return getattr(candidate, capability_attr, None)
        return getattr(entry, capability_attr, None)

    async def _invoke_chat_service(
        self,
        chat_service,
        chat_history: ChatHistory,
        enable_functions: bool,
        generation_params: Optional[dict[str, Any]] = None,
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
        return await self._invoke_chat_with_fallbacks(
            chat_service=chat_service,
            chat_history=chat_history,
            settings=settings,
            enable_functions=enable_functions,
        )

    def _build_execution_settings(
        self, enable_functions: bool, generation_params: Optional[dict[str, Any]] = None
    ):
        """
        Tworzy ustawienia wykonania promptu zależnie od wsparcia funkcji i parametrów generacji.

        Args:
            enable_functions: Czy włączyć function calling
            generation_params: Opcjonalne parametry generacji
        """
        kwargs: dict[str, Any] = {}
        if enable_functions:
            behavior = FunctionChoiceBehavior.Auto()
            kwargs["function_choice_behavior"] = behavior

        # Użyj helpera z BaseAgent do utworzenia ustawień z parametrami
        return self._create_execution_settings(
            generation_params=generation_params, **kwargs
        )
