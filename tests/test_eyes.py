"""Testy dla modułu eyes - warstwa percepcji wizualnej."""

import base64
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from venom_core.perception.eyes import Eyes


class TestEyes:
    """Testy dla klasy Eyes."""

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch("venom_core.perception.eyes.httpx.get")
    def test_initialization_with_openai(self, mock_get, mock_settings):
        """Test inicjalizacji z OpenAI API key."""
        # Arrange
        mock_settings.OPENAI_API_KEY = "test_key"
        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_get.side_effect = Exception("No local model")

        # Act
        eyes = Eyes()

        # Assert
        assert eyes.use_openai is True
        assert eyes.local_vision_available is False

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch("venom_core.perception.eyes.httpx.get")
    def test_initialization_without_openai(self, mock_get, mock_settings):
        """Test inicjalizacji bez OpenAI API key."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_get.side_effect = Exception("No local model")

        # Act
        eyes = Eyes()

        # Assert
        assert eyes.use_openai is False

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch("venom_core.perception.eyes.httpx.get")
    def test_prepare_image_base64_with_data_uri(self, mock_get, mock_settings):
        """Test przygotowania base64 z data URI."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_get.side_effect = Exception("No local model")
        eyes = Eyes()
        data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA"

        # Act
        result = eyes._prepare_image_base64(data_uri)

        # Assert
        assert result == "iVBORw0KGgoAAAANSUhEUgAAAAUA"

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch("venom_core.perception.eyes.httpx.get")
    def test_prepare_image_base64_with_plain_base64(self, mock_get, mock_settings):
        """Test przygotowania base64 z czystego base64 stringa."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.MIN_BASE64_LENGTH = 500
        mock_get.side_effect = Exception("No local model")
        eyes = Eyes()
        # Długi base64 bez slashów (prawdopodobnie base64)
        long_base64 = "a" * 600

        # Act
        result = eyes._prepare_image_base64(long_base64)

        # Assert
        assert result == long_base64

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch("venom_core.perception.eyes.httpx.get")
    def test_prepare_image_base64_with_file_path(self, mock_get, mock_settings, tmp_path):
        """Test przygotowania base64 z pliku."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.MIN_BASE64_LENGTH = 500
        mock_get.side_effect = Exception("No local model")
        eyes = Eyes()

        # Utwórz testowy plik obrazu
        image_file = tmp_path / "test.png"
        test_data = b"fake image data"
        image_file.write_bytes(test_data)

        # Act
        result = eyes._prepare_image_base64(str(image_file))

        # Assert
        expected = base64.b64encode(test_data).decode("utf-8")
        assert result == expected

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch("venom_core.perception.eyes.httpx.get")
    def test_prepare_image_base64_file_not_found(self, mock_get, mock_settings):
        """Test przygotowania base64 z nieistniejącego pliku."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.MIN_BASE64_LENGTH = 500
        mock_get.side_effect = Exception("No local model")
        eyes = Eyes()

        # Act & Assert
        with pytest.raises(ValueError, match="Plik nie istnieje"):
            eyes._prepare_image_base64("/nonexistent/path/to/image.png")

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch("venom_core.perception.eyes.httpx.get")
    def test_check_local_vision_not_available(self, mock_get, mock_settings):
        """Test sprawdzania lokalnego modelu vision gdy niedostępny."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_get.side_effect = Exception("Connection error")

        # Act
        eyes = Eyes()

        # Assert
        assert eyes.local_vision_available is False
        assert eyes.local_vision_model is None

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch("venom_core.perception.eyes.httpx.get")
    def test_check_local_vision_available(self, mock_get, mock_settings):
        """Test sprawdzania lokalnego modelu vision gdy dostępny."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.VISION_MODEL_NAMES = ["llava"]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "llava:latest"}]
        }
        mock_get.return_value = mock_response

        # Act
        eyes = Eyes()

        # Assert
        assert eyes.local_vision_available is True
        assert eyes.local_vision_model == "llava:latest"
