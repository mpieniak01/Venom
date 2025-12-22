"""Modele API dla endpointów związanych z modelami AI."""

from venom_core.api.model_schemas.model_requests import (
    ModelActivateRequest,
    ModelConfigUpdateRequest,
    ModelInstallRequest,
    ModelRegistryInstallRequest,
    ModelSwitchRequest,
    TranslationRequest,
)
from venom_core.api.model_schemas.model_validators import (
    validate_huggingface_model_name,
    validate_model_name_basic,
    validate_model_name_extended,
    validate_ollama_model_name,
    validate_provider,
    validate_runtime,
)

__all__ = [
    # Requests
    "ModelInstallRequest",
    "ModelSwitchRequest",
    "ModelRegistryInstallRequest",
    "ModelActivateRequest",
    "TranslationRequest",
    "ModelConfigUpdateRequest",
    # Validators
    "validate_model_name_basic",
    "validate_model_name_extended",
    "validate_huggingface_model_name",
    "validate_ollama_model_name",
    "validate_provider",
    "validate_runtime",
]
