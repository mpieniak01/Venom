"""Tests for Control Plane compatibility validation."""

import pytest

from venom_core.services.control_plane_compatibility import (
    CompatibilityMatrix,
    CompatibilityValidator,
    get_compatibility_validator,
)


class TestCompatibilityValidator:
    """Test compatibility validation logic."""

    @pytest.fixture
    def validator(self):
        """Fixture providing a compatibility validator."""
        return get_compatibility_validator()

    def test_kernel_runtime_compatible(self, validator):
        """Test compatible kernel and runtime combination."""
        compatible, message = validator.validate_kernel_runtime("standard", "python")
        assert compatible is True
        assert "compatible" in message.lower()

    def test_kernel_runtime_incompatible(self, validator):
        """Test incompatible kernel and runtime combination."""
        compatible, message = validator.validate_kernel_runtime("minimal", "docker")
        assert compatible is False
        assert "not compatible" in message.lower()
        assert "python" in message.lower()  # Should list compatible runtimes

    def test_kernel_runtime_unknown_kernel(self, validator):
        """Test validation with unknown kernel type."""
        compatible, message = validator.validate_kernel_runtime("unknown", "python")
        assert compatible is False
        assert "unknown" in message.lower()

    def test_runtime_provider_compatible(self, validator):
        """Test compatible runtime and provider combination."""
        compatible, message = validator.validate_runtime_provider("python", "ollama")
        assert compatible is True
        assert "compatible" in message.lower()

        compatible, _ = validator.validate_runtime_provider("python", "onnx")
        assert compatible is True

    def test_runtime_provider_incompatible(self, validator):
        """Test incompatible runtime and provider combination."""
        # Use python runtime with vllm provider (vllm not in python's compatible providers)
        compatible, message = validator.validate_runtime_provider("python", "vllm")
        assert compatible is False
        assert "not compatible" in message.lower()

    def test_runtime_provider_unknown_runtime(self, validator):
        """Test validation with unknown runtime type."""
        compatible, message = validator.validate_runtime_provider("unknown", "ollama")
        assert compatible is False
        assert "unknown" in message.lower()

    def test_provider_model_known_provider(self, validator):
        """Test provider model validation with known provider."""
        compatible, message = validator.validate_provider_model("ollama", "llama2")
        assert compatible is True
        compatible, _ = validator.validate_provider_model("onnx", "phi")
        assert compatible is True

    def test_provider_model_unknown_provider(self, validator):
        """Test provider model validation with unknown provider."""
        compatible, message = validator.validate_provider_model("unknown", "model")
        assert compatible is False
        assert "unknown" in message.lower()

    def test_embedding_model_compatible(self, validator):
        """Test compatible embedding model and provider."""
        compatible, message = validator.validate_embedding_model(
            "sentence-transformers", "huggingface"
        )
        assert compatible is True

    def test_embedding_model_incompatible(self, validator):
        """Test incompatible embedding model and provider."""
        compatible, message = validator.validate_embedding_model(
            "openai-embeddings", "ollama"
        )
        assert compatible is False
        assert "not compatible" in message.lower()

    def test_embedding_model_unknown(self, validator):
        """Test validation with unknown embedding model."""
        compatible, message = validator.validate_embedding_model("unknown", "ollama")
        assert compatible is False
        assert "unknown" in message.lower()

    def test_intent_mode_simple_no_embedding(self, validator):
        """Test simple intent mode without embedding."""
        compatible, message = validator.validate_intent_mode(
            "simple", "small", has_embedding=False
        )
        assert compatible is True

    def test_intent_mode_advanced_requires_embedding(self, validator):
        """Test advanced intent mode requires embedding."""
        compatible, message = validator.validate_intent_mode(
            "advanced", "medium", has_embedding=False
        )
        assert compatible is False
        assert "requires embedding" in message.lower()

    def test_intent_mode_advanced_with_embedding(self, validator):
        """Test advanced intent mode with embedding."""
        compatible, message = validator.validate_intent_mode(
            "advanced", "medium", has_embedding=True
        )
        assert compatible is True

    def test_intent_mode_unknown(self, validator):
        """Test validation with unknown intent mode."""
        compatible, message = validator.validate_intent_mode(
            "unknown", "medium", has_embedding=True
        )
        assert compatible is False
        assert "unknown" in message.lower()

    def test_full_stack_compatible(self, validator):
        """Test full stack validation with compatible configuration."""
        compatible, issues = validator.validate_full_stack(
            kernel="standard",
            runtime="python",
            provider="ollama",
            model="llama2",
            embedding_model="sentence-transformers",
            intent_mode="advanced",
        )
        assert compatible is True
        assert len(issues) == 0

    def test_full_stack_incompatible_kernel_runtime(self, validator):
        """Test full stack validation with incompatible kernel-runtime."""
        compatible, issues = validator.validate_full_stack(
            kernel="minimal",
            runtime="docker",
            provider="ollama",
            model="llama2",
            embedding_model="",
            intent_mode="simple",
        )
        assert compatible is False
        assert len(issues) > 0
        assert any("kernel" in issue.lower() for issue in issues)

    def test_full_stack_incompatible_runtime_provider(self, validator):
        """Test full stack validation with incompatible runtime-provider."""
        compatible, issues = validator.validate_full_stack(
            kernel="standard",
            runtime="hybrid",
            provider="vllm",
            model="llama2",
            embedding_model="",
            intent_mode="simple",
        )
        assert compatible is False
        assert len(issues) > 0
        assert any("runtime" in issue.lower() for issue in issues)

    def test_full_stack_missing_embedding_for_advanced_intent(self, validator):
        """Test full stack validation missing embedding for advanced intent."""
        compatible, issues = validator.validate_full_stack(
            kernel="standard",
            runtime="python",
            provider="ollama",
            model="llama2",
            embedding_model="",
            intent_mode="advanced",
        )
        assert compatible is False
        assert len(issues) > 0
        assert any("embedding" in issue.lower() for issue in issues)

    def test_full_stack_multiple_issues(self, validator):
        """Test full stack validation with multiple compatibility issues."""
        compatible, issues = validator.validate_full_stack(
            kernel="minimal",
            runtime="docker",
            provider="vllm",
            model="llama2",
            embedding_model="",
            intent_mode="advanced",
        )
        assert compatible is False
        assert len(issues) > 1  # Should have multiple issues


class TestCompatibilityMatrix:
    """Test compatibility matrix structure."""

    def test_matrix_has_kernel_runtime_mapping(self):
        """Test matrix contains kernel-runtime mappings."""
        from venom_core.services.control_plane_compatibility import (
            DEFAULT_COMPATIBILITY_MATRIX,
        )

        assert "standard" in DEFAULT_COMPATIBILITY_MATRIX.kernel_runtime
        assert "python" in DEFAULT_COMPATIBILITY_MATRIX.kernel_runtime["standard"]

    def test_matrix_has_runtime_provider_mapping(self):
        """Test matrix contains runtime-provider mappings."""
        from venom_core.services.control_plane_compatibility import (
            DEFAULT_COMPATIBILITY_MATRIX,
        )

        assert "python" in DEFAULT_COMPATIBILITY_MATRIX.runtime_provider
        assert "ollama" in DEFAULT_COMPATIBILITY_MATRIX.runtime_provider["python"]

    def test_matrix_has_provider_models_mapping(self):
        """Test matrix contains provider-models mappings."""
        from venom_core.services.control_plane_compatibility import (
            DEFAULT_COMPATIBILITY_MATRIX,
        )

        assert "ollama" in DEFAULT_COMPATIBILITY_MATRIX.provider_models
        assert len(DEFAULT_COMPATIBILITY_MATRIX.provider_models["ollama"]) > 0

    def test_matrix_has_embedding_compatibility(self):
        """Test matrix contains embedding compatibility mappings."""
        from venom_core.services.control_plane_compatibility import (
            DEFAULT_COMPATIBILITY_MATRIX,
        )

        assert (
            "sentence-transformers"
            in DEFAULT_COMPATIBILITY_MATRIX.embedding_compatibility
        )

    def test_matrix_has_intent_mode_requirements(self):
        """Test matrix contains intent mode requirements."""
        from venom_core.services.control_plane_compatibility import (
            DEFAULT_COMPATIBILITY_MATRIX,
        )

        assert "simple" in DEFAULT_COMPATIBILITY_MATRIX.intent_mode_requirements
        assert "advanced" in DEFAULT_COMPATIBILITY_MATRIX.intent_mode_requirements

    def test_custom_matrix_creation(self):
        """Test creating a custom compatibility matrix."""
        custom_matrix = CompatibilityMatrix(
            kernel_runtime={"custom_kernel": ["custom_runtime"]},
            runtime_provider={"custom_runtime": ["custom_provider"]},
            provider_models={"custom_provider": ["custom_model"]},
            embedding_compatibility={"custom_embedding": ["custom_provider"]},
            intent_mode_requirements={"custom_mode": {"requires_embedding": False}},
        )

        validator = CompatibilityValidator(matrix=custom_matrix)
        compatible, _ = validator.validate_kernel_runtime(
            "custom_kernel", "custom_runtime"
        )
        assert compatible is True


class TestValidatorSingleton:
    """Test singleton pattern for validator."""

    def test_get_compatibility_validator_returns_singleton(self):
        """Test that get_compatibility_validator returns same instance."""
        validator1 = get_compatibility_validator()
        validator2 = get_compatibility_validator()
        assert validator1 is validator2
