"""Moduł: kernel_builder - dynamiczne budowanie Semantic Kernel."""

from openai import AsyncOpenAI
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class KernelBuilder:
    """Builder do tworzenia Semantic Kernel z konfiguracją local-first."""

    def __init__(self, settings=None):
        """
        Inicjalizacja KernelBuilder.

        Args:
            settings: Opcjonalna konfiguracja (domyślnie SETTINGS z config.py)
        """
        self.settings = settings or SETTINGS

    def build_kernel(self) -> Kernel:
        """
        Buduje i konfiguruje Semantic Kernel.

        Returns:
            Skonfigurowane jądro Semantic Kernel

        Raises:
            ValueError: Jeśli konfiguracja jest niepoprawna
        """
        kernel = Kernel()

        service_type = self.settings.LLM_SERVICE_TYPE.lower()
        model_name = self.settings.LLM_MODEL_NAME

        logger.info(f"Inicjalizacja Kernel z typem serwisu: {service_type}")

        if service_type == "local":
            # Konfiguracja dla lokalnego LLM (Ollama/vLLM/LocalAI)
            logger.info(
                f"Konfiguracja lokalnego LLM: endpoint={self.settings.LLM_LOCAL_ENDPOINT}, model={model_name}"
            )

            # Utwórz klienta OpenAI z customowym endpoint
            async_client = AsyncOpenAI(
                api_key=self.settings.LLM_LOCAL_API_KEY,  # Konfigurowalny dummy key
                base_url=self.settings.LLM_LOCAL_ENDPOINT,
            )

            chat_service = OpenAIChatCompletion(
                service_id="local_llm",
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

            logger.info(f"Konfiguracja OpenAI Cloud: model={model_name}")

            chat_service = OpenAIChatCompletion(
                service_id="openai",
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

        logger.info(f"Kernel zainicjalizowany pomyślnie z serwisem: {service_type}")
        return kernel
