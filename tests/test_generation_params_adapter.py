"""Testy dla adaptera parametrów generacji."""

import pytest

from venom_core.core.generation_params_adapter import GenerationParamsAdapter


class TestGenerationParamsAdapter:
    """Testy dla GenerationParamsAdapter."""

    def test_adapt_params_empty(self):
        """Test adaptacji pustych parametrów."""
        result = GenerationParamsAdapter.adapt_params(None, "vllm")
        assert result == {}

        result = GenerationParamsAdapter.adapt_params({}, "vllm")
        assert result == {}

    def test_adapt_params_vllm(self):
        """Test adaptacji parametrów dla vLLM."""
        params = {
            "temperature": 0.7,
            "max_tokens": 2048,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
        }

        result = GenerationParamsAdapter.adapt_params(params, "vllm")

        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 2048
        assert result["top_p"] == 0.9
        assert result["top_k"] == 40
        assert result["repetition_penalty"] == 1.1  # Zmapowano na repetition_penalty
        assert "repeat_penalty" not in result

    def test_adapt_params_ollama(self):
        """Test adaptacji parametrów dla Ollama."""
        params = {
            "temperature": 0.5,
            "max_tokens": 1024,
            "top_p": 0.95,
            "top_k": 50,
            "repeat_penalty": 1.2,
        }

        result = GenerationParamsAdapter.adapt_params(params, "ollama")

        assert result["temperature"] == 0.5
        assert result["num_predict"] == 1024  # Zmapowano na num_predict
        assert result["top_p"] == 0.95
        assert result["top_k"] == 50
        assert result["repeat_penalty"] == 1.2
        assert "max_tokens" not in result

    def test_adapt_params_openai(self):
        """Test adaptacji parametrów dla OpenAI."""
        params = {
            "temperature": 0.8,
            "max_tokens": 512,
            "top_p": 0.9,
            "top_k": 40,  # OpenAI nie wspiera
            "repeat_penalty": 1.1,  # OpenAI nie wspiera
        }

        result = GenerationParamsAdapter.adapt_params(params, "openai")

        assert result["temperature"] == 0.8
        assert result["max_tokens"] == 512
        assert result["top_p"] == 0.9
        # Parametry nieobsługiwane powinny być pominięte
        assert "top_k" not in result
        assert "repeat_penalty" not in result

    def test_adapt_params_local_defaults_to_vllm(self):
        """Test że provider 'local' domyślnie używa mapowania vLLM."""
        params = {"max_tokens": 1000, "repeat_penalty": 1.1}

        result = GenerationParamsAdapter.adapt_params(params, "local")

        assert result["max_tokens"] == 1000
        assert result["repetition_penalty"] == 1.1  # vLLM mapping

    def test_detect_provider_ollama_variations(self):
        """Test wykrywania providera Ollama z różnych wartości."""
        assert GenerationParamsAdapter._detect_provider("ollama") == "ollama"
        assert GenerationParamsAdapter._detect_provider("Ollama") == "ollama"
        assert GenerationParamsAdapter._detect_provider("OLLAMA") == "ollama"

    def test_detect_provider_vllm_variations(self):
        """Test wykrywania providera vLLM z różnych wartości."""
        assert GenerationParamsAdapter._detect_provider("vllm") == "vllm"
        assert GenerationParamsAdapter._detect_provider("vLLM") == "vllm"
        assert GenerationParamsAdapter._detect_provider("VLLM") == "vllm"

    def test_detect_provider_openai_variations(self):
        """Test wykrywania providera OpenAI z różnych wartości."""
        assert GenerationParamsAdapter._detect_provider("openai") == "openai"
        assert GenerationParamsAdapter._detect_provider("OpenAI") == "openai"
        assert GenerationParamsAdapter._detect_provider("azure-openai") == "openai"

    def test_merge_with_defaults_no_user_params(self):
        """Test łączenia z domyślnymi gdy brak parametrów użytkownika."""
        defaults = {"temperature": 0.7, "max_tokens": 2048}
        result = GenerationParamsAdapter.merge_with_defaults(None, defaults)
        assert result == defaults

    def test_merge_with_defaults_user_overrides(self):
        """Test że parametry użytkownika nadpisują domyślne."""
        defaults = {"temperature": 0.7, "max_tokens": 2048, "top_p": 0.9}
        user_params = {"temperature": 0.3, "top_k": 50}

        result = GenerationParamsAdapter.merge_with_defaults(user_params, defaults)

        assert result["temperature"] == 0.3  # Nadpisane przez użytkownika
        assert result["max_tokens"] == 2048  # Z domyślnych
        assert result["top_p"] == 0.9  # Z domyślnych
        assert result["top_k"] == 50  # Nowy od użytkownika

    def test_merge_with_defaults_no_defaults(self):
        """Test łączenia gdy brak domyślnych parametrów."""
        user_params = {"temperature": 0.5}
        result = GenerationParamsAdapter.merge_with_defaults(user_params, None)
        assert result == user_params

    def test_adapt_params_partial_parameters(self):
        """Test adaptacji tylko części parametrów."""
        params = {"temperature": 0.5}
        result = GenerationParamsAdapter.adapt_params(params, "vllm")
        assert result == {"temperature": 0.5}

    def test_adapt_params_unknown_provider(self):
        """Test adaptacji dla nieznanego providera."""
        params = {"temperature": 0.7, "max_tokens": 1000}
        result = GenerationParamsAdapter.adapt_params(params, "unknown-provider")
        # Powinno zwrócić parametry bez mapowania
        assert "temperature" in result
        assert "max_tokens" in result
