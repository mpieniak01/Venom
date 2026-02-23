"""Testy jednostkowe dla model_validators."""

import pytest

from venom_core.api.model_schemas.model_validators import (
    validate_huggingface_model_name,
    validate_model_name_basic,
    validate_model_name_extended,
    validate_ollama_model_name,
    validate_provider,
)


class TestValidateModelNameBasic:
    """Testy dla validate_model_name_basic."""

    def test_valid_model_name(self):
        """Test z poprawną nazwą modelu."""
        result = validate_model_name_basic("gpt-4")
        assert result == "gpt-4"

    def test_valid_model_name_with_dots(self):
        """Test z kropkami w nazwie."""
        result = validate_model_name_basic("model.v1.2")
        assert result == "model.v1.2"

    def test_valid_model_name_with_colon(self):
        """Test z dwukropkiem w nazwie."""
        result = validate_model_name_basic("model:latest")
        assert result == "model:latest"

    def test_valid_model_name_with_underscore(self):
        """Test z podkreśleniem w nazwie."""
        result = validate_model_name_basic("my_model_v1")
        assert result == "my_model_v1"

    def test_empty_model_name(self):
        """Test z pustą nazwą modelu."""
        with pytest.raises(ValueError, match="Nazwa modelu musi mieć"):
            validate_model_name_basic("")

    def test_none_model_name(self):
        """Test z None jako nazwą."""
        with pytest.raises((ValueError, AttributeError)):
            validate_model_name_basic(None)

    def test_too_long_model_name(self):
        """Test z zbyt długą nazwą modelu."""
        long_name = "a" * 101
        with pytest.raises(ValueError, match="Nazwa modelu musi mieć"):
            validate_model_name_basic(long_name)

    def test_custom_max_length(self):
        """Test z niestandardową maksymalną długością."""
        result = validate_model_name_basic("short", max_length=10)
        assert result == "short"

        with pytest.raises(ValueError):
            validate_model_name_basic("toolongname", max_length=5)

    def test_invalid_characters(self):
        """Test z niedozwolonymi znakami."""
        with pytest.raises(ValueError, match="niedozwolone znaki"):
            validate_model_name_basic("model@name")

        with pytest.raises(ValueError, match="niedozwolone znaki"):
            validate_model_name_basic("model name")  # spacja

        with pytest.raises(ValueError, match="niedozwolone znaki"):
            validate_model_name_basic("model#123")


class TestValidateModelNameExtended:
    """Testy dla validate_model_name_extended."""

    def test_valid_model_name_with_slash(self):
        """Test z slashem w nazwie (dozwolone w extended)."""
        result = validate_model_name_extended("org/model")
        assert result == "org/model"

    def test_valid_model_name_with_multiple_slashes(self):
        """Test z wieloma slashami."""
        result = validate_model_name_extended("org/subdir/model")
        assert result == "org/subdir/model"

    def test_empty_model_name(self):
        """Test z pustą nazwą."""
        with pytest.raises(ValueError, match="Nazwa modelu musi mieć"):
            validate_model_name_extended("")

    def test_too_long_model_name(self):
        """Test z zbyt długą nazwą."""
        long_name = "a" * 201
        with pytest.raises(ValueError):
            validate_model_name_extended(long_name)

    def test_invalid_characters(self):
        """Test z niedozwolonymi znakami."""
        with pytest.raises(ValueError, match="niedozwolone znaki"):
            validate_model_name_extended("model@name")


class TestValidateHuggingfaceModelName:
    """Testy dla validate_huggingface_model_name."""

    def test_valid_huggingface_name(self):
        """Test z poprawną nazwą HuggingFace."""
        result = validate_huggingface_model_name("bert-base-uncased/model")
        assert result == "bert-base-uncased/model"

    def test_valid_org_model_format(self):
        """Test formatu org/model."""
        result = validate_huggingface_model_name("openai/gpt-2")
        assert result == "openai/gpt-2"

    def test_missing_slash(self):
        """Test bez slasha (niepoprawny format)."""
        with pytest.raises(ValueError, match="org/model"):
            validate_huggingface_model_name("model-name")

    def test_invalid_format(self):
        """Test z niepoprawnym formatem."""
        with pytest.raises(ValueError, match="Invalid HuggingFace"):
            validate_huggingface_model_name("org/model@version")

    def test_empty_org(self):
        """Test z pustą organizacją."""
        with pytest.raises(ValueError):
            validate_huggingface_model_name("/model")

    def test_empty_model(self):
        """Test z pustą nazwą modelu."""
        with pytest.raises(ValueError):
            validate_huggingface_model_name("org/")


class TestValidateOllamaModelName:
    """Testy dla validate_ollama_model_name."""

    def test_valid_ollama_name(self):
        """Test z poprawną nazwą Ollama."""
        result = validate_ollama_model_name("llama2")
        assert result == "llama2"

    def test_valid_with_version(self):
        """Test z wersją."""
        result = validate_ollama_model_name("llama2:13b")
        assert result == "llama2:13b"

    def test_valid_with_tag(self):
        """Test z tagiem."""
        result = validate_ollama_model_name("mistral:latest")
        assert result == "mistral:latest"

    def test_invalid_with_slash(self):
        """Test ze slashem (niedozwolony w Ollama)."""
        with pytest.raises(ValueError, match="cannot contain forward slashes"):
            validate_ollama_model_name("org/model")

    def test_invalid_characters(self):
        """Test z niedozwolonymi znakami."""
        with pytest.raises(ValueError, match="Invalid Ollama"):
            validate_ollama_model_name("model@name")


class TestValidateProvider:
    """Testy dla validate_provider."""

    def test_valid_provider_ollama(self):
        """Test z poprawnym providerem Ollama."""
        result = validate_provider("ollama")
        assert result == "ollama"

    def test_valid_provider_huggingface(self):
        """Test z poprawnym providerem HuggingFace."""
        result = validate_provider("huggingface")
        assert result == "huggingface"

    def test_invalid_provider_openai(self):
        """Test z niepoprawnym providerem OpenAI (nie jest obsługiwany)."""
        with pytest.raises(ValueError, match="huggingface.*ollama"):
            validate_provider("openai")

    def test_invalid_provider_anthropic(self):
        """Test z niepoprawnym providerem Anthropic (nie jest obsługiwany)."""
        with pytest.raises(ValueError, match="huggingface.*ollama"):
            validate_provider("anthropic")

    def test_empty_provider(self):
        """Test z pustym providerem."""
        with pytest.raises(ValueError):
            validate_provider("")

    def test_invalid_provider_random(self):
        """Test z losowym niepoprawnym providerem."""
        with pytest.raises(ValueError, match="huggingface.*ollama"):
            validate_provider("random_provider")
