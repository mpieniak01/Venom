"""Compatibility validation for Control Plane configuration changes.

This module provides compatibility checking between different system components:
- Kernel x Runtime x Provider x Embedding Model x Intent Mode
"""

from dataclasses import dataclass
from typing import Any

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CompatibilityMatrix:
    """Matrix defining compatible combinations of system components."""

    # Kernel compatibility with runtimes
    kernel_runtime: dict[str, list[str]]

    # Runtime compatibility with providers
    runtime_provider: dict[str, list[str]]

    # Provider compatibility with models
    provider_models: dict[str, list[str]]

    # Embedding model compatibility
    embedding_compatibility: dict[str, list[str]]

    # Intent mode requirements
    intent_mode_requirements: dict[str, dict[str, Any]]


# Default compatibility matrix
DEFAULT_COMPATIBILITY_MATRIX = CompatibilityMatrix(
    kernel_runtime={
        "standard": ["python", "docker", "hybrid"],
        "optimized": ["python", "docker"],
        "minimal": ["python"],
    },
    runtime_provider={
        "python": ["huggingface", "ollama", "openai", "google"],
        "docker": ["vllm", "ollama", "huggingface"],
        "hybrid": ["ollama", "openai", "google"],
    },
    provider_models={
        "huggingface": ["bert", "gpt2", "roberta", "distilbert"],
        "ollama": ["llama2", "llama3", "mistral", "phi"],
        "vllm": ["llama2", "mistral"],
        "openai": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
        "google": ["gemini-pro", "gemini-pro-vision"],
    },
    embedding_compatibility={
        "sentence-transformers": ["huggingface", "ollama"],
        "openai-embeddings": ["openai"],
        "google-embeddings": ["google"],
    },
    intent_mode_requirements={
        "simple": {"min_model_size": "small", "requires_embedding": False},
        "advanced": {"min_model_size": "medium", "requires_embedding": True},
        "expert": {"min_model_size": "large", "requires_embedding": True},
    },
)


class CompatibilityValidator:
    """Validates compatibility between system components."""

    def __init__(self, matrix: CompatibilityMatrix = DEFAULT_COMPATIBILITY_MATRIX):
        """Initialize validator with compatibility matrix.

        Args:
            matrix: Compatibility matrix to use for validation
        """
        self.matrix = matrix

    def validate_kernel_runtime(self, kernel: str, runtime: str) -> tuple[bool, str]:
        """Validate kernel and runtime compatibility.

        Args:
            kernel: Kernel type
            runtime: Runtime type

        Returns:
            Tuple of (is_compatible, message)
        """
        if kernel not in self.matrix.kernel_runtime:
            return False, f"Unknown kernel type: {kernel}"

        compatible_runtimes = self.matrix.kernel_runtime[kernel]
        if runtime not in compatible_runtimes:
            return (
                False,
                f"Kernel '{kernel}' not compatible with runtime '{runtime}'. "
                f"Compatible runtimes: {', '.join(compatible_runtimes)}",
            )

        return True, "Kernel and runtime are compatible"

    def validate_runtime_provider(
        self, runtime: str, provider: str
    ) -> tuple[bool, str]:
        """Validate runtime and provider compatibility.

        Args:
            runtime: Runtime type
            provider: Provider type

        Returns:
            Tuple of (is_compatible, message)
        """
        if runtime not in self.matrix.runtime_provider:
            return False, f"Unknown runtime type: {runtime}"

        compatible_providers = self.matrix.runtime_provider[runtime]
        if provider not in compatible_providers:
            return (
                False,
                f"Runtime '{runtime}' not compatible with provider '{provider}'. "
                f"Compatible providers: {', '.join(compatible_providers)}",
            )

        return True, "Runtime and provider are compatible"

    def validate_provider_model(self, provider: str, model: str) -> tuple[bool, str]:
        """Validate provider and model compatibility.

        Args:
            provider: Provider type
            model: Model name

        Returns:
            Tuple of (is_compatible, message)
        """
        if provider not in self.matrix.provider_models:
            return False, f"Unknown provider type: {provider}"

        # Validate model against provider's supported models
        compatible_models = self.matrix.provider_models[provider]
        if model not in compatible_models:
            return (
                False,
                f"Provider '{provider}' not compatible with model '{model}'. "
                f"Compatible models: {', '.join(compatible_models)}",
            )

        return True, "Provider and model are compatible"

    def validate_embedding_model(
        self, embedding_model: str, provider: str
    ) -> tuple[bool, str]:
        """Validate embedding model and provider compatibility.

        Args:
            embedding_model: Embedding model type
            provider: Provider type

        Returns:
            Tuple of (is_compatible, message)
        """
        if embedding_model not in self.matrix.embedding_compatibility:
            return False, f"Unknown embedding model: {embedding_model}"

        compatible_providers = self.matrix.embedding_compatibility[embedding_model]
        if provider not in compatible_providers:
            return (
                False,
                f"Embedding model '{embedding_model}' not compatible with "
                f"provider '{provider}'. "
                f"Compatible providers: {', '.join(compatible_providers)}",
            )

        return True, "Embedding model and provider are compatible"

    def validate_intent_mode(
        self, intent_mode: str, model_size: str, has_embedding: bool
    ) -> tuple[bool, str]:
        """Validate intent mode requirements.

        Args:
            intent_mode: Intent mode
            model_size: Model size (small, medium, large)
            has_embedding: Whether embedding model is configured

        Returns:
            Tuple of (is_compatible, message)
        """
        if intent_mode not in self.matrix.intent_mode_requirements:
            return False, f"Unknown intent mode: {intent_mode}"

        requirements = self.matrix.intent_mode_requirements[intent_mode]
        _ = model_size  # Reserved for future per-size intent constraints

        if requirements.get("requires_embedding") and not has_embedding:
            return (
                False,
                f"Intent mode '{intent_mode}' requires embedding model",
            )

        return True, "Intent mode requirements satisfied"

    def validate_full_stack(
        self,
        kernel: str,
        runtime: str,
        provider: str,
        model: str,
        embedding_model: str,
        intent_mode: str,
    ) -> tuple[bool, list[str]]:
        """Validate entire stack configuration.

        Args:
            kernel: Kernel type
            runtime: Runtime type
            provider: Provider type
            model: Model name
            embedding_model: Embedding model type
            intent_mode: Intent mode

        Returns:
            Tuple of (is_compatible, list of issues)
        """
        issues = []

        # Validate kernel x runtime
        compatible, msg = self.validate_kernel_runtime(kernel, runtime)
        if not compatible:
            issues.append(msg)

        # Validate runtime x provider
        compatible, msg = self.validate_runtime_provider(runtime, provider)
        if not compatible:
            issues.append(msg)

        # Validate provider x model
        compatible, msg = self.validate_provider_model(provider, model)
        if not compatible:
            issues.append(msg)

        # Validate embedding
        if embedding_model:
            compatible, msg = self.validate_embedding_model(embedding_model, provider)
            if not compatible:
                issues.append(msg)

        # Validate intent mode
        has_embedding = bool(embedding_model)
        model_size = "medium"  # Default, would come from model metadata
        compatible, msg = self.validate_intent_mode(
            intent_mode, model_size, has_embedding
        )
        if not compatible:
            issues.append(msg)

        return len(issues) == 0, issues


# Singleton instance
_compatibility_validator: CompatibilityValidator | None = None


def get_compatibility_validator() -> CompatibilityValidator:
    """Get singleton compatibility validator instance.

    Returns:
        CompatibilityValidator instance
    """
    global _compatibility_validator
    if _compatibility_validator is None:
        _compatibility_validator = CompatibilityValidator()
    return _compatibility_validator
