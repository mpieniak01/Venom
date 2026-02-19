"""HTTP Client wrapper z integracją traffic control."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from venom_core.utils.logger import get_logger

from .controller import TrafficController, get_traffic_controller
from .retry_policy import is_retriable_http_error

logger = get_logger(__name__)


class TrafficControlledHttpClient:
    """
    HTTP Client z integracją traffic control.

    Zapewnia:
    1. Rate limiting per provider
    2. Circuit breaker dla ochrony przed degradacją
    3. Retry policy z exponential backoff
    4. Telemetria requestów
    """

    def __init__(
        self,
        provider: str,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        traffic_controller: Optional[TrafficController] = None,
    ):
        """
        Inicjalizacja HTTP clienta z traffic control.

        Args:
            provider: Nazwa providera (np. 'openai', 'github', 'reddit')
            base_url: Bazowy URL dla requestów (opcjonalne)
            timeout: Timeout w sekundach (default: 30.0)
            traffic_controller: TrafficController instance (default: singleton)
        """
        self.provider = provider
        self.base_url = base_url
        self.timeout = timeout
        self.traffic_controller = traffic_controller or get_traffic_controller()

        # httpx client (sync)
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            follow_redirects=True,
        )

        # httpx async client
        self._async_client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            follow_redirects=True,
        )

    def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Wykonuje HTTP request z traffic control (sync).

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL requestu
            **kwargs: Dodatkowe argumenty dla httpx.request

        Returns:
            httpx.Response

        Raises:
            httpx.HTTPError: Jeśli request nie powiódł się
            RuntimeError: Jeśli circuit breaker jest otwarty lub rate limit
        """
        # Check traffic control
        allowed, reason, wait_seconds = self.traffic_controller.check_outbound_request(
            self.provider
        )
        if not allowed:
            if reason == "circuit_breaker_open":
                raise RuntimeError(
                    f"Circuit breaker open for provider '{self.provider}'"
                )
            elif reason == "rate_limit_exceeded":
                raise RuntimeError(
                    f"Rate limit exceeded for provider '{self.provider}'. "
                    f"Retry after {wait_seconds:.1f} seconds"
                )

        # Get retry policy
        policy = self.traffic_controller._get_or_create_outbound_policy(self.provider)

        # Execute with retry
        def _execute():
            response = self._client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

        result, response, error = policy.retry_policy.execute_with_retry(
            _execute,
            is_retriable=is_retriable_http_error,
            on_retry=lambda attempt, exc, delay: (
                logger.warning(
                    f"Retry {attempt + 1} for {self.provider} {method} {url}: {exc}. "
                    f"Waiting {delay:.1f}s"
                )
                if self.traffic_controller.config.enable_logging
                else None
            ),
        )

        # Record response
        if response:
            self.traffic_controller.record_outbound_response(
                self.provider, response.status_code
            )
            return response
        else:
            # Failed after retries
            status_code = None
            if hasattr(error, "response") and hasattr(error.response, "status_code"):
                status_code = error.response.status_code
            self.traffic_controller.record_outbound_response(
                self.provider, status_code, error
            )
            raise error

    async def arequest(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Wykonuje HTTP request z traffic control (async).

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL requestu
            **kwargs: Dodatkowe argumenty dla httpx.request

        Returns:
            httpx.Response

        Raises:
            httpx.HTTPError: Jeśli request nie powiódł się
            RuntimeError: Jeśli circuit breaker jest otwarty lub rate limit
        """
        # Check traffic control
        allowed, reason, wait_seconds = self.traffic_controller.check_outbound_request(
            self.provider
        )
        if not allowed:
            if reason == "circuit_breaker_open":
                raise RuntimeError(
                    f"Circuit breaker open for provider '{self.provider}'"
                )
            elif reason == "rate_limit_exceeded":
                raise RuntimeError(
                    f"Rate limit exceeded for provider '{self.provider}'. "
                    f"Retry after {wait_seconds:.1f} seconds"
                )

        # Get retry policy
        policy = self.traffic_controller._get_or_create_outbound_policy(self.provider)

        # Execute with retry (note: async version needs manual implementation)
        last_exception = None
        for attempt in range(policy.retry_policy.max_attempts):
            try:
                response = await self._async_client.request(method, url, **kwargs)
                response.raise_for_status()
                self.traffic_controller.record_outbound_response(
                    self.provider, response.status_code
                )
                return response
            except Exception as e:
                last_exception = e

                # Check if retriable
                if not is_retriable_http_error(e):
                    # Non-retriable error
                    status_code = None
                    if hasattr(e, "response") and hasattr(e.response, "status_code"):
                        status_code = e.response.status_code
                    self.traffic_controller.record_outbound_response(
                        self.provider, status_code, e
                    )
                    raise

                # Last attempt?
                if attempt >= policy.retry_policy.max_attempts - 1:
                    break

                # Calculate delay and wait
                import asyncio

                delay = policy.retry_policy.calculate_delay(attempt)
                if self.traffic_controller.config.enable_logging:
                    logger.warning(
                        f"Retry {attempt + 1} for {self.provider} {method} {url}: {e}. "
                        f"Waiting {delay:.1f}s"
                    )
                await asyncio.sleep(delay)

        # Failed after all retries
        status_code = None
        if hasattr(last_exception, "response") and hasattr(
            last_exception.response, "status_code"
        ):
            status_code = last_exception.response.status_code
        self.traffic_controller.record_outbound_response(
            self.provider, status_code, last_exception
        )
        raise last_exception

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST request."""
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """PUT request."""
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """DELETE request."""
        return self.request("DELETE", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """PATCH request."""
        return self.request("PATCH", url, **kwargs)

    async def aget(self, url: str, **kwargs: Any) -> httpx.Response:
        """Async GET request."""
        return await self.arequest("GET", url, **kwargs)

    async def apost(self, url: str, **kwargs: Any) -> httpx.Response:
        """Async POST request."""
        return await self.arequest("POST", url, **kwargs)

    async def aput(self, url: str, **kwargs: Any) -> httpx.Response:
        """Async PUT request."""
        return await self.arequest("PUT", url, **kwargs)

    async def adelete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Async DELETE request."""
        return await self.arequest("DELETE", url, **kwargs)

    async def apatch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Async PATCH request."""
        return await self.arequest("PATCH", url, **kwargs)

    def close(self) -> None:
        """Zamyka klienta."""
        self._client.close()

    async def aclose(self) -> None:
        """Zamyka async klienta."""
        await self._async_client.aclose()

    def __del__(self) -> None:
        """
        Best-effort cleanup w przypadku gdy klient nie jest użyty jako context manager.

        Uwaga: Wyjątki podczas cleanup są pomijane aby uniknąć problemów
        podczas garbage collection.
        """
        try:
            # Synchronous cleanup only - async cleanup in __del__ is not safe
            if hasattr(self, "_client") and self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
        except Exception:
            # If even basic cleanup fails, silently ignore
            pass

    def __enter__(self):
        """Context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    async def __aenter__(self):
        """Async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()
