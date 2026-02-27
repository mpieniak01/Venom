"""Logika ładowania/zapisu manifestu dla ModelRegistry."""

import json
from datetime import datetime
from typing import Any, Dict

from venom_core.core.model_registry_types import (
    GenerationParameter,
    ModelCapabilities,
    ModelMetadata,
    ModelProvider,
    ModelStatus,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def load_manifest(registry: Any) -> None:
    """Ładuje manifest z dysku."""
    if not registry.manifest_path.exists():
        return

    try:
        with open(registry.manifest_path, "r") as f:
            data = json.load(f)
            for model_data in data.get("models", []):
                caps_data = model_data.get("capabilities", {})

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
                    supports_system_role=caps_data.get("supports_system_role", True),
                    supports_function_calling=caps_data.get(
                        "supports_function_calling", False
                    ),
                    allowed_roles=caps_data.get(
                        "allowed_roles", ["system", "user", "assistant"]
                    ),
                    prompt_template=caps_data.get("prompt_template"),
                    max_context_length=caps_data.get("max_context_length", 4096),
                    quantization=caps_data.get("quantization"),
                    generation_schema=generation_schema,
                )

                metadata = ModelMetadata(
                    name=model_data["name"],
                    provider=ModelProvider(model_data["provider"]),
                    display_name=model_data.get("display_name", model_data["name"]),
                    size_gb=model_data.get("size_gb"),
                    status=ModelStatus(model_data.get("status", "available")),
                    capabilities=capabilities,
                    local_path=model_data.get("local_path"),
                    sha256=model_data.get("sha256"),
                    installed_at=model_data.get("installed_at"),
                    runtime=model_data.get("runtime", "vllm"),
                )
                registry.manifest[metadata.name] = metadata
        logger.info(f"Załadowano manifest: {len(registry.manifest)} modeli")
    except Exception as e:
        logger.error(f"Błąd podczas ładowania manifestu: {e}")


def save_manifest(registry: Any) -> None:
    """Zapisuje manifest na dysk."""
    try:
        data: Dict[str, Any] = {
            "models": [model.to_dict() for model in registry.manifest.values()],
            "updated_at": datetime.now().isoformat(),
        }
        with open(registry.manifest_path, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug("Manifest zapisany")
    except Exception as e:
        logger.error(f"Błąd podczas zapisywania manifestu: {e}")
