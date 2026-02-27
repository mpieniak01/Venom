"""
ModelRegistry - Centralny system zarządzania modelami AI.

Odpowiedzialny za:
- Pobieranie modeli z HuggingFace i Ollama
- Zarządzanie metadanymi modeli (capabilities, rozmiary, etc.)
- Aktywację i przełączanie modeli
- Monitoring operacji instalacji/usuwania
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from venom_core.core.model_registry_catalog import (
    list_catalog_models as catalog_list_models,
)
from venom_core.core.model_registry_catalog import list_news as catalog_list_news
from venom_core.core.model_registry_catalog import (
    list_trending_models as catalog_list_trending_models,
)
from venom_core.core.model_registry_catalog import (
    search_external_models as catalog_search_external_models,
)
from venom_core.core.model_registry_clients import HuggingFaceClient, OllamaClient
from venom_core.core.model_registry_manifest import (
    load_manifest as manifest_load_manifest,
)
from venom_core.core.model_registry_manifest import (
    save_manifest as manifest_save_manifest,
)
from venom_core.core.model_registry_operations import (
    get_model_capabilities as operations_get_model_capabilities,
)
from venom_core.core.model_registry_operations import (
    get_operation_status as operations_get_operation_status,
)
from venom_core.core.model_registry_operations import (
    install_model as operations_install_model,
)
from venom_core.core.model_registry_operations import (
    list_operations as operations_list_operations,
)
from venom_core.core.model_registry_operations import (
    remove_model as operations_remove_model,
)
from venom_core.core.model_registry_providers import (
    BaseModelProvider,
    HuggingFaceModelProvider,
    OllamaModelProvider,
    create_default_generation_schema,
    resolve_hf_token,
)
from venom_core.core.model_registry_runtime import (
    activate_model as runtime_activate_model,
)
from venom_core.core.model_registry_runtime import (
    apply_model_activation_config as runtime_apply_model_activation_config,
)
from venom_core.core.model_registry_runtime import (
    apply_vllm_activation_updates as runtime_apply_vllm_activation_updates,
)
from venom_core.core.model_registry_runtime import (
    ensure_model_metadata_for_activation as runtime_ensure_model_metadata_for_activation,
)
from venom_core.core.model_registry_runtime import (
    restart_runtime_after_activation as runtime_restart_runtime_after_activation,
)
from venom_core.core.model_registry_runtime import safe_setattr as runtime_safe_setattr
from venom_core.core.model_registry_types import (
    GenerationParameter,
    ModelCapabilities,
    ModelMetadata,
    ModelOperation,
    ModelProvider,
    ModelStatus,
    OperationStatus,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Backward compatibility for existing imports in API/routes.
_create_default_generation_schema = create_default_generation_schema


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
                token=resolve_hf_token(),
            ),
        }
        self.hf_client = HuggingFaceClient(token=resolve_hf_token())
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
        manifest_load_manifest(self)

    def _save_manifest(self):
        manifest_save_manifest(self)

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
        return await catalog_list_trending_models(self, provider, limit)

    async def list_catalog_models(
        self, provider: ModelProvider, limit: int = 20
    ) -> Dict[str, Any]:
        """Lista dostępnych modeli z zewnętrznych źródeł."""
        return await catalog_list_models(self, provider, limit)

    async def list_news(
        self,
        provider: ModelProvider,
        limit: int = 5,
        kind: str = "blog",
        month: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lista newsow dla danego providera."""
        return await catalog_list_news(
            self, provider, limit=limit, kind=kind, month=month
        )

    async def search_external_models(
        self, provider: ModelProvider, query: str, limit: int = 20
    ) -> Dict[str, Any]:
        """Przeszukuje modele u zewnętrznego providera."""
        return await catalog_search_external_models(self, provider, query, limit)

    async def install_model(
        self,
        model_name: str,
        provider: ModelProvider,
        runtime: str = "vllm",
    ) -> str:
        return await operations_install_model(self, model_name, provider, runtime)

    async def _install_model_task(
        self,
        operation: ModelOperation,
        provider: ModelProvider,
        runtime: str,
    ):
        from venom_core.core.model_registry_operations import _install_model_task

        await _install_model_task(self, operation, provider, runtime)

    async def remove_model(self, model_name: str) -> str:
        return await operations_remove_model(self, model_name)

    async def _remove_model_task(
        self, operation: ModelOperation, provider: ModelProvider
    ):
        from venom_core.core.model_registry_operations import _remove_model_task

        await _remove_model_task(self, operation, provider)

    def get_operation_status(self, operation_id: str) -> Optional[ModelOperation]:
        return operations_get_operation_status(self, operation_id)

    def list_operations(self, limit: int = 10) -> List[ModelOperation]:
        return operations_list_operations(self, limit)

    def get_model_capabilities(self, model_name: str) -> Optional[ModelCapabilities]:
        return operations_get_model_capabilities(self, model_name)

    async def activate_model(self, model_name: str, runtime: str) -> bool:
        return await runtime_activate_model(self, model_name, runtime)

    async def _ensure_model_metadata_for_activation(
        self, model_name: str, runtime: str
    ) -> bool:
        return await runtime_ensure_model_metadata_for_activation(
            self, model_name, runtime
        )

    def _apply_model_activation_config(
        self, model_name: str, runtime: str, meta: "ModelMetadata"
    ):
        return runtime_apply_model_activation_config(self, model_name, runtime, meta)

    def _apply_vllm_activation_updates(
        self,
        model_name: str,
        meta: "ModelMetadata",
        updates: Dict[str, Any],
        settings: Any,
    ) -> None:
        runtime_apply_vllm_activation_updates(self, model_name, meta, updates, settings)

    def _safe_setattr(self, target: Any, attr: str, value: Any) -> None:
        runtime_safe_setattr(target, attr, value)

    async def _restart_runtime_after_activation(
        self, runtime: str, settings: Any
    ) -> None:
        await runtime_restart_runtime_after_activation(runtime, settings)


__all__ = [
    "BaseModelProvider",
    "GenerationParameter",
    "HuggingFaceModelProvider",
    "ModelCapabilities",
    "ModelMetadata",
    "ModelOperation",
    "ModelProvider",
    "ModelRegistry",
    "ModelStatus",
    "OllamaModelProvider",
    "OperationStatus",
    "create_default_generation_schema",
    "_create_default_generation_schema",
]
