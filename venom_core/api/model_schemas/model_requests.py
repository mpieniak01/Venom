"""Modele Pydantic dla requestów API związanych z modelami AI."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from venom_core.api.model_schemas.model_validators import (
    validate_huggingface_model_name,
    validate_model_name_basic,
    validate_model_name_extended,
    validate_ollama_model_name,
    validate_provider,
    validate_runtime,
)


class ModelInstallRequest(BaseModel):
    """Request do instalacji modelu."""

    name: str

    @field_validator("name")
    def validate_name(cls, v):
        return validate_model_name_basic(v, max_length=100)


class ModelSwitchRequest(BaseModel):
    """Request do zmiany aktywnego modelu."""

    name: str
    role: Optional[str] = (
        None  # Opcjonalnie: dla jakiej roli (np. "reasoning", "creative")
    )

    @field_validator("name")
    def validate_name(cls, v):
        return validate_model_name_basic(v, max_length=100)


class ModelRegistryInstallRequest(BaseModel):
    """Request do instalacji modelu przez ModelRegistry."""

    name: str
    provider: str  # "huggingface" lub "ollama"
    runtime: str = "vllm"  # "vllm" lub "ollama"

    @field_validator("name")
    def validate_name(cls, v):
        return validate_model_name_extended(v, max_length=200)

    @field_validator("provider")
    def validate_provider(cls, v):
        return validate_provider(v)

    @field_validator("runtime")
    def validate_runtime(cls, v):
        return validate_runtime(v)

    def model_post_init(self, __context):
        """Validate model name format based on provider."""
        if self.provider == "huggingface":
            validate_huggingface_model_name(self.name)
            if self.runtime != "vllm":
                raise ValueError("Runtime dla HuggingFace musi być 'vllm'")
        elif self.provider == "ollama":
            validate_ollama_model_name(self.name)
            if self.runtime != "ollama":
                raise ValueError("Runtime dla Ollama musi być 'ollama'")


class ModelActivateRequest(BaseModel):
    """Request do aktywacji modelu."""

    name: str
    runtime: str

    @field_validator("name")
    def validate_name(cls, v):
        return validate_model_name_extended(v, max_length=200)

    @field_validator("runtime")
    def validate_runtime(cls, v):
        return validate_runtime(v)


class TranslationRequest(BaseModel):
    """Request do tłumaczenia tekstu."""

    text: str
    target_lang: str = "pl"
    source_lang: Optional[str] = None
    use_cache: bool = True


class ModelConfigUpdateRequest(BaseModel):
    """Request do aktualizacji parametrów generacji modelu."""

    runtime: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
