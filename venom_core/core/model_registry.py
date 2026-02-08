"""
ModelRegistry - Centralny system zarządzania modelami AI.

Odpowiedzialny za:
- Pobieranie modeli z HuggingFace i Ollama
- Zarządzanie metadanymi modeli (capabilities, rozmiary, etc.)
- Aktywację i przełączanie modeli
- Monitoring operacji instalacji/usuwania
"""

import abc
import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.core.model_registry_clients import HuggingFaceClient, OllamaClient
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)


def _resolve_hf_token() -> Optional[str]:
    token = getattr(SETTINGS, "HF_TOKEN", None)
    if token is None:
        return None
    if hasattr(token, "get_secret_value"):
        token_value = token.get_secret_value()
    else:
        token_value = token
    return token_value or None


class ModelProvider(str, Enum):
    """Providery modeli."""

    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    VLLM = "vllm"
    LOCAL = "local"


class ModelStatus(str, Enum):
    """Statusy modelu."""

    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    INSTALLED = "installed"
    FAILED = "failed"
    REMOVING = "removing"


class OperationStatus(str, Enum):
    """Statusy operacji."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GenerationParameter:
    """Definicja pojedynczego parametru generacji dla modelu."""

    type: str  # "float", "int", "bool", "list", "enum"
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    desc: Optional[str] = None
    options: Optional[List[Any]] = None  # dla enum/list

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje do słownika."""
        result = {
            "type": self.type,
            "default": self.default,
        }
        if self.min is not None:
            result["min"] = self.min
        if self.max is not None:
            result["max"] = self.max
        if self.desc is not None:
            result["desc"] = self.desc
        if self.options is not None:
            result["options"] = self.options
        return result


@dataclass
class ModelCapabilities:
    """Możliwości modelu (obsługa ról, templaty, etc.)."""

    supports_system_role: bool = True
    supports_function_calling: bool = False
    allowed_roles: List[str] = field(
        default_factory=lambda: ["system", "user", "assistant"]
    )
    prompt_template: Optional[str] = None
    max_context_length: int = 4096
    quantization: Optional[str] = None
    generation_schema: Optional[Dict[str, GenerationParameter]] = None


@dataclass
class ModelMetadata:
    """Metadane modelu."""

    name: str
    provider: ModelProvider
    display_name: str
    size_gb: Optional[float] = None
    status: ModelStatus = ModelStatus.AVAILABLE
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    local_path: Optional[str] = None
    sha256: Optional[str] = None
    installed_at: Optional[str] = None
    runtime: str = "vllm"  # "vllm" lub "ollama"

    @property
    def supports_system_role(self) -> bool:
        """Zachowuje kompatybilność ze starszym kodem oczekującym pola bezpośrednio w metadata."""
        return self.capabilities.supports_system_role

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje do słownika."""
        capabilities_dict = {
            "supports_system_role": self.capabilities.supports_system_role,
            "supports_function_calling": self.capabilities.supports_function_calling,
            "allowed_roles": self.capabilities.allowed_roles,
            "prompt_template": self.capabilities.prompt_template,
            "max_context_length": self.capabilities.max_context_length,
            "quantization": self.capabilities.quantization,
        }

        if self.capabilities.generation_schema:
            capabilities_dict["generation_schema"] = {
                key: param.to_dict()
                for key, param in self.capabilities.generation_schema.items()
            }

        return {
            "name": self.name,
            "provider": self.provider.value,
            "display_name": self.display_name,
            "size_gb": self.size_gb,
            "status": self.status.value,
            "capabilities": capabilities_dict,
            "local_path": self.local_path,
            "sha256": self.sha256,
            "installed_at": self.installed_at,
            "runtime": self.runtime,
        }


@dataclass
class ModelOperation:
    """Operacja na modelu (instalacja/usuwanie)."""

    operation_id: str
    model_name: str
    operation_type: str  # "install", "remove", "activate"
    status: OperationStatus
    progress: float = 0.0
    message: str = ""
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje do słownika."""
        return {
            "operation_id": self.operation_id,
            "model_name": self.model_name,
            "operation_type": self.operation_type,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


class BaseModelProvider(abc.ABC):
    """Bazowa klasa dla providerów modeli."""

    @abc.abstractmethod
    async def list_available_models(self) -> List[ModelMetadata]:
        """Lista dostępnych modeli."""
        pass

    @abc.abstractmethod
    async def install_model(
        self, model_name: str, progress_callback: Optional[Callable] = None
    ) -> bool:
        """Instaluje model."""
        pass

    @abc.abstractmethod
    async def remove_model(self, model_name: str) -> bool:
        """Usuwa model."""
        pass

    @abc.abstractmethod
    async def get_model_info(self, model_name: str) -> Optional[ModelMetadata]:
        """Pobiera informacje o modelu."""
        pass


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

                # Określ generation_schema na podstawie nazwy modelu
                generation_schema = _create_default_generation_schema()
                # Używamy regex do precyzyjnego wykrycia modeli Llama 3
                # Pasuje do: llama3, llama-3, llama3:latest, llama-3:8b
                # Nie pasuje do: llama-30b, llama-3b, my-llama-v3
                if re.search(r"llama-?3(?:[:\-]|$)", name, re.IGNORECASE):
                    # Llama 3 ma temperaturę 0.0-1.0
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
        # Ollama models don't support forward slashes
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


def _create_default_generation_schema() -> Dict[str, GenerationParameter]:
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


class HuggingFaceModelProvider(BaseModelProvider):
    """Provider dla modeli HuggingFace."""

    def __init__(self, cache_dir: Optional[str] = None, token: Optional[str] = None):
        self.cache_dir = Path(cache_dir or "./models_cache/hf")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.client = HuggingFaceClient(token=self.token)

    async def list_available_models(self) -> List[ModelMetadata]:
        """Lista popularnych modeli HF (stub - do rozszerzenia)."""
        # TODO: Integracja z HF Hub API do wyszukiwania modeli
        popular_models = [
            ModelMetadata(
                name="google/gemma-2b-it",
                provider=ModelProvider.HUGGINGFACE,
                display_name="Gemma 2B IT",
                size_gb=4.0,
                status=ModelStatus.AVAILABLE,
                runtime="vllm",
                capabilities=ModelCapabilities(
                    supports_system_role=False,  # Gemma nie wspiera roli system
                    allowed_roles=["user", "assistant"],
                    generation_schema=_create_default_generation_schema(),
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
                    generation_schema=_create_default_generation_schema(),
                ),
            ),
        ]
        # Symuluj async operację
        await asyncio.sleep(0)
        return popular_models

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
            # Symuluj async operację
            await asyncio.sleep(0)
            success = self.client.remove_cached_model(self.cache_dir, model_name)
            if success:
                logger.info(f"✅ Model {model_name} usunięty z cache HF")
            return success
        except Exception as e:
            logger.error(f"Błąd podczas usuwania modelu: {e}")
            return False

    async def get_model_info(self, model_name: str) -> Optional[ModelMetadata]:
        """Pobiera informacje o modelu z HF (stub)."""
        # TODO: Integracja z HF Hub API
        models = await self.list_available_models()
        for model in models:
            if model.name == model_name:
                return model
        return None


class ModelRegistry:
    """
    Centralny rejestr modeli - zarządza instalacją, usuwaniem i aktywacją modeli.
    """

    def __init__(self, models_dir: Optional[str] = None):
        self.models_dir = Path(models_dir or "./data/models")
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # Manifest z metadanymi modeli
        self.manifest_path = self.models_dir / "manifest.json"
        self.manifest: Dict[str, ModelMetadata] = {}
        self._load_manifest()

        # Providery
        self.providers: Dict[ModelProvider, BaseModelProvider] = {
            ModelProvider.OLLAMA: OllamaModelProvider(),
            ModelProvider.HUGGINGFACE: HuggingFaceModelProvider(
                cache_dir=str(self.models_dir / "hf_cache"),
                token=_resolve_hf_token(),
            ),
        }
        self.hf_client = HuggingFaceClient(token=_resolve_hf_token())
        self.ollama_catalog_client = OllamaClient(endpoint="https://ollama.com")

        # Operacje w toku
        self.operations: Dict[str, ModelOperation] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()

        # Lock dla operacji per runtime
        self._runtime_locks: Dict[str, asyncio.Lock] = {
            "vllm": asyncio.Lock(),
            "ollama": asyncio.Lock(),
        }
        self._external_cache: Dict[str, Dict[str, Any]] = {}
        self._external_cache_ttl_seconds = 1800

        logger.info(f"ModelRegistry zainicjalizowany (models_dir={self.models_dir})")

    def _load_manifest(self):
        """Ładuje manifest z dysku."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r") as f:
                    data = json.load(f)
                    for model_data in data.get("models", []):
                        # Safely extract capabilities with known fields only
                        caps_data = model_data.get("capabilities", {})

                        # Parse generation_schema if present
                        generation_schema = None
                        if "generation_schema" in caps_data:
                            generation_schema = {}
                            for param_name, param_data in caps_data[
                                "generation_schema"
                            ].items():
                                generation_schema[param_name] = GenerationParameter(
                                    type=param_data.get("type", "float"),
                                    default=param_data.get("default"),
                                    min=param_data.get("min"),
                                    max=param_data.get("max"),
                                    desc=param_data.get("desc"),
                                    options=param_data.get("options"),
                                )

                        capabilities = ModelCapabilities(
                            supports_system_role=caps_data.get(
                                "supports_system_role", True
                            ),
                            supports_function_calling=caps_data.get(
                                "supports_function_calling", False
                            ),
                            allowed_roles=caps_data.get(
                                "allowed_roles", ["system", "user", "assistant"]
                            ),
                            prompt_template=caps_data.get("prompt_template"),
                            max_context_length=caps_data.get(
                                "max_context_length", 4096
                            ),
                            quantization=caps_data.get("quantization"),
                            generation_schema=generation_schema,
                        )

                        metadata = ModelMetadata(
                            name=model_data["name"],
                            provider=ModelProvider(model_data["provider"]),
                            display_name=model_data.get(
                                "display_name", model_data["name"]
                            ),
                            size_gb=model_data.get("size_gb"),
                            status=ModelStatus(model_data.get("status", "available")),
                            capabilities=capabilities,
                            local_path=model_data.get("local_path"),
                            sha256=model_data.get("sha256"),
                            installed_at=model_data.get("installed_at"),
                            runtime=model_data.get("runtime", "vllm"),
                        )
                        self.manifest[metadata.name] = metadata
                logger.info(f"Załadowano manifest: {len(self.manifest)} modeli")
            except Exception as e:
                logger.error(f"Błąd podczas ładowania manifestu: {e}")

    def _save_manifest(self):
        """Zapisuje manifest na dysk."""
        try:
            data = {
                "models": [model.to_dict() for model in self.manifest.values()],
                "updated_at": datetime.now().isoformat(),
            }
            with open(self.manifest_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug("Manifest zapisany")
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania manifestu: {e}")

    async def list_available_models(
        self, provider: Optional[ModelProvider] = None
    ) -> List[ModelMetadata]:
        """Lista dostępnych modeli ze wszystkich providerów."""
        all_models = []
        providers_to_query = [provider] if provider else list(self.providers.keys())

        for prov in providers_to_query:
            provider_obj = self.providers.get(prov)
            if provider_obj:
                models = await provider_obj.list_available_models()
                all_models.extend(models)

        return all_models

    async def list_trending_models(
        self, provider: ModelProvider, limit: int = 12
    ) -> Dict[str, Any]:
        """Lista trendujących modeli z zewnętrznych źródeł."""
        return await self._list_external_models(provider, limit, mode="trending")

    async def list_catalog_models(
        self, provider: ModelProvider, limit: int = 20
    ) -> Dict[str, Any]:
        """Lista dostępnych modeli z zewnętrznych źródeł."""
        return await self._list_external_models(provider, limit, mode="catalog")

    async def list_news(
        self,
        provider: ModelProvider,
        limit: int = 5,
        kind: str = "blog",
        month: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lista newsow dla danego providera."""
        if provider != ModelProvider.HUGGINGFACE:
            return {"items": [], "stale": False, "error": None}
        try:
            if kind == "papers":
                items = await self._fetch_hf_papers_month(limit=limit, month=month)
            else:
                items = await self._fetch_hf_blog_feed(limit=limit)
            return {"items": items, "stale": False, "error": None}
        except Exception as e:
            logger.warning(f"Nie udało się pobrać newsów HF: {e}")
            return {"items": [], "stale": True, "error": str(e)}

    async def search_external_models(
        self, provider: ModelProvider, query: str, limit: int = 20
    ) -> Dict[str, Any]:
        """Przeszukuje modele u zewnętrznego providera."""
        try:
            if not query or len(query) < 2:
                return {"models": [], "count": 0}

            if provider == ModelProvider.HUGGINGFACE:
                models = await self.hf_client.search_models(query, limit)
                # Mapowanie wyników HF na format katalogu
                formatted = []
                for item in models:
                    model_id = item.get("modelId") or item.get("id")
                    if not model_id:
                        continue
                    entry = self._format_catalog_entry(
                        provider=ModelProvider.HUGGINGFACE,
                        model_name=model_id,
                        display_name=model_id.split("/")[-1],
                        runtime="vllm",
                        size_gb=None,
                        tags=item.get("tags"),
                        downloads=item.get("downloads"),
                        likes=item.get("likes"),
                    )
                    entry["description"] = None
                    formatted.append(entry)
                return {"models": formatted, "count": len(formatted)}

            elif provider == ModelProvider.OLLAMA:
                raw_models = await self.ollama_catalog_client.search_models(
                    query, limit
                )
                formatted = []
                for item in raw_models:
                    entry = self._format_catalog_entry(
                        provider=ModelProvider.OLLAMA,
                        model_name=item["name"],
                        display_name=item["name"],
                        runtime="ollama",
                        size_gb=None,
                        tags=[],
                        downloads=None,
                        likes=None,
                    )
                    entry["description"] = item.get("description")
                    formatted.append(entry)
                return {"models": formatted, "count": len(formatted)}

            return {"models": [], "count": 0}

        except Exception as e:
            logger.error(f"Search failed for {provider}: {e}")
            return {"models": [], "count": 0, "error": str(e)}

    async def _list_external_models(
        self, provider: ModelProvider, limit: int, mode: str
    ) -> Dict[str, Any]:
        cache_key = f"{provider.value}:{mode}:{limit}"
        cached = self._external_cache.get(cache_key)
        now = time.time()
        if cached and now - cached["timestamp"] < self._external_cache_ttl_seconds:
            return {"models": cached["data"], "stale": False, "error": None}

        try:
            if provider == ModelProvider.HUGGINGFACE:
                sort = "trendingScore" if mode == "trending" else "downloads"
                models = await self._fetch_huggingface_models(sort=sort, limit=limit)
            elif provider == ModelProvider.OLLAMA:
                models = await self._fetch_ollama_models(limit=limit)
            else:
                models = []
            self._external_cache[cache_key] = {
                "timestamp": now,
                "data": models,
            }
            return {"models": models, "stale": False, "error": None}
        except Exception as e:
            logger.warning(f"Nie udało się pobrać listy {mode} dla {provider}: {e}")
            if cached:
                return {"models": cached["data"], "stale": True, "error": str(e)}
            return {"models": [], "stale": True, "error": str(e)}

    async def _fetch_huggingface_models(
        self, sort: str, limit: int
    ) -> List[Dict[str, Any]]:
        payload = await self.hf_client.list_models(sort=sort, limit=limit)
        if not isinstance(payload, list):
            return []

        models: List[Dict[str, Any]] = []
        for item in payload:
            model_id = item.get("modelId") or item.get("id")
            if not model_id:
                continue
            display = model_id.split("/")[-1]
            models.append(
                self._format_catalog_entry(
                    provider=ModelProvider.HUGGINGFACE,
                    model_name=model_id,
                    display_name=display,
                    runtime="vllm",
                    size_gb=None,
                    tags=item.get("tags") or [],
                    downloads=item.get("downloads"),
                    likes=item.get("likes"),
                )
            )
        return models

    async def _fetch_ollama_models(self, limit: int) -> List[Dict[str, Any]]:
        payload = await self.ollama_catalog_client.list_tags()
        models: List[Dict[str, Any]] = []
        for item in payload.get("models", [])[:limit]:
            name = item.get("name")
            if not name:
                continue
            details = item.get("details") or {}
            tags = [
                value
                for value in [
                    details.get("family"),
                    details.get("parameter_size"),
                    details.get("quantization_level"),
                    details.get("format"),
                ]
                if value
            ]
            size_bytes = item.get("size")
            if isinstance(size_bytes, (int, float)):
                size_gb = round(size_bytes / (1024**3), 2)
            else:
                size_gb = None
            models.append(
                self._format_catalog_entry(
                    provider=ModelProvider.OLLAMA,
                    model_name=name,
                    display_name=name,
                    runtime="ollama",
                    size_gb=size_gb,
                    tags=tags,
                    downloads=None,
                    likes=None,
                )
            )
        return models

    async def _fetch_hf_blog_feed(self, limit: int) -> List[Dict[str, Any]]:
        return await self.hf_client.fetch_blog_feed(limit=limit)

    async def _fetch_hf_papers_month(
        self, limit: int, month: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return await self.hf_client.fetch_papers_month(limit=limit, month=month)

    def _format_catalog_entry(
        self,
        provider: ModelProvider,
        model_name: str,
        display_name: str,
        runtime: str,
        size_gb: Optional[float] = None,
        tags: Optional[List[str]] = None,
        downloads: Optional[int] = None,
        likes: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {
            "provider": provider.value,
            "model_name": model_name,
            "display_name": display_name,
            "size_gb": size_gb,
            "runtime": runtime,
            "tags": tags or [],
            "downloads": downloads,
            "likes": likes,
        }

    async def install_model(
        self,
        model_name: str,
        provider: ModelProvider,
        runtime: str = "vllm",
    ) -> str:
        """
        Instaluje model (asynchronicznie).

        Returns:
            operation_id - ID operacji do sprawdzania statusu
        """
        operation_id = str(uuid.uuid4())

        # Sprawdź czy provider istnieje
        if provider not in self.providers:
            raise ValueError(f"Nieznany provider: {provider}")
        if provider == ModelProvider.OLLAMA and runtime != "ollama":
            raise ValueError("Ollama wspiera tylko runtime 'ollama'")
        if provider == ModelProvider.HUGGINGFACE and runtime != "vllm":
            raise ValueError("HuggingFace wspiera tylko runtime 'vllm'")

        # Utwórz operację
        operation = ModelOperation(
            operation_id=operation_id,
            model_name=model_name,
            operation_type="install",
            status=OperationStatus.PENDING,
        )
        self.operations[operation_id] = operation

        # Uruchom instalację w tle z obsługą wyjątków
        task = asyncio.create_task(
            self._install_model_task(operation, provider, runtime)
        )
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        await asyncio.sleep(0)

        return operation_id

    async def _install_model_task(
        self,
        operation: ModelOperation,
        provider: ModelProvider,
        runtime: str,
    ):
        """Zadanie instalacji modelu."""
        if runtime not in self._runtime_locks:
            raise ValueError(f"Nieznany runtime: {runtime}")

        async with self._runtime_locks[runtime]:
            try:
                operation.status = OperationStatus.IN_PROGRESS
                operation.message = f"Pobieranie modelu {operation.model_name}..."

                async def progress_callback(message: str):
                    operation.message = message
                    logger.info(f"[{operation.operation_id}] {message}")
                    await asyncio.sleep(0)

                provider_obj = self.providers[provider]
                success = await provider_obj.install_model(
                    operation.model_name, progress_callback
                )

                if success:
                    operation.status = OperationStatus.COMPLETED
                    operation.progress = 100.0
                    operation.message = f"Model {operation.model_name} zainstalowany"
                    operation.completed_at = datetime.now().isoformat()

                    # Dodaj do manifestu
                    metadata = ModelMetadata(
                        name=operation.model_name,
                        provider=provider,
                        display_name=operation.model_name,
                        status=ModelStatus.INSTALLED,
                        installed_at=datetime.now().isoformat(),
                        runtime=runtime,
                    )
                    self.manifest[operation.model_name] = metadata
                    self._save_manifest()
                else:
                    operation.status = OperationStatus.FAILED
                    operation.error = "Instalacja nie powiodła się"

            except Exception as e:
                logger.error(f"Błąd podczas instalacji modelu: {e}")
                operation.status = OperationStatus.FAILED
                operation.error = str(e)

    async def remove_model(self, model_name: str) -> str:
        """Usuwa model."""
        operation_id = str(uuid.uuid4())

        # Sprawdź czy model istnieje w manifeście
        if model_name not in self.manifest:
            raise ValueError(f"Model {model_name} nie znaleziony")

        metadata = self.manifest[model_name]
        provider = metadata.provider

        # Utwórz operację
        operation = ModelOperation(
            operation_id=operation_id,
            model_name=model_name,
            operation_type="remove",
            status=OperationStatus.PENDING,
        )
        self.operations[operation_id] = operation

        # Uruchom usuwanie w tle
        remove_task = asyncio.create_task(self._remove_model_task(operation, provider))
        self._background_tasks.add(remove_task)
        remove_task.add_done_callback(self._background_tasks.discard)
        await asyncio.sleep(0)

        return operation_id

    async def _remove_model_task(
        self, operation: ModelOperation, provider: ModelProvider
    ):
        """Zadanie usuwania modelu."""
        try:
            operation.status = OperationStatus.IN_PROGRESS
            operation.message = f"Usuwanie modelu {operation.model_name}..."

            provider_obj = self.providers[provider]
            success = await provider_obj.remove_model(operation.model_name)

            if success:
                operation.status = OperationStatus.COMPLETED
                operation.progress = 100.0
                operation.message = f"Model {operation.model_name} usunięty"
                operation.completed_at = datetime.now().isoformat()

                # Usuń z manifestu
                if operation.model_name in self.manifest:
                    del self.manifest[operation.model_name]
                    self._save_manifest()
            else:
                operation.status = OperationStatus.FAILED
                operation.error = "Usuwanie nie powiodło się"

        except Exception as e:
            logger.error(f"Błąd podczas usuwania modelu: {e}")
            operation.status = OperationStatus.FAILED
            operation.error = str(e)

    def get_operation_status(self, operation_id: str) -> Optional[ModelOperation]:
        """Pobiera status operacji."""
        return self.operations.get(operation_id)

    def list_operations(self, limit: int = 10) -> List[ModelOperation]:
        """Lista ostatnich operacji."""
        ops = sorted(
            self.operations.values(),
            key=lambda op: op.started_at,
            reverse=True,
        )
        return ops[:limit]

    def get_model_capabilities(self, model_name: str) -> Optional[ModelCapabilities]:
        """Pobiera capabilities modelu."""
        if model_name in self.manifest:
            return self.manifest[model_name].capabilities
        return None

    async def activate_model(self, model_name: str, runtime: str) -> bool:
        """
        Aktywuje model dla danego runtime (prosty update konfiguracji).

        Returns:
            True jeśli sukces
        """
        logger.info(f"Aktywacja modelu {model_name} dla runtime {runtime}")

        if model_name not in self.manifest:
            if runtime == "ollama":
                provider = self.providers.get(ModelProvider.OLLAMA)
                if provider:
                    try:
                        metadata = await provider.get_model_info(model_name)
                        if metadata:
                            self.manifest[model_name] = metadata
                            self._save_manifest()
                        else:
                            logger.error(f"Model {model_name} nie znaleziony w Ollama")
                            return False
                    except Exception as exc:
                        logger.warning(
                            f"Nie udało się pobrać metadanych modelu Ollama {model_name}: {exc}"
                        )
                        return False
                else:
                    logger.error("Provider Ollama niedostępny")
                    return False
            else:
                logger.error(f"Model {model_name} nie znaleziony w manifeście")
                return False

        meta = self.manifest.get(model_name)
        if not meta:
            logger.error("Brak metadanych modelu %s po aktywacji", model_name)
            return False

        # Aktualizuj SETTINGS i .env przez config_manager
        try:
            from venom_core.config import SETTINGS
            from venom_core.services.config_manager import config_manager

            template_value = ""
            updates = {
                "LLM_MODEL_NAME": model_name,
                "ACTIVE_LLM_SERVER": runtime,
            }
            if runtime == "vllm":
                local_path = meta.local_path or model_name
                template_candidate = Path(local_path) / "chat_template.jinja"
                if not template_candidate.is_absolute():
                    template_candidate = Path(SETTINGS.REPO_ROOT) / template_candidate
                if template_candidate.exists():
                    template_value = str(template_candidate)
                updates.update(
                    {
                        "VLLM_MODEL_PATH": local_path,
                        "VLLM_SERVED_MODEL_NAME": model_name,
                        "VLLM_CHAT_TEMPLATE": template_value,
                        "LAST_MODEL_VLLM": model_name,
                    }
                )
                SETTINGS.VLLM_MODEL_PATH = local_path
                SETTINGS.VLLM_SERVED_MODEL_NAME = model_name
                try:
                    SETTINGS.VLLM_CHAT_TEMPLATE = template_value
                except Exception:
                    # Atrybut dynamiczny - może nie istnieć w starszych wersjach Settings
                    pass
            if runtime == "ollama":
                updates["LAST_MODEL_OLLAMA"] = model_name

            config_manager.update_config(updates)

            SETTINGS.LLM_MODEL_NAME = model_name
            SETTINGS.ACTIVE_LLM_SERVER = runtime
            if runtime == "ollama":
                try:
                    SETTINGS.LAST_MODEL_OLLAMA = model_name
                except Exception:
                    # Atrybut dynamiczny - może nie istnieć w starszych wersjach Settings
                    pass
            if runtime == "vllm":
                try:
                    SETTINGS.LAST_MODEL_VLLM = model_name
                except Exception:
                    # Atrybut dynamiczny - może nie istnieć w starszych wersjach Settings
                    pass

            # Restart odpowiedniego runtime, jeśli mamy komendę
            try:
                from venom_core.core.llm_server_controller import LlmServerController

                controller = LlmServerController(SETTINGS)
                action = "restart"
                if controller.has_server(runtime):
                    result = await controller.run_action(runtime, action)
                    if not result.ok:
                        logger.warning(
                            "Restart %s po aktywacji modelu nie powiódł się: %s",
                            runtime,
                            result.stderr,
                        )
            except Exception as exc:
                logger.warning("Nie udało się wykonać restartu %s: %s", runtime, exc)

        except Exception as e:
            logger.warning(
                f"Nie udało się zaktualizować SETTINGS/config dla {model_name}: {e}"
            )
            return False

        logger.info(f"Model {model_name} aktywowany (runtime={runtime})")
        return True
