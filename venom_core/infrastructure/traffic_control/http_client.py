"""HTTP Client wrapper z integracją traffic control."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from venom_core.utils.logger import get_logger

from .controller import TrafficController, get_traffic_controller
from .retry_policy import RetryPolicy, is_retriable_http_error

logger = get_logger(__name__)


class TrafficControlledHttpClient:
    """
    HTTP Client z integracją traffic control.

    Zapewnia:
    1. Rate limiting per provider
    2. Circuit breaker dla ochrony przed degradacją
    3. Retry policy z exponential backoff
    4. Telemetria requestów

    **Ważne zasady użycia:**
    - Metody synchroniczne (get, post, etc.) mogą być używane bez context managera,
      ale zalecane jest użycie: `with TrafficControlledHttpClient(...) as client:`
    - Metody async (aget, apost, etc.) MUSZĄ być używane z async context manager:
      `async with TrafficControlledHttpClient(...) as client:`
    - Resource cleanup dla async clienta działa TYLKO przez context manager
      (__del__ nie może bezpiecznie zamknąć async zasobów)
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
        base_url_value = base_url or ""
        self._client = httpx.Client(
            base_url=base_url_value,
            timeout=timeout,
            follow_redirects=True,
        )

        # httpx async client
        self._async_client = httpx.AsyncClient(
            base_url=base_url_value,
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
            self.provider,
            method=method,
        )
        if not allowed:
            self._raise_if_blocked(reason, wait_seconds)

        # Get retry policy for the same scope as rate limiting (provider + method)
        scope = self.traffic_controller._build_outbound_scope(self.provider, method)
        policy = self.traffic_controller._get_or_create_outbound_policy(scope)

        # Execute with retry
        def _execute():
            response = self._client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

        retry_policy = policy.retry_policy
        if retry_policy is None:
            raise RuntimeError(
                f"Retry policy not configured for provider scope: {scope}"
            )

        result, response, error = retry_policy.execute_with_retry(
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

        if response:
            self.traffic_controller.record_outbound_response(
                self.provider, response.status_code, method=method
            )
            return response
        if isinstance(error, Exception):
            self._record_outbound_error_and_raise(error, method=method)
        self._record_outbound_error_and_raise(
            RuntimeError(
                f"Request failed without response for {self.provider} {method} {url}"
            ),
            method=method,
        )
        raise RuntimeError("unreachable")

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
            self.provider,
            method=method,
        )
        if not allowed:
            self._raise_if_blocked(reason, wait_seconds)

        # Get retry policy for the same scope as rate limiting (provider + method)
        scope = self.traffic_controller._build_outbound_scope(self.provider, method)
        policy = self.traffic_controller._get_or_create_outbound_policy(scope)

        # Execute with retry (note: async version needs manual implementation)
        last_exception: Exception | None = None
        retry_policy = policy.retry_policy
        if retry_policy is None:
            raise RuntimeError(
                f"Retry policy not configured for provider scope: {scope}"
            )

        for attempt in range(retry_policy.max_attempts):
            try:
                response = await self._async_client.request(method, url, **kwargs)
                response.raise_for_status()
                self.traffic_controller.record_outbound_response(
                    self.provider, response.status_code, method=method
                )
                return response
            except Exception as exc:
                last_exception = exc
                if not is_retriable_http_error(exc):
                    self._record_outbound_error_and_raise(exc, method=method)
                if attempt >= retry_policy.max_attempts - 1:
                    break
                await self._sleep_before_retry(
                    attempt=attempt,
                    policy=retry_policy,
                    method=method,
                    url=url,
                    error=exc,
                )

        if last_exception is None:
            raise RuntimeError("Retry exhausted without captured exception")
        self._record_outbound_error_and_raise(last_exception, method=method)
        raise RuntimeError("unreachable")

    def _raise_if_blocked(
        self, reason: Optional[str], wait_seconds: Optional[float]
    ) -> None:
        if reason == "circuit_breaker_open":
            raise RuntimeError(f"Circuit breaker open for provider '{self.provider}'")
        if reason == "degraded_mode_active":
            raise RuntimeError("Traffic control is in degraded mode")
        if reason == "global_request_cap_exceeded":
            raise RuntimeError("Global outbound request cap exceeded")
        if reason == "rate_limit_exceeded":
            wait = 0.0 if wait_seconds is None else wait_seconds
            raise RuntimeError(
                f"Rate limit exceeded for provider '{self.provider}'. "
                f"Retry after {wait:.1f} seconds"
            )
        raise RuntimeError("Outbound request blocked by traffic control")

    @staticmethod
    def _extract_status_code(error: Exception) -> Optional[int]:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code if isinstance(status_code, int) else None

    def _record_outbound_error_and_raise(
        self, error: Exception, *, method: Optional[str]
    ) -> None:
        status_code = self._extract_status_code(error)
        self.traffic_controller.record_outbound_response(
            self.provider, status_code, error, method=method
        )
        raise error

    async def _sleep_before_retry(
        self,
        *,
        attempt: int,
        policy: RetryPolicy,
        method: str,
        url: str,
        error: Exception,
    ) -> None:
        import asyncio

        delay = policy.calculate_delay(attempt)
        if self.traffic_controller.config.enable_logging:
            logger.warning(
                "Retry %s for %s %s %s: %s. Waiting %.1fs",
                attempt + 1,
                self.provider,
                method,
                url,
                error,
                delay,
            )
        await asyncio.sleep(delay)

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

        WAŻNE: Ta metoda zamyka TYLKO synchroniczny _client. Async _async_client
        NIE jest zamykany, ponieważ async cleanup w __del__ jest niebezpieczny
        (brak running event loop podczas garbage collection).

        **Zalecenie**: Używaj async metod WYŁĄCZNIE z async context manager:
        ```python
        async with TrafficControlledHttpClient(provider="github") as client:
            response = await client.aget("https://api.github.com/users/mpieniak01")
        ```

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
