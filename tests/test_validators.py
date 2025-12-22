"""Testy jednostkowe dla modułu validators."""

import pytest

from venom_core.api.validators import (
    validate_generation_params,
    validate_huggingface_model_name,
    validate_model_name,
    validate_ollama_model_name,
    validate_provider,
    validate_runtime,
)


class TestValidateModelName:
    """Testy dla validate_model_name."""

    def test_valid_name_without_slash(self):
        """Test walidacji poprawnej nazwy bez ukośników."""
        result = validate_model_name("phi3:latest", max_length=100, allow_slash=False)
        assert result == "phi3:latest"

    def test_valid_name_with_slash(self):
        """Test walidacji poprawnej nazwy z ukośnikami."""
        result = validate_model_name(
            "google/gemma-2b", max_length=100, allow_slash=True
        )
        assert result == "google/gemma-2b"

    def test_empty_name(self):
        """Test walidacji pustej nazwy."""
        with pytest.raises(ValueError, match="Nazwa modelu musi mieć"):
            validate_model_name("", max_length=100)

    def test_name_too_long(self):
        """Test walidacji zbyt długiej nazwy."""
        long_name = "a" * 101
        with pytest.raises(ValueError, match="Nazwa modelu musi mieć"):
            validate_model_name(long_name, max_length=100)

    def test_invalid_characters(self):
        """Test walidacji nazwy z niedozwolonymi znakami."""
        with pytest.raises(ValueError, match="Nazwa modelu zawiera niedozwolone znaki"):
            validate_model_name("model@#$%", max_length=100)

    def test_slash_not_allowed(self):
        """Test walidacji nazwy z ukośnikiem gdy nie jest dozwolony."""
        with pytest.raises(ValueError, match="Nazwa modelu zawiera niedozwolone znaki"):
            validate_model_name("org/model", max_length=100, allow_slash=False)

    def test_valid_special_characters(self):
        """Test walidacji nazwy z dozwolonymi znakami specjalnymi."""
        result = validate_model_name("model-name_v1.0:latest", max_length=100)
        assert result == "model-name_v1.0:latest"


class TestValidateHuggingFaceModelName:
    """Testy dla validate_huggingface_model_name."""

    def test_valid_huggingface_name(self):
        """Test walidacji poprawnej nazwy HuggingFace."""
        result = validate_huggingface_model_name("google/gemma-2b-it")
        assert result == "google/gemma-2b-it"

    def test_missing_slash(self):
        """Test walidacji nazwy bez ukośnika (niepoprawny format)."""
        with pytest.raises(
            ValueError, match="Model HuggingFace musi być w formacie 'org/model'"
        ):
            validate_huggingface_model_name("gemma-2b-it")

    def test_invalid_format(self):
        """Test walidacji nazwy z niepoprawnym formatem."""
        with pytest.raises(
            ValueError, match="Nieprawidłowy format nazwy modelu HuggingFace"
        ):
            validate_huggingface_model_name("org//model")

    def test_valid_with_version(self):
        """Test walidacji nazwy z wersją."""
        result = validate_huggingface_model_name("microsoft/phi-3-mini:v1.0")
        assert result == "microsoft/phi-3-mini:v1.0"


class TestValidateOllamaModelName:
    """Testy dla validate_ollama_model_name."""

    def test_valid_ollama_name(self):
        """Test walidacji poprawnej nazwy Ollama."""
        result = validate_ollama_model_name("phi3:latest")
        assert result == "phi3:latest"

    def test_name_with_slash(self):
        """Test walidacji nazwy z ukośnikiem (niepoprawne dla Ollama)."""
        with pytest.raises(
            ValueError, match="Nazwy modeli Ollama nie mogą zawierać ukośników"
        ):
            validate_ollama_model_name("org/model")

    def test_invalid_characters(self):
        """Test walidacji nazwy z niepoprawnym formatem."""
        with pytest.raises(
            ValueError, match="Nieprawidłowy format nazwy modelu Ollama"
        ):
            validate_ollama_model_name("model@#$")

    def test_valid_with_tag(self):
        """Test walidacji nazwy z tagiem."""
        result = validate_ollama_model_name("llama-3:8b")
        assert result == "llama-3:8b"


class TestValidateProvider:
    """Testy dla validate_provider."""

    def test_valid_huggingface_provider(self):
        """Test walidacji providera HuggingFace."""
        result = validate_provider("huggingface")
        assert result == "huggingface"

    def test_valid_ollama_provider(self):
        """Test walidacji providera Ollama."""
        result = validate_provider("ollama")
        assert result == "ollama"

    def test_invalid_provider(self):
        """Test walidacji niepoprawnego providera."""
        with pytest.raises(
            ValueError, match="Provider musi być 'huggingface' lub 'ollama'"
        ):
            validate_provider("invalid")


class TestValidateRuntime:
    """Testy dla validate_runtime."""

    def test_valid_vllm_runtime(self):
        """Test walidacji runtime vLLM."""
        result = validate_runtime("vllm")
        assert result == "vllm"

    def test_valid_ollama_runtime(self):
        """Test walidacji runtime Ollama."""
        result = validate_runtime("ollama")
        assert result == "ollama"

    def test_invalid_runtime(self):
        """Test walidacji niepoprawnego runtime."""
        with pytest.raises(ValueError, match="Runtime musi być 'vllm' lub 'ollama'"):
            validate_runtime("invalid")


class TestValidateGenerationParams:
    """Testy dla validate_generation_params."""

    def test_valid_float_param(self):
        """Test walidacji parametru float."""
        schema = {"temperature": {"type": "float", "min": 0.0, "max": 1.0}}
        params = {"temperature": 0.7}

        result = validate_generation_params(params, schema)

        assert result == {"temperature": 0.7}

    def test_float_param_below_min(self):
        """Test walidacji parametru float poniżej minimum."""
        schema = {"temperature": {"type": "float", "min": 0.0, "max": 1.0}}
        params = {"temperature": -0.1}

        with pytest.raises(ValueError, match="musi być >="):
            validate_generation_params(params, schema)

    def test_float_param_above_max(self):
        """Test walidacji parametru float powyżej maksimum."""
        schema = {"temperature": {"type": "float", "min": 0.0, "max": 1.0}}
        params = {"temperature": 1.5}

        with pytest.raises(ValueError, match="musi być <="):
            validate_generation_params(params, schema)

    def test_valid_int_param(self):
        """Test walidacji parametru int."""
        schema = {"max_tokens": {"type": "int", "min": 1, "max": 4096}}
        params = {"max_tokens": 2048}

        result = validate_generation_params(params, schema)

        assert result == {"max_tokens": 2048}

    def test_int_param_below_min(self):
        """Test walidacji parametru int poniżej minimum."""
        schema = {"max_tokens": {"type": "int", "min": 1, "max": 4096}}
        params = {"max_tokens": 0}

        with pytest.raises(ValueError, match="musi być >="):
            validate_generation_params(params, schema)

    def test_valid_bool_param(self):
        """Test walidacji parametru bool."""
        schema = {"stream": {"type": "bool"}}
        params = {"stream": True}

        result = validate_generation_params(params, schema)

        assert result == {"stream": True}

    def test_invalid_bool_param(self):
        """Test walidacji niepoprawnego parametru bool."""
        schema = {"stream": {"type": "bool"}}
        params = {"stream": "yes"}

        with pytest.raises(ValueError, match="musi być wartością logiczną"):
            validate_generation_params(params, schema)

    def test_valid_enum_param(self):
        """Test walidacji parametru enum."""
        schema = {"mode": {"type": "enum", "options": ["fast", "balanced", "quality"]}}
        params = {"mode": "balanced"}

        result = validate_generation_params(params, schema)

        assert result == {"mode": "balanced"}

    def test_invalid_enum_value(self):
        """Test walidacji niepoprawnej wartości enum."""
        schema = {"mode": {"type": "enum", "options": ["fast", "balanced", "quality"]}}
        params = {"mode": "invalid"}

        with pytest.raises(ValueError, match="musi być jedną z wartości"):
            validate_generation_params(params, schema)

    def test_unknown_param(self):
        """Test walidacji nieznanego parametru."""
        schema = {"temperature": {"type": "float"}}
        params = {"unknown_param": 0.5}

        with pytest.raises(ValueError, match="Nieznany parametr"):
            validate_generation_params(params, schema)

    def test_multiple_valid_params(self):
        """Test walidacji wielu poprawnych parametrów."""
        schema = {
            "temperature": {"type": "float", "min": 0.0, "max": 1.0},
            "max_tokens": {"type": "int", "min": 1, "max": 4096},
            "stream": {"type": "bool"},
        }
        params = {"temperature": 0.7, "max_tokens": 2048, "stream": True}

        result = validate_generation_params(params, schema)

        assert result == {"temperature": 0.7, "max_tokens": 2048, "stream": True}

    def test_string_to_float_conversion(self):
        """Test konwersji string na float."""
        schema = {"temperature": {"type": "float", "min": 0.0, "max": 1.0}}
        params = {"temperature": "0.7"}

        result = validate_generation_params(params, schema)

        assert result == {"temperature": 0.7}

    def test_invalid_float_string(self):
        """Test konwersji niepoprawnego stringa na float."""
        schema = {"temperature": {"type": "float"}}
        params = {"temperature": "invalid"}

        with pytest.raises(ValueError, match="musi być liczbą zmiennoprzecinkową"):
            validate_generation_params(params, schema)
