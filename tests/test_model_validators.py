"""Unit tests for model_validators."""

import pytest

from venom_core.api.model_schemas.model_validators import (
    validate_huggingface_model_name,
    validate_model_name_basic,
    validate_model_name_extended,
    validate_ollama_model_name,
    validate_provider,
)


class TestValidateModelNameBasic:
    """Tests for validate_model_name_basic."""

    def test_valid_model_name(self):
        """Test with a valid model name."""
        result = validate_model_name_basic("gpt-4")
        assert result == "gpt-4"

    def test_valid_model_name_with_dots(self):
        """Test with dots in the name."""
        result = validate_model_name_basic("model.v1.2")
        assert result == "model.v1.2"

    def test_valid_model_name_with_colon(self):
        """Test with a colon in the name."""
        result = validate_model_name_basic("model:latest")
        assert result == "model:latest"

    def test_valid_model_name_with_underscore(self):
        """Test with an underscore in the name."""
        result = validate_model_name_basic("my_model_v1")
        assert result == "my_model_v1"

    def test_empty_model_name(self):
        """Test with empty model name."""
        with pytest.raises(ValueError, match="Nazwa modelu musi mieć"):
            validate_model_name_basic("")

    def test_none_model_name(self):
        """Test with None as the name."""
        with pytest.raises((ValueError, AttributeError)):
            validate_model_name_basic(None)

    def test_too_long_model_name(self):
        """Test with a model name that is too long."""
        long_name = "a" * 101
        with pytest.raises(ValueError, match="Nazwa modelu musi mieć"):
            validate_model_name_basic(long_name)

    def test_custom_max_length(self):
        """Test with a custom maximum length."""
        result = validate_model_name_basic("short", max_length=10)
        assert result == "short"

        with pytest.raises(ValueError):
            validate_model_name_basic("toolongname", max_length=5)

    def test_invalid_characters(self):
        """Test with invalid characters."""
        with pytest.raises(ValueError, match="niedozwolone znaki"):
            validate_model_name_basic("model@name")

        with pytest.raises(ValueError, match="niedozwolone znaki"):
            validate_model_name_basic("model name")  # spacja

        with pytest.raises(ValueError, match="niedozwolone znaki"):
            validate_model_name_basic("model#123")


class TestValidateModelNameExtended:
    """Tests for validate_model_name_extended."""

    def test_valid_model_name_with_slash(self):
        """Test with a slash in the name (allowed in extended)."""
        result = validate_model_name_extended("org/model")
        assert result == "org/model"

    def test_valid_model_name_with_multiple_slashes(self):
        """Test with multiple slashes."""
        result = validate_model_name_extended("org/subdir/model")
        assert result == "org/subdir/model"

    def test_empty_model_name(self):
        """Test with empty name."""
        with pytest.raises(ValueError, match="Nazwa modelu musi mieć"):
            validate_model_name_extended("")

    def test_too_long_model_name(self):
        """Test with a name that is too long."""
        long_name = "a" * 201
        with pytest.raises(ValueError):
            validate_model_name_extended(long_name)

    def test_invalid_characters(self):
        """Test with invalid characters."""
        with pytest.raises(ValueError, match="niedozwolone znaki"):
            validate_model_name_extended("model@name")


class TestValidateHuggingfaceModelName:
    """Tests for validate_huggingface_model_name."""

    def test_valid_huggingface_name(self):
        """Test with a valid HuggingFace name."""
        result = validate_huggingface_model_name("bert-base-uncased/model")
        assert result == "bert-base-uncased/model"

    def test_valid_org_model_format(self):
        """Test org/model format."""
        result = validate_huggingface_model_name("openai/gpt-2")
        assert result == "openai/gpt-2"

    def test_missing_slash(self):
        """Test without slash (invalid format)."""
        with pytest.raises(ValueError, match="org/model"):
            validate_huggingface_model_name("model-name")

    def test_invalid_format(self):
        """Test with invalid format."""
        with pytest.raises(ValueError, match="Invalid HuggingFace"):
            validate_huggingface_model_name("org/model@version")

    def test_empty_org(self):
        """Test with empty organization."""
        with pytest.raises(ValueError):
            validate_huggingface_model_name("/model")

    def test_empty_model(self):
        """Test with empty model name."""
        with pytest.raises(ValueError):
            validate_huggingface_model_name("org/")


class TestValidateOllamaModelName:
    """Tests for validate_ollama_model_name."""

    def test_valid_ollama_name(self):
        """Test with a valid Ollama name."""
        result = validate_ollama_model_name("llama2")
        assert result == "llama2"

    def test_valid_with_version(self):
        """Test with a version tag."""
        result = validate_ollama_model_name("llama2:13b")
        assert result == "llama2:13b"

    def test_valid_with_tag(self):
        """Test with a tag."""
        result = validate_ollama_model_name("mistral:latest")
        assert result == "mistral:latest"

    def test_invalid_with_slash(self):
        """Test with a slash (not allowed in Ollama)."""
        with pytest.raises(ValueError, match="cannot contain forward slashes"):
            validate_ollama_model_name("org/model")

    def test_invalid_characters(self):
        """Test with invalid characters."""
        with pytest.raises(ValueError, match="Invalid Ollama"):
            validate_ollama_model_name("model@name")


class TestValidateProvider:
    """Tests for validate_provider."""

    def test_valid_provider_ollama(self):
        """Test with valid Ollama provider."""
        result = validate_provider("ollama")
        assert result == "ollama"

    def test_valid_provider_huggingface(self):
        """Test with valid HuggingFace provider."""
        result = validate_provider("huggingface")
        assert result == "huggingface"

    def test_invalid_provider_openai(self):
        """Test with unsupported OpenAI provider."""
        with pytest.raises(ValueError, match="huggingface.*ollama"):
            validate_provider("openai")

    def test_invalid_provider_anthropic(self):
        """Test with unsupported Anthropic provider."""
        with pytest.raises(ValueError, match="huggingface.*ollama"):
            validate_provider("anthropic")

    def test_empty_provider(self):
        """Test with empty provider."""
        with pytest.raises(ValueError):
            validate_provider("")

    def test_invalid_provider_random(self):
        """Test with a random invalid provider."""
        with pytest.raises(ValueError, match="huggingface.*ollama"):
            validate_provider("random_provider")
