"""Moduł: kernel_builder - budowanie usług Microsoft Agent Framework."""

import importlib.util
from contextlib import aclosing
from typing import Any, Optional

from openai import AsyncOpenAI

from venom_core.config import SETTINGS
from venom_core.core.model_router import ModelRouter, ServiceId
from venom_core.core.prompt_manager import PromptManager
from venom_core.core.token_economist import TokenEconomist
from venom_core.execution.maf_runtime import AgentRuntime as Kernel
from venom_core.execution.maf_runtime import MafChatService
from venom_core.utils.llm_runtime import resolve_local_worker_endpoint
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def _safe_find_spec(module_name: str) -> Any | None:
    """Probe an optional provider without constructing clients or loading models."""
    try:
        return importlib.util.find_spec(module_name)
    except (ImportError, ValueError):
        return None


GOOGLE_AVAILABLE = _safe_find_spec("agent_framework_openai") is not None
GEMINI_OPENAI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"


class _DeferredVastChatService(MafChatService):
    """Keep an offline external selection without making it a startup dependency."""

    def __init__(self, service_id: str, runtime: Any):
        self.service_id = service_id
        self.ai_model_id = runtime.model_name
        from venom_core.services.vast_chat_runtime import selection

        self._target_id = runtime.runtime_id.rsplit(":", 1)[0]
        self._selection = selection()
        self._delegate: MafChatService | None = None
        self._endpoint: str | None = None

    async def _available_service(self) -> MafChatService:
        from venom_core.services.remote_provider_control import enabled
        from venom_core.services.vast_chat_runtime import (
            is_remote,
            runtime_override,
            selection,
        )

        if not enabled("vast_ollama"):
            raise ValueError("vast_chat_disabled")
        current = runtime_override()
        if (
            not is_remote(current)
            or selection() != self._selection
            or current.runtime_id.rsplit(":", 1)[0] != self._target_id
            or current.model_name != self.ai_model_id
        ):
            raise ValueError("vast_chat_target_changed")
        if not current.endpoint:
            raise ValueError("vast_chat_target_unavailable")
        if self._delegate is None or self._endpoint != current.endpoint:
            await self.aclose()
            self._delegate = MafChatService(
                service_id=self.service_id,
                ai_model_id=self.ai_model_id,
                async_client=AsyncOpenAI(
                    api_key="ollama", base_url=current.endpoint, max_retries=0
                ),
            )
            self._endpoint = current.endpoint
        return self._delegate

    async def get_chat_message_content(self, **kwargs):
        service = await self._available_service()
        return await service.get_chat_message_content(**kwargs)

    async def get_streaming_chat_message_contents(self, **kwargs):
        service = await self._available_service()
        async with aclosing(
            service.get_streaming_chat_message_contents(**kwargs)
        ) as stream:
            async for chunk in stream:
                yield chunk

    async def aclose(self) -> None:
        if self._delegate is not None:
            await self._delegate.aclose()
            self._delegate = None
            self._endpoint = None


class KernelBuilder:
    """Builder do tworzenia runtime MAF z konfiguracją local-first i inteligentnym routingiem."""

    def __init__(
        self,
        settings=None,
        enable_routing: bool = True,
        enable_multi_service: bool = False,
    ):
        """
        Inicjalizacja KernelBuilder.

        Args:
            settings: Opcjonalna konfiguracja (domyślnie SETTINGS z config.py)
            enable_routing: Czy włączyć inteligentny routing modeli (domyślnie True)
            enable_multi_service: Czy inicjalizować wiele serwisów jednocześnie (domyślnie False)
        """
        self.settings = settings or SETTINGS
        self.enable_routing = enable_routing
        self.enable_multi_service = enable_multi_service

        # Inicjalizuj komponenty zarządzania
        self.model_router = ModelRouter(enable_routing=enable_routing)
        self.prompt_manager = PromptManager()
        self.token_economist = TokenEconomist()

        logger.info(
            f"KernelBuilder zainicjalizowany (routing={enable_routing}, multi_service={enable_multi_service})"
        )

    def build_kernel(self, task: Optional[str] = None) -> Kernel:
        """
        Buduje i konfiguruje runtime MAF.

        Args:
            task: Opcjonalny opis zadania dla inteligentnego routingu

        Returns:
            Skonfigurowane jądro runtime MAF

        Raises:
            ValueError: Jeśli konfiguracja jest niepoprawna
        """
        kernel = Kernel()
        from venom_core.services.vast_chat_runtime import is_remote, runtime_override

        runtime = runtime_override()
        if is_remote(runtime):
            kernel.add_service(
                _DeferredVastChatService(
                    "local_llm" if self.enable_multi_service else "local", runtime
                )
            )
            return kernel

        if self.enable_multi_service:
            # Tryb multi-service - zarejestruj wszystkie dostępne serwisy
            logger.info("Inicjalizacja Kernel w trybie multi-service")
            self._register_all_services(kernel)
        else:
            # Tryb single-service - wybierz optymalny serwis
            service_type = self._resolve_single_service_type(task)
            self._register_service(kernel, service_type)

        return kernel

    def _resolve_single_service_type(self, task: Optional[str]) -> str:
        """Resolve routing and local-only policy for a single service."""
        service_type = self.settings.LLM_SERVICE_TYPE.lower()

        # Jeśli routing włączony i podano zadanie, użyj routera
        if self.enable_routing and task:
            routing_info = self.model_router.get_routing_info(task)
            recommended_service = routing_info["selected_service"]
            logger.info(
                f"Router rekomenduje: {recommended_service} (complexity={routing_info['complexity']})"
            )

            # Mapowanie ServiceId na typ serwisu
            service_mapping = {
                ServiceId.LOCAL.value: "local",
                ServiceId.CLOUD_FAST.value: (
                    service_type if service_type in ["openai", "azure"] else "openai"
                ),
                ServiceId.CLOUD_HIGH.value: (
                    service_type if service_type in ["openai", "azure"] else "openai"
                ),
            }

            service_type = service_mapping.get(recommended_service, service_type)

        force_local = getattr(self.settings, "FORCE_LOCAL_MODEL", False)
        ai_mode = getattr(self.settings, "AI_MODE", "")
        if force_local or ai_mode == "LOCAL":
            service_type = "local"
        logger.info(f"Inicjalizacja Kernel z typem serwisu: {service_type}")
        return service_type

    def _register_all_services(self, kernel: Kernel) -> None:
        """
        Rejestruje wszystkie dostępne serwisy LLM.

        Args:
            kernel: Jądro runtime MAF
        """
        # Lokalny model
        try:
            self._register_service(kernel, "local", service_id="local_llm")
            logger.info("Zarejestrowano serwis: local_llm")
        except Exception as e:
            from venom_core.services.vast_chat_runtime import selection

            if selection() is not None:
                raise
            if self.settings.LLM_SERVICE_TYPE.lower() == "onnx":
                raise
            active_server = str(getattr(self.settings, "ACTIVE_LLM_SERVER", "") or "")
            if active_server.strip().lower() == "onnx":
                raise
            logger.warning(f"Nie udało się zarejestrować serwisu local: {e}")

        # OpenAI (jeśli klucz API dostępny)
        if self.settings.OPENAI_API_KEY:
            try:
                # Cloud Fast - GPT-3.5
                self._register_service(
                    kernel,
                    "openai",
                    service_id="cloud_fast",
                    model_name="gpt-3.5-turbo",
                )
                logger.info("Zarejestrowano serwis: cloud_fast (GPT-3.5)")

                # Cloud High - GPT-4o
                self._register_service(
                    kernel, "openai", service_id="cloud_high", model_name="gpt-4o"
                )
                logger.info("Zarejestrowano serwis: cloud_high (GPT-4o)")
            except Exception as e:
                logger.warning(f"Nie udało się zarejestrować serwisów OpenAI: {e}")

    def _register_service(
        self,
        kernel: Kernel,
        service_type: str,
        service_id: Optional[str] = None,
        model_name: Optional[str] = None,
        enable_grounding: bool = False,
    ) -> None:
        """
        Rejestruje pojedynczy serwis LLM w kernelu.

        Args:
            kernel: Jądro runtime MAF
            service_type: Typ serwisu ('local', 'openai', 'azure', 'google')
            service_id: Opcjonalny ID serwisu (domyślnie typ)
            model_name: Opcjonalna nazwa modelu (domyślnie z ustawień)
            enable_grounding: Czy włączyć Google Search Grounding (tylko dla Google Gemini)
        """
        service_id = service_id or service_type
        model_name = model_name or self.settings.LLM_MODEL_NAME

        handlers = {
            "local": self._register_local_service,
            "onnx": self._register_onnx_service,
            "openai": self._register_openai_service,
            "google": self._register_google_service,
            "azure": self._register_azure_service,
        }
        handler = handlers.get(service_type)
        if handler is None:
            raise ValueError(
                f"Nieznany typ serwisu LLM: {service_type}. Dostępne: local, onnx, openai, google, azure"
            )
        handler(kernel, service_id, model_name, enable_grounding)

    def _register_local_service(
        self, kernel: Kernel, service_id: str, model_name: str, _enable_grounding: bool
    ) -> None:
        from venom_core.services.vast_chat_runtime import is_remote, runtime_override

        runtime = runtime_override()
        if is_remote(runtime):
            kernel.add_service(_DeferredVastChatService(service_id, runtime))
            return

        active_server = str(
            getattr(self.settings, "ACTIVE_LLM_SERVER", "") or ""
        ).lower()
        service_type = self.settings.LLM_SERVICE_TYPE.lower()
        if active_server == "onnx" or service_type == "onnx":
            self._register_onnx_service(
                kernel, service_id, model_name, _enable_grounding
            )
            return
        self._register_local_http_service(
            kernel, service_id, model_name, self.settings.LLM_LOCAL_ENDPOINT
        )

    def _register_onnx_service(
        self, kernel: Kernel, service_id: str, model_name: str, _enable_grounding: bool
    ) -> None:
        if not getattr(self.settings, "ONNX_LLM_ENABLED", False):
            raise ValueError("ONNX_LLM_ENABLED is disabled")
        endpoint = resolve_local_worker_endpoint(
            getattr(self.settings, "ONNX_LLM_ENDPOINT", None)
        )
        if not endpoint:
            raise ValueError("ONNX_LLM_ENDPOINT is required for the isolated worker")
        self._register_local_http_service(kernel, service_id, model_name, endpoint)

    def _register_local_http_service(
        self,
        kernel: Kernel,
        service_id: str,
        model_name: str,
        endpoint: str,
        *,
        max_retries: int | None = None,
        api_key: str | None = None,
    ) -> None:
        options: dict[str, Any] = (
            {"max_retries": max_retries} if max_retries is not None else {}
        )
        async_client = AsyncOpenAI(
            api_key=self.settings.LLM_LOCAL_API_KEY if api_key is None else api_key,
            base_url=endpoint,
            **options,
        )
        chat_service = MafChatService(
            service_id=service_id,
            ai_model_id=model_name,
            async_client=async_client,
        )
        kernel.add_service(chat_service)

    def _register_openai_service(
        self, kernel: Kernel, service_id: str, model_name: str, _enable_grounding: bool
    ) -> None:
        if not self.settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY jest wymagany dla LLM_SERVICE_TYPE='openai'"
            )
        logger.debug(f"Konfiguracja OpenAI Cloud: model={model_name}")
        chat_service = MafChatService(
            service_id=service_id,
            ai_model_id=model_name,
            api_key=self.settings.OPENAI_API_KEY,
        )
        chat_service.operator_provider = "openai"
        kernel.add_service(chat_service)

    def _register_google_service(
        self, kernel: Kernel, service_id: str, model_name: str, enable_grounding: bool
    ) -> None:
        if not GOOGLE_AVAILABLE:
            raise ValueError("Provider MAF OpenAI nie jest zainstalowany")
        if not self.settings.GOOGLE_API_KEY:
            raise ValueError(
                "GOOGLE_API_KEY jest wymagany dla LLM_SERVICE_TYPE='google'"
            )
        # Gemini officially exposes Chat Completions, streaming and function calls
        # on this endpoint. No legacy Google/SK connector is initialized.
        if enable_grounding:
            logger.debug("Grounding remains owned by the GoogleGrounding skill")
        chat_service = MafChatService(
            service_id=service_id,
            ai_model_id=model_name,
            api_key=self.settings.GOOGLE_API_KEY,
            base_url=GEMINI_OPENAI_ENDPOINT,
        )
        chat_service.operator_provider = "google"
        kernel.add_service(chat_service)

    def _register_azure_service(
        self,
        _kernel: Kernel,
        _service_id: str,
        model_name: str,
        _enable_grounding: bool,
    ) -> None:
        azure_endpoint = getattr(self.settings, "AZURE_OPENAI_ENDPOINT", None)
        azure_key = getattr(self.settings, "AZURE_OPENAI_KEY", None)
        if not azure_endpoint or not azure_key:
            raise NotImplementedError(
                "Azure OpenAI wymaga konfiguracji AZURE_OPENAI_ENDPOINT i AZURE_OPENAI_KEY. "
                "Obecnie wspierane: 'local', 'openai'. "
                "Azure jest dostępny jako opcja zapasowa po skonfigurowaniu credentials."
            )
        logger.info(
            f"Konfiguracja Azure OpenAI: endpoint={azure_endpoint}, model={model_name}"
        )
        raise NotImplementedError(
            "Azure OpenAI connector jest w trakcie implementacji. "
            "Credentials zostały wykryte, ale faktyczny serwis nie jest jeszcze zarejestrowany. "
            "Użyj 'local' lub 'openai'."
        )

    def get_model_router(self) -> ModelRouter:
        """
        Zwraca instancję ModelRouter.

        Returns:
            ModelRouter
        """
        return self.model_router

    def get_prompt_manager(self) -> PromptManager:
        """
        Zwraca instancję PromptManager.

        Returns:
            PromptManager
        """
        return self.prompt_manager

    def get_token_economist(self) -> TokenEconomist:
        """
        Zwraca instancję TokenEconomist.

        Returns:
            TokenEconomist
        """
        return self.token_economist
