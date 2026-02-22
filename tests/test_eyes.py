"""Testy dla modułu eyes - warstwa percepcji wizualnej.

UWAGA: Te testy są pomijane w środowisku headless (bez X11),
ponieważ venom_core.perception.__init__.py importuje recorder,
który wymaga pynput i dostępu do display.

W środowisku z X11, testy te zostaną uruchomione poprawnie.
"""

import base64
import os
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from tests.helpers.url_fixtures import LOCALHOST_11434_V1

# Sprawdź czy środowisko headless PRZED importem perception
HEADLESS = os.environ.get("DISPLAY", "") == ""
_ORIGINAL_RECORDER_MODULE = sys.modules.get("venom_core.perception.recorder")

if HEADLESS:
    # Mock całego modułu perception.recorder aby uniknąć importu pynput
    import types

    mock_recorder = types.ModuleType("venom_core.perception.recorder")
    mock_recorder.DemonstrationRecorder = Mock
    sys.modules["venom_core.perception.recorder"] = mock_recorder

from venom_core.perception.eyes import Eyes  # noqa: E402  # import after recorder mock

if HEADLESS:
    # Przywrócenie stanu sys.modules po imporcie Eyes, aby nie zanieczyścić innych testów.
    if _ORIGINAL_RECORDER_MODULE is None:
        sys.modules.pop("venom_core.perception.recorder", None)
    else:
        sys.modules["venom_core.perception.recorder"] = _ORIGINAL_RECORDER_MODULE


class TestEyes:
    """Testy dla klasy Eyes."""

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch.object(Eyes, "_check_local_vision", return_value=False)
    def test_initialization_with_openai(self, _mock_check_local, mock_settings):
        """Test inicjalizacji z OpenAI API key."""
        # Arrange
        mock_settings.OPENAI_API_KEY = "test_key"
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5

        # Act
        eyes = Eyes()

        # Assert
        assert eyes.use_openai is True
        assert eyes.local_vision_available is False

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch.object(Eyes, "_check_local_vision", return_value=False)
    def test_initialization_without_openai(self, _mock_check_local, mock_settings):
        """Test inicjalizacji bez OpenAI API key."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5

        # Act
        eyes = Eyes()

        # Assert
        assert eyes.use_openai is False

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch.object(Eyes, "_check_local_vision", return_value=False)
    def test_prepare_image_base64_with_data_uri(self, _mock_check_local, mock_settings):
        """Test przygotowania base64 z data URI."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        eyes = Eyes()
        data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA"

        # Act
        result = eyes._prepare_image_base64(data_uri)

        # Assert
        assert result == "iVBORw0KGgoAAAANSUhEUgAAAAUA"

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch.object(Eyes, "_check_local_vision", return_value=False)
    def test_prepare_image_base64_with_plain_base64(
        self, _mock_check_local, mock_settings
    ):
        """Test przygotowania base64 z czystego base64 stringa."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.MIN_BASE64_LENGTH = 500
        eyes = Eyes()
        # Długi base64 bez slashów (prawdopodobnie base64)
        long_base64 = "a" * 600

        # Act
        result = eyes._prepare_image_base64(long_base64)

        # Assert
        assert result == long_base64

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch.object(Eyes, "_check_local_vision", return_value=False)
    def test_prepare_image_base64_with_file_path(
        self, _mock_check_local, mock_settings, tmp_path
    ):
        """Test przygotowania base64 z pliku."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.MIN_BASE64_LENGTH = 500
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
    @patch.object(Eyes, "_check_local_vision", return_value=False)
    def test_prepare_image_base64_file_not_found(
        self, _mock_check_local, mock_settings
    ):
        """Test przygotowania base64 z nieistniejącego pliku."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.MIN_BASE64_LENGTH = 500
        eyes = Eyes()

        # Act & Assert (combined for exception testing)
        with pytest.raises(ValueError, match="Plik nie istnieje"):
            eyes._prepare_image_base64("/nonexistent/path/to/image.png")

    @patch("venom_core.perception.eyes.SETTINGS")
    @patch.object(Eyes, "_check_local_vision", return_value=False)
    def test_check_local_vision_not_available(self, _mock_check_local, mock_settings):
        """Test sprawdzania lokalnego modelu vision gdy niedostępny."""
        # Arrange
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        # Act
        eyes = Eyes()

        # Assert
        assert eyes.local_vision_available is False
        assert eyes.local_vision_model is None


def test_headless_detection():
    """Weryfikuje, że import i inicjalizacja Eyes działa w trybie headless."""
    if not HEADLESS:
        pytest.skip("Test dotyczy wyłącznie środowiska headless.")

    with (
        patch("venom_core.perception.eyes.SETTINGS") as mock_settings,
        patch.object(Eyes, "_check_local_vision", return_value=False),
    ):
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5

        eyes = Eyes()
        assert eyes.use_openai is False
        assert eyes.local_vision_available is False


@pytest.mark.asyncio
async def test_analyze_with_openai_uses_traffic_client():
    with (
        patch("venom_core.perception.eyes.SETTINGS") as mock_settings,
        patch.object(Eyes, "_check_local_vision", return_value=False),
        patch(
            "venom_core.perception.eyes.TrafficControlledHttpClient"
        ) as mock_client_cls,
    ):
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_GPT4O_MODEL = "gpt-4o"
        mock_settings.VISION_MAX_TOKENS = 256
        mock_settings.OPENAI_API_TIMEOUT = 10.0
        mock_settings.OPENAI_CHAT_COMPLETIONS_ENDPOINT = (
            "https://api.openai.com/v1/chat/completions"
        )
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.LOCAL_VISION_TIMEOUT = 20.0

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "opis"}}]
        }
        mock_client = MagicMock()
        mock_client.apost = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        eyes = Eyes()
        result = await eyes._analyze_with_openai("iVBORw0KGgoAAAANS", "co widzisz?")

    assert result == "opis"
    assert mock_client_cls.call_args.kwargs["provider"] == "openai"
    mock_client.apost.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_with_openai_http_error_is_raised():
    with (
        patch("venom_core.perception.eyes.SETTINGS") as mock_settings,
        patch.object(Eyes, "_check_local_vision", return_value=False),
        patch(
            "venom_core.perception.eyes.TrafficControlledHttpClient"
        ) as mock_client_cls,
    ):
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_GPT4O_MODEL = "gpt-4o"
        mock_settings.VISION_MAX_TOKENS = 256
        mock_settings.OPENAI_API_TIMEOUT = 10.0
        mock_settings.OPENAI_CHAT_COMPLETIONS_ENDPOINT = (
            "https://api.openai.com/v1/chat/completions"
        )
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.LOCAL_VISION_TIMEOUT = 20.0

        mock_client = MagicMock()
        mock_client.apost = AsyncMock(side_effect=httpx.HTTPError("upstream down"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        eyes = Eyes()
        with pytest.raises(httpx.HTTPError):
            await eyes._analyze_with_openai("iVBORw0KGgoAAAANS", "co widzisz?")


@pytest.mark.asyncio
async def test_analyze_with_local_uses_traffic_client_and_http_error_branch():
    with (
        patch("venom_core.perception.eyes.SETTINGS") as mock_settings,
        patch.object(Eyes, "_check_local_vision", return_value=False),
        patch(
            "venom_core.perception.eyes.TrafficControlledHttpClient"
        ) as mock_client_cls,
    ):
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.LLM_LOCAL_ENDPOINT = LOCALHOST_11434_V1
        mock_settings.OLLAMA_CHECK_TIMEOUT = 5
        mock_settings.LOCAL_VISION_TIMEOUT = 20.0

        ok_response = MagicMock()
        ok_response.json.return_value = {"response": "lokalny opis"}
        mock_client = MagicMock()
        mock_client.apost = AsyncMock(
            side_effect=[ok_response, httpx.HTTPError("boom")]
        )
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        eyes = Eyes()
        eyes.local_vision_model = "llava:latest"
        result = await eyes._analyze_with_local("iVBORw0KGgoAAAANS", "prompt")
        assert result == "lokalny opis"

        with pytest.raises(httpx.HTTPError):
            await eyes._analyze_with_local("iVBORw0KGgoAAAANS", "prompt")

    assert mock_client_cls.call_args.kwargs["provider"] == "ollama"
