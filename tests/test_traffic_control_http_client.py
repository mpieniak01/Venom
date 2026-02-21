"""Comprehensive tests for TrafficControlledHttpClient - HTTP client wrapper."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from venom_core.infrastructure.traffic_control import (
    TrafficControlConfig,
    TrafficControlledHttpClient,
    TrafficController,
)


@pytest.fixture
def mock_httpx():
    """Fixture to mock both httpx.Client and httpx.AsyncClient."""
    with patch("httpx.Client") as mock_sync, patch("httpx.AsyncClient") as mock_async:
        yield mock_sync, mock_async


class TestTrafficControlledHttpClientSync:
    """Tests for synchronous HTTP client methods."""

    def test_http_client_initialization(self, mock_httpx):
        """Test HTTP client initialization with all parameters."""
        client = TrafficControlledHttpClient(
            provider="test_provider",
            base_url="https://api.example.com",
            timeout=60.0,
        )

        assert client.provider == "test_provider"
        assert client.base_url == "https://api.example.com"
        assert client.timeout == 60.0
        assert client.traffic_controller is not None

    def test_http_client_successful_get_request(self, mock_httpx):
        """Test successful GET request."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response
        mock_sync.return_value = mock_client

        config = TrafficControlConfig()
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        response = client.get("/test")

        assert response.status_code == 200
        mock_client.request.assert_called_once()

    def test_http_client_successful_post_request(self, mock_httpx):
        """Test successful POST request."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response
        mock_sync.return_value = mock_client

        config = TrafficControlConfig()
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        response = client.post("/test", json={"key": "value"})

        assert response.status_code == 201

    def test_http_client_put_request(self, mock_httpx):
        """Test PUT request."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response
        mock_sync.return_value = mock_client

        client = TrafficControlledHttpClient("test")
        response = client.put("/test", json={"key": "value"})

        assert response.status_code == 200

    def test_http_client_delete_request(self, mock_httpx):
        """Test DELETE request."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response
        mock_sync.return_value = mock_client

        client = TrafficControlledHttpClient("test")
        response = client.delete("/test/123")

        assert response.status_code == 204

    def test_http_client_patch_request(self, mock_httpx):
        """Test PATCH request."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response
        mock_sync.return_value = mock_client

        client = TrafficControlledHttpClient("test")
        response = client.patch("/test/123", json={"status": "updated"})

        assert response.status_code == 200

    def test_http_client_rate_limit_exception(self, mock_httpx):
        """Test that rate limit raises RuntimeError."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_sync.return_value = mock_client

        config = TrafficControlConfig()
        config.global_outbound.rate_limit.capacity = 1
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        # First request should succeed
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response
        client.get("/test")

        # Second request should be rate limited
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            client.get("/test")

    def test_http_client_circuit_breaker_exception(self, mock_httpx):
        """Test that circuit breaker raises RuntimeError."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_sync.return_value = mock_client

        config = TrafficControlConfig()
        config.global_outbound.circuit_breaker.failure_threshold = 2
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        # Simulate failures
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Service unavailable", request=MagicMock(), response=mock_response
            )
        )
        mock_client.request.return_value = mock_response

        # First two requests fail, opening circuit
        for _ in range(2):
            try:
                client.get("/test")
            except httpx.HTTPStatusError:
                pass

        # Next request should be blocked by circuit breaker
        with pytest.raises(RuntimeError, match="Circuit breaker open"):
            client.get("/test")

    def test_http_client_retry_on_transient_error(self, mock_httpx):
        """Test that client retries on transient errors."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_sync.return_value = mock_client

        # First attempt fails, second succeeds
        attempts = [0]

        def side_effect(*args, **kwargs):
            attempts[0] += 1
            if attempts[0] == 1:
                response = MagicMock()
                response.status_code = 503
                response.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "Service unavailable", request=MagicMock(), response=response
                    )
                )
                return response
            else:
                response = MagicMock()
                response.status_code = 200
                response.raise_for_status = MagicMock()
                return response

        mock_client.request.side_effect = side_effect

        config = TrafficControlConfig()
        config.global_outbound.retry_policy.initial_delay_seconds = 0.01
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        response = client.get("/test")

        assert response.status_code == 200
        assert attempts[0] == 2  # Failed once, then succeeded

    def test_http_client_non_retriable_error(self, mock_httpx):
        """Test that non-retriable errors are not retried."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_sync.return_value = mock_client

        # 401 is non-retriable
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized", request=MagicMock(), response=mock_response
            )
        )
        mock_client.request.return_value = mock_response

        client = TrafficControlledHttpClient("test")

        with pytest.raises(httpx.HTTPStatusError):
            client.get("/test")

        # Should only be called once (no retry)
        assert mock_client.request.call_count == 1

    def test_http_client_context_manager(self, mock_httpx):
        """Test that client works as context manager."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_sync.return_value = mock_client

        with TrafficControlledHttpClient("test") as client:
            assert client is not None

        mock_client.close.assert_called_once()

    def test_http_client_close(self, mock_httpx):
        """Test explicit close."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_sync.return_value = mock_client

        client = TrafficControlledHttpClient("test")
        client.close()

        mock_client.close.assert_called_once()


class TestTrafficControlledHttpClientAsync:
    """Tests for asynchronous HTTP client methods."""

    @pytest.mark.asyncio
    async def test_http_client_async_get_request(self, mock_httpx):
        """Test successful async GET request."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_async.return_value = mock_client

        config = TrafficControlConfig()
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        response = await client.aget("/test")

        assert response.status_code == 200
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_client_async_post_request(self, mock_httpx):
        """Test successful async POST request."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.raise_for_status = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_async.return_value = mock_client

        client = TrafficControlledHttpClient("test")
        response = await client.apost("/test", json={"key": "value"})

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_http_client_async_put_request(self, mock_httpx):
        """Test async PUT request."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_async.return_value = mock_client

        client = TrafficControlledHttpClient("test")
        response = await client.aput("/test", json={"key": "value"})

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_http_client_async_delete_request(self, mock_httpx):
        """Test async DELETE request."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_async.return_value = mock_client

        client = TrafficControlledHttpClient("test")
        response = await client.adelete("/test/123")

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_http_client_async_patch_request(self, mock_httpx):
        """Test async PATCH request."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_async.return_value = mock_client

        client = TrafficControlledHttpClient("test")
        response = await client.apatch("/test/123", json={"status": "updated"})

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_http_client_async_rate_limit_exception(self, mock_httpx):
        """Test that async rate limit raises RuntimeError."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_async.return_value = mock_client

        config = TrafficControlConfig()
        config.global_outbound.rate_limit.capacity = 1
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        # First request should succeed
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        await client.aget("/test")

        # Second request should be rate limited
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await client.aget("/test")

    @pytest.mark.asyncio
    async def test_http_client_async_circuit_breaker_exception(self, mock_httpx):
        """Test that async circuit breaker raises RuntimeError."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_async.return_value = mock_client

        config = TrafficControlConfig()
        config.global_outbound.circuit_breaker.failure_threshold = 2
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        # Simulate failures
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Service unavailable", request=MagicMock(), response=mock_response
            )
        )
        mock_client.request = AsyncMock(return_value=mock_response)

        # First two requests fail, opening circuit
        for _ in range(2):
            try:
                await client.aget("/test")
            except httpx.HTTPStatusError:
                pass

        # Next request should be blocked by circuit breaker
        with pytest.raises(RuntimeError, match="Circuit breaker open"):
            await client.aget("/test")

    @pytest.mark.asyncio
    async def test_http_client_async_retry_on_transient_error(self, mock_httpx):
        """Test that async client retries on transient errors."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_async.return_value = mock_client

        # First attempt fails, second succeeds
        attempts = [0]

        async def side_effect(*args, **kwargs):
            attempts[0] += 1
            if attempts[0] == 1:
                response = MagicMock()
                response.status_code = 503
                response.raise_for_status = MagicMock(
                    side_effect=httpx.HTTPStatusError(
                        "Service unavailable", request=MagicMock(), response=response
                    )
                )
                return response
            else:
                response = MagicMock()
                response.status_code = 200
                response.raise_for_status = MagicMock()
                return response

        mock_client.request = AsyncMock(side_effect=side_effect)

        config = TrafficControlConfig()
        config.global_outbound.retry_policy.initial_delay_seconds = 0.01
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        response = await client.aget("/test")

        assert response.status_code == 200
        assert attempts[0] == 2  # Failed once, then succeeded

    @pytest.mark.asyncio
    async def test_http_client_async_non_retriable_error(self, mock_httpx):
        """Test that async non-retriable errors are not retried."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_async.return_value = mock_client

        # 401 is non-retriable
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized", request=MagicMock(), response=mock_response
            )
        )
        mock_client.request = AsyncMock(return_value=mock_response)

        client = TrafficControlledHttpClient("test")

        with pytest.raises(httpx.HTTPStatusError):
            await client.aget("/test")

        # Should only be called once (no retry)
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_http_client_async_context_manager(self, mock_httpx):
        """Test that async client works as context manager."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_async.return_value = mock_client

        async with TrafficControlledHttpClient("test") as client:
            assert client is not None

        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_client_async_close(self, mock_httpx):
        """Test explicit async close."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_async.return_value = mock_client

        client = TrafficControlledHttpClient("test")
        await client.aclose()

        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_client_async_retry_exhaustion(self, mock_httpx):
        """Test async client when all retry attempts are exhausted."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_async.return_value = mock_client

        # All attempts fail
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Service unavailable", request=MagicMock(), response=mock_response
            )
        )
        mock_client.request = AsyncMock(return_value=mock_response)

        config = TrafficControlConfig()
        config.global_outbound.retry_policy.max_attempts = 3
        config.global_outbound.retry_policy.initial_delay_seconds = 0.01
        controller = TrafficController(config)
        client = TrafficControlledHttpClient("test", traffic_controller=controller)

        with pytest.raises(httpx.HTTPStatusError):
            await client.aget("/test")

        # Should be called 3 times (initial + 2 retries)
        assert mock_client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_http_client_async_error_without_response(self, mock_httpx):
        """Test async client with error that has no response attribute."""
        _, mock_async = mock_httpx
        mock_client = AsyncMock()
        mock_async.return_value = mock_client

        # Error without response attribute
        mock_client.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection failed")
        )

        client = TrafficControlledHttpClient("test")

        with pytest.raises(httpx.ConnectError):
            await client.aget("/test")


class TestTrafficControlledHttpClientIntegration:
    """Integration tests for HTTP client with traffic control."""

    def test_http_client_records_metrics(self, mock_httpx):
        """Test that HTTP client records metrics."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response
        mock_sync.return_value = mock_client

        config = TrafficControlConfig()
        controller = TrafficController(config)
        client = TrafficControlledHttpClient(
            "test_provider", traffic_controller=controller
        )

        # Make successful requests
        client.get("/test1")
        client.post("/test2")

        # Check metrics
        metrics = controller.get_metrics("test_provider")
        assert metrics["metrics"]["total_requests"] == 2
        assert metrics["metrics"]["total_2xx"] == 2

    def test_http_client_respects_provider_limits(self, mock_httpx):
        """Test that HTTP client respects provider-specific limits."""
        mock_sync, _ = mock_httpx
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response
        mock_sync.return_value = mock_client

        config = TrafficControlConfig.from_env()
        controller = TrafficController(config)

        # GitHub has limit of 60/min
        github_client = TrafficControlledHttpClient(
            "github", traffic_controller=controller
        )

        # Make 60 requests (should all succeed)
        for i in range(60):
            github_client.get(f"/test{i}")

        # 61st request should be rate limited
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            github_client.get("/test61")
