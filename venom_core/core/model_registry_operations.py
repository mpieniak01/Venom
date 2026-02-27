"""Operacje install/remove i statusy dla ModelRegistry."""

import asyncio
import uuid
from datetime import datetime
from typing import Any, List, Optional

from venom_core.core.model_registry_types import (
    ModelCapabilities,
    ModelMetadata,
    ModelOperation,
    ModelProvider,
    ModelStatus,
    OperationStatus,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def install_model(
    registry: Any,
    model_name: str,
    provider: ModelProvider,
    runtime: str = "vllm",
) -> str:
    """Instaluje model (asynchronicznie) i zwraca operation_id."""
    operation_id = str(uuid.uuid4())

    if provider not in registry.providers:
        raise ValueError(f"Nieznany provider: {provider}")
    if provider == ModelProvider.OLLAMA and runtime != "ollama":
        raise ValueError("Ollama wspiera tylko runtime 'ollama'")
    if provider == ModelProvider.HUGGINGFACE and runtime != "vllm":
        raise ValueError("HuggingFace wspiera tylko runtime 'vllm'")

    operation = ModelOperation(
        operation_id=operation_id,
        model_name=model_name,
        operation_type="install",
        status=OperationStatus.PENDING,
    )
    registry.operations[operation_id] = operation

    task = asyncio.create_task(
        _install_model_task(registry, operation, provider, runtime)
    )
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    await asyncio.sleep(0)

    return operation_id


async def _install_model_task(
    registry: Any,
    operation: ModelOperation,
    provider: ModelProvider,
    runtime: str,
) -> None:
    """Zadanie instalacji modelu."""
    if runtime not in registry._runtime_locks:
        raise ValueError(f"Nieznany runtime: {runtime}")

    async with registry._runtime_locks[runtime]:
        try:
            operation.status = OperationStatus.IN_PROGRESS
            operation.message = f"Pobieranie modelu {operation.model_name}..."

            async def progress_callback(message: str) -> None:
                operation.message = message
                logger.info(f"[{operation.operation_id}] {message}")
                await asyncio.sleep(0)

            provider_obj = registry.providers[provider]
            success = await provider_obj.install_model(
                operation.model_name, progress_callback
            )

            if success:
                operation.status = OperationStatus.COMPLETED
                operation.progress = 100.0
                operation.message = f"Model {operation.model_name} zainstalowany"
                operation.completed_at = datetime.now().isoformat()

                metadata = ModelMetadata(
                    name=operation.model_name,
                    provider=provider,
                    display_name=operation.model_name,
                    status=ModelStatus.INSTALLED,
                    installed_at=datetime.now().isoformat(),
                    runtime=runtime,
                )
                registry.manifest[operation.model_name] = metadata
                registry._save_manifest()
            else:
                operation.status = OperationStatus.FAILED
                operation.error = "Instalacja nie powiodła się"
        except Exception as e:
            logger.error(f"Błąd podczas instalacji modelu: {e}")
            operation.status = OperationStatus.FAILED
            operation.error = str(e)


async def remove_model(registry: Any, model_name: str) -> str:
    """Usuwa model i zwraca operation_id."""
    operation_id = str(uuid.uuid4())

    if model_name not in registry.manifest:
        raise ValueError(f"Model {model_name} nie znaleziony")

    metadata = registry.manifest[model_name]
    provider = metadata.provider

    operation = ModelOperation(
        operation_id=operation_id,
        model_name=model_name,
        operation_type="remove",
        status=OperationStatus.PENDING,
    )
    registry.operations[operation_id] = operation

    remove_task = asyncio.create_task(_remove_model_task(registry, operation, provider))
    registry._background_tasks.add(remove_task)
    remove_task.add_done_callback(registry._background_tasks.discard)
    await asyncio.sleep(0)

    return operation_id


async def _remove_model_task(
    registry: Any, operation: ModelOperation, provider: ModelProvider
) -> None:
    """Zadanie usuwania modelu."""
    try:
        operation.status = OperationStatus.IN_PROGRESS
        operation.message = f"Usuwanie modelu {operation.model_name}..."

        provider_obj = registry.providers[provider]
        success = await provider_obj.remove_model(operation.model_name)

        if success:
            operation.status = OperationStatus.COMPLETED
            operation.progress = 100.0
            operation.message = f"Model {operation.model_name} usunięty"
            operation.completed_at = datetime.now().isoformat()

            if operation.model_name in registry.manifest:
                del registry.manifest[operation.model_name]
                registry._save_manifest()
        else:
            operation.status = OperationStatus.FAILED
            operation.error = "Usuwanie nie powiodło się"
    except Exception as e:
        logger.error(f"Błąd podczas usuwania modelu: {e}")
        operation.status = OperationStatus.FAILED
        operation.error = str(e)


def get_operation_status(registry: Any, operation_id: str) -> Optional[ModelOperation]:
    """Pobiera status operacji."""
    return registry.operations.get(operation_id)


def list_operations(registry: Any, limit: int = 10) -> List[ModelOperation]:
    """Lista ostatnich operacji."""
    ops = sorted(
        registry.operations.values(),
        key=lambda op: op.started_at,
        reverse=True,
    )
    return ops[:limit]


def get_model_capabilities(
    registry: Any, model_name: str
) -> Optional[ModelCapabilities]:
    """Pobiera capabilities modelu."""
    if model_name in registry.manifest:
        return registry.manifest[model_name].capabilities
    return None
