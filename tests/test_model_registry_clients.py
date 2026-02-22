"""Testy dla model_registry_clients - HuggingFaceClient (PR-132B coverage improvement)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from venom_core.core.model_registry_clients import HuggingFaceClient


class TestHuggingFaceClientGetModelInfo:
    """Testy dla HuggingFaceClient.get_model_info() method (PR-132B)."""

    @pytest.mark.asyncio
    async def test_get_model_info_success_with_token(self):
        """Test pobierania info o modelu z tokenem autoryzacyjnym."""
        client = HuggingFaceClient(token="test_token")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "microsoft/phi-3-mini",
            "downloads": 100000,
            "likes": 500,
            "tags": ["text-generation"],
            "author": "microsoft",
        }
        mock_response.raise_for_status = MagicMock()

        with patch(
            "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.aget = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await client.get_model_info("microsoft/phi-3-mini")

            assert result is not None
            assert result["id"] == "microsoft/phi-3-mini"
            assert result["downloads"] == 100000

            # Sprawdź że użyto tokena
            call_kwargs = mock_client.aget.call_args[1]
            assert "headers" in call_kwargs
            # Token powinien być w headerach (jako ******)

    @pytest.mark.asyncio
    async def test_get_model_info_404_not_found(self):
        """Test gdy model nie istnieje (404)."""
        client = HuggingFaceClient()

        with patch(
            "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
        ) as mock_client_class:
            mock_client = MagicMock()

            # Symuluj 404
            import httpx

            mock_response = MagicMock()
            mock_response.status_code = 404
            error = httpx.HTTPStatusError(
                "Not found", request=MagicMock(), response=mock_response
            )
            mock_client.aget = AsyncMock(side_effect=error)
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await client.get_model_info("nonexistent/model")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_model_info_http_error_non_404(self):
        """Test błędu HTTP innego niż 404."""
        client = HuggingFaceClient()

        with patch(
            "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
        ) as mock_client_class:
            mock_client = MagicMock()

            # Symuluj 500
            import httpx

            mock_response = MagicMock()
            mock_response.status_code = 500
            error = httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_response
            )
            mock_client.aget = AsyncMock(side_effect=error)
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await client.get_model_info("some/model")

            # Powinno zwrócić None z logiem warning
            assert result is None

    @pytest.mark.asyncio
    async def test_get_model_info_generic_exception(self):
        """Test obsługi generycznego błędu."""
        client = HuggingFaceClient()

        with patch(
            "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.aget = AsyncMock(side_effect=Exception("Network error"))
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await client.get_model_info("some/model")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_model_info_without_token(self):
        """Test pobierania info bez tokena."""
        client = HuggingFaceClient(token=None)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "gpt2",
            "downloads": 1000000,
        }
        mock_response.raise_for_status = MagicMock()

        with patch(
            "venom_core.core.model_registry_clients.TrafficControlledHttpClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.aget = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await client.get_model_info("gpt2")

            assert result is not None
            assert result["id"] == "gpt2"

            # Sprawdź że NIE użyto tokena (brak headerów auth)
            call_kwargs = mock_client.aget.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert (
                "Authorization" not in headers or headers.get("Authorization") is None
            )
