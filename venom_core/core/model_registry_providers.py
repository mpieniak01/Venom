"""Providery i helpery dla ModelRegistry."""

import abc
import asyncio
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.core.model_registry_clients import HuggingFaceClient, OllamaClient
from venom_core.core.model_registry_types import (
    GenerationParameter,
    ModelCapabilities,
    ModelMetadata,
    ModelProvider,
    ModelStatus,
)
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)


def resolve_hf_token() -> Optional[str]:
    token = getattr(SETTINGS, "HF_TOKEN", None)
    if token is None:
        return None
    if hasattr(token, "get_secret_value"):
        token_value = token.get_secret_value()
    else:
        token_value = token
    return token_value or None


def create_default_generation_schema() -> Dict[str, GenerationParameter]:
    """Tworzy domyślny schemat parametrów generacji dla modeli."""
    return {
        "temperature": GenerationParameter(
            type="float",
            default=0.7,
            min=0.0,
            max=2.0,
            desc="Kreatywność modelu (0 = deterministyczny, 2 = bardzo kreatywny)",
        ),
        "max_tokens": GenerationParameter(
            type="int",
            default=2048,
            min=128,
            max=8192,
            desc="Maksymalna liczba tokenów w odpowiedzi",
        ),
        "top_p": GenerationParameter(
            type="float",
            default=0.9,
            min=0.0,
            max=1.0,
            desc="Nucleus sampling - próg kumulatywnego prawdopodobieństwa",
        ),
        "top_k": GenerationParameter(
            type="int",
            default=40,
            min=1,
            max=100,
            desc="Top-K sampling - liczba najlepszych tokenów do rozważenia",
        ),
        "repeat_penalty": GenerationParameter(
            type="float",
            default=1.1,
            min=1.0,
            max=2.0,
            desc="Kara za powtarzanie tokenów",
        ),
    }


class BaseModelProvider(abc.ABC):
    """Bazowa klasa dla providerów modeli."""

    @abc.abstractmethod
    async def list_available_models(self) -> List[ModelMetadata]:
        """Lista dostępnych modeli."""

    @abc.abstractmethod
    async def install_model(
        self, model_name: str, progress_callback: Optional[Callable] = None
    ) -> bool:
        """Instaluje model."""

    @abc.abstractmethod
    async def remove_model(self, model_name: str) -> bool:
        """Usuwa model."""

    @abc.abstractmethod
    async def get_model_info(self, model_name: str) -> Optional[ModelMetadata]:
        """Pobiera informacje o modelu."""


class OllamaModelProvider(BaseModelProvider):
    """Provider dla modeli Ollama."""

    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = (endpoint or build_http_url("localhost", 11434)).rstrip("/")
        self.client = OllamaClient(endpoint=self.endpoint)

    async def list_available_models(self) -> List[ModelMetadata]:
        """Lista modeli z Ollama."""
        models = []
        try:
            data = await self.client.list_tags()
            for model in data.get("models", []):
                name = model.get("name", "unknown")
                size_bytes = model.get("size", 0)

                generation_schema = create_default_generation_schema()
                if re.search(r"llama-?3(?:[:\-]|$)", name, re.IGNORECASE):
                    generation_schema["temperature"] = GenerationParameter(
                        type="float",
                        default=0.7,
                        min=0.0,
                        max=1.0,
                        desc="Kreatywność modelu (0 = deterministyczny, 1 = kreatywny)",
                    )

                models.append(
                    ModelMetadata(
                        name=name,
                        provider=ModelProvider.OLLAMA,
                        display_name=name,
                        size_gb=size_bytes / (1024**3) if size_bytes else None,
                        status=ModelStatus.INSTALLED,
                        runtime="ollama",
                        capabilities=ModelCapabilities(
                            generation_schema=generation_schema,
                        ),
                    )
                )
        except Exception as e:
            logger.warning(f"Nie udało się pobrać listy modeli z Ollama: {e}")
        return models

    async def install_model(
        self, model_name: str, progress_callback: Optional[Callable] = None
    ) -> bool:
        """Instaluje model przez `ollama pull`."""
        if not model_name or not re.match(r"^[\w\-.:]+$", model_name):
            logger.error(f"Nieprawidłowa nazwa modelu Ollama: {model_name}")
            return False

        try:
            logger.info(f"Rozpoczynam pobieranie modelu Ollama: {model_name}")
            success = await self.client.pull_model(model_name, progress_callback)
            if success:
                logger.info(f"✅ Model {model_name} pobrany pomyślnie")
            return success
        except Exception as e:
            logger.error(f"Błąd podczas pobierania modelu: {e}")
            return False

    async def remove_model(self, model_name: str) -> bool:
        """Usuwa model z Ollama."""
        if not model_name or not re.match(r"^[\w\-.:]+$", model_name):
            logger.error(f"Nieprawidłowa nazwa modelu: {model_name}")
            return False

        try:
            success = await self.client.remove_model(model_name)
            if success:
                logger.info(f"✅ Model {model_name} usunięty z Ollama")
            return success
        except Exception as e:
            logger.error(f"Błąd podczas usuwania modelu: {e}")
            return False

    async def get_model_info(self, model_name: str) -> Optional[ModelMetadata]:
        """Pobiera informacje o modelu z Ollama."""
        models = await self.list_available_models()
        for model in models:
            if model.name == model_name:
                return model
        return None


class HuggingFaceModelProvider(BaseModelProvider):
    """Provider dla modeli HuggingFace."""

    def __init__(self, cache_dir: Optional[str] = None, token: Optional[str] = None):
        self.cache_dir = Path(cache_dir or "./models_cache/hf")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.client = HuggingFaceClient(token=self.token)

    async def list_available_models(self) -> List[ModelMetadata]:
        """Lista popularnych modeli HF z HuggingFace Hub API."""
        try:
            models_data = await self.client.list_models(sort="downloads", limit=20)

            model_list = []
            for model_data in models_data:
                try:
                    model_name = model_data.get("id", model_data.get("modelId", ""))
                    if not model_name:
                        continue

                    model_list.append(
                        ModelMetadata(
                            name=model_name,
                            provider=ModelProvider.HUGGINGFACE,
                            display_name=model_name.split("/")[-1]
                            if "/" in model_name
                            else model_name,
                            size_gb=0.0,
                            status=ModelStatus.AVAILABLE,
                            runtime="vllm",
                            capabilities=ModelCapabilities(
                                generation_schema=create_default_generation_schema(),
                            ),
                        )
                    )
                except Exception as e:
                    logger.debug(f"Pominięto model podczas parsowania: {e}")
                    continue

            if not model_list:
                logger.warning("HF API zwróciło pusty wynik, używam fallbacku")
                model_list = [
                    ModelMetadata(
                        name="google/gemma-2b-it",
                        provider=ModelProvider.HUGGINGFACE,
                        display_name="Gemma 2B IT",
                        size_gb=4.0,
                        status=ModelStatus.AVAILABLE,
                        runtime="vllm",
                        capabilities=ModelCapabilities(
                            supports_system_role=False,
                            allowed_roles=["user", "assistant"],
                            generation_schema=create_default_generation_schema(),
                        ),
                    ),
                    ModelMetadata(
                        name="microsoft/phi-3-mini-4k-instruct",
                        provider=ModelProvider.HUGGINGFACE,
                        display_name="Phi-3 Mini 4K Instruct",
                        size_gb=7.0,
                        status=ModelStatus.AVAILABLE,
                        runtime="vllm",
                        capabilities=ModelCapabilities(
                            generation_schema=create_default_generation_schema(),
                        ),
                    ),
                ]

            logger.info(f"Pobrano {len(model_list)} modeli z HuggingFace")
            return model_list

        except Exception as e:
            logger.error(f"Błąd podczas pobierania listy modeli z HF: {e}")
            return [
                ModelMetadata(
                    name="google/gemma-2b-it",
                    provider=ModelProvider.HUGGINGFACE,
                    display_name="Gemma 2B IT",
                    size_gb=4.0,
                    status=ModelStatus.AVAILABLE,
                    runtime="vllm",
                    capabilities=ModelCapabilities(
                        supports_system_role=False,
                        allowed_roles=["user", "assistant"],
                        generation_schema=create_default_generation_schema(),
                    ),
                ),
            ]

    async def install_model(
        self, model_name: str, progress_callback: Optional[Callable] = None
    ) -> bool:
        """Pobiera model z HuggingFace."""
        try:
            logger.info(f"Rozpoczynam pobieranie modelu HF: {model_name}")

            local_path = await self.client.download_snapshot(
                model_name=model_name,
                cache_dir=str(self.cache_dir),
                progress_callback=progress_callback,
            )
            if not local_path:
                return False
            logger.info(f"✅ Model {model_name} pobrany do {local_path}")
            if progress_callback:
                await progress_callback(f"Model {model_name} zainstalowany pomyślnie")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas pobierania modelu z HF: {e}")
            return False

    async def remove_model(self, model_name: str) -> bool:
        """Usuwa model z cache HF."""
        try:
            await asyncio.sleep(0)
            success = self.client.remove_cached_model(self.cache_dir, model_name)
            if success:
                logger.info(f"✅ Model {model_name} usunięty z cache HF")
            return success
        except Exception as e:
            logger.error(f"Błąd podczas usuwania modelu: {e}")
            return False

    async def get_model_info(self, model_name: str) -> Optional[ModelMetadata]:
        """Pobiera informacje o modelu z HuggingFace Hub API."""
        try:
            model_data = await self.client.get_model_info(model_name)

            if model_data:
                return ModelMetadata(
                    name=model_name,
                    provider=ModelProvider.HUGGINGFACE,
                    display_name=model_name.split("/")[-1]
                    if "/" in model_name
                    else model_name,
                    size_gb=0.0,
                    status=ModelStatus.AVAILABLE,
                    runtime="vllm",
                    capabilities=ModelCapabilities(
                        generation_schema=create_default_generation_schema(),
                    ),
                )

            logger.debug(f"Model {model_name} nie znaleziony w HF API, sprawdzam cache")
            models = await self.list_available_models()
            for model in models:
                if model.name == model_name:
                    return model

            return None

        except Exception as e:
            logger.error(f"Błąd podczas pobierania info o modelu {model_name}: {e}")
            models = await self.list_available_models()
            for model in models:
                if model.name == model_name:
                    return model
            return None


__all__ = [
    "BaseModelProvider",
    "HuggingFaceModelProvider",
    "OllamaModelProvider",
    "create_default_generation_schema",
    "resolve_hf_token",
]
