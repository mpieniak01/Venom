"""Typy i modele domenowe dla ModelRegistry."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


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
        """Kompatybilność ze starszym kodem oczekującym pola bezpośrednio."""
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


__all__ = [
    "GenerationParameter",
    "ModelCapabilities",
    "ModelMetadata",
    "ModelOperation",
    "ModelProvider",
    "ModelStatus",
    "OperationStatus",
]
