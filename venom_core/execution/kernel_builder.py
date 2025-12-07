"""Moduł: kernel_builder - dynamiczne budowanie Semantic Kernel."""

from typing import Optional

from openai import AsyncOpenAI
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

from venom_core.config import SETTINGS
from venom_core.core.model_router import ModelRouter, ServiceId
from venom_core.core.prompt_manager import PromptManager
from venom_core.core.token_economist import TokenEconomist
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class KernelBuilder:
    """Builder do tworzenia Semantic Kernel z konfiguracją local-first i inteligentnym routingiem."""

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
        Buduje i konfiguruje Semantic Kernel.

        Args:
            task: Opcjonalny opis zadania dla inteligentnego routingu

        Returns:
            Skonfigurowane jądro Semantic Kernel

        Raises:
            ValueError: Jeśli konfiguracja jest niepoprawna
        """
        kernel = Kernel()

        if self.enable_multi_service:
            # Tryb multi-service - zarejestruj wszystkie dostępne serwisy
            logger.info("Inicjalizacja Kernel w trybie multi-service")
            self._register_all_services(kernel)
        else:
            # Tryb single-service - wybierz optymalny serwis
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
                    ServiceId.CLOUD_FAST.value: service_type if service_type in ["openai", "azure"] else "openai",
                    ServiceId.CLOUD_HIGH.value: service_type if service_type in ["openai", "azure"] else "openai",
                }

                service_type = service_mapping.get(recommended_service, service_type)

            logger.info(f"Inicjalizacja Kernel z typem serwisu: {service_type}")
            self._register_service(kernel, service_type)

        return kernel

    def _register_all_services(self, kernel: Kernel) -> None:
        """
        Rejestruje wszystkie dostępne serwisy LLM.

        Args:
            kernel: Jądro Semantic Kernel
        """
        # Lokalny model
        try:
            self._register_service(kernel, "local", service_id="local_llm")
            logger.info("Zarejestrowano serwis: local_llm")
        except Exception as e:
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
    ) -> None:
        """
        Rejestruje pojedynczy serwis LLM w kernelu.

        Args:
            kernel: Jądro Semantic Kernel
            service_type: Typ serwisu ('local', 'openai', 'azure')
            service_id: Opcjonalny ID serwisu (domyślnie typ)
            model_name: Opcjonalna nazwa modelu (domyślnie z ustawień)
        """
        service_id = service_id or service_type
        model_name = model_name or self.settings.LLM_MODEL_NAME

        if service_type == "local":
            # Konfiguracja dla lokalnego LLM (Ollama/vLLM/LocalAI)
            logger.debug(
                f"Konfiguracja lokalnego LLM: endpoint={self.settings.LLM_LOCAL_ENDPOINT}, model={model_name}"
            )

            # Utwórz klienta OpenAI z customowym endpoint
            async_client = AsyncOpenAI(
                api_key=self.settings.LLM_LOCAL_API_KEY,  # Konfigurowalny dummy key
                base_url=self.settings.LLM_LOCAL_ENDPOINT,
            )

            chat_service = OpenAIChatCompletion(
                service_id=service_id,
                ai_model_id=model_name,
                async_client=async_client,
            )

            kernel.add_service(chat_service)

        elif service_type == "openai":
            # Konfiguracja dla OpenAI Cloud
            if not self.settings.OPENAI_API_KEY:
                raise ValueError(
                    "OPENAI_API_KEY jest wymagany dla LLM_SERVICE_TYPE='openai'"
                )

            logger.debug(f"Konfiguracja OpenAI Cloud: model={model_name}")

            chat_service = OpenAIChatCompletion(
                service_id=service_id,
                ai_model_id=model_name,
                api_key=self.settings.OPENAI_API_KEY,
            )

            kernel.add_service(chat_service)

        elif service_type == "azure":
            # Placeholder dla Azure OpenAI (można rozszerzyć w przyszłości)
            raise NotImplementedError(
                "Azure OpenAI nie jest jeszcze zaimplementowany. Użyj 'local' lub 'openai'."
            )

        else:
            raise ValueError(
                f"Nieznany typ serwisu LLM: {service_type}. Dostępne: local, openai, azure"
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
