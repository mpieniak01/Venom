"""HTTP Client wrapper z integracją traffic control."""

from __future__ import annotations

import inspect
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

import httpx

from venom_core.infrastructure.traffic_control.config import TrafficControlConfig
from venom_core.infrastructure.traffic_control.controller import (
    TrafficController,
    get_traffic_controller,
)
from venom_core.infrastructure.traffic_control.retry_policy import (
    RetryPolicy,
    is_retriable_http_error,
)
from venom_core.utils.logger import get_logger

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
        timeout: float | None = 30.0,
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
        self.traffic_controller = (
            traffic_controller or self._resolve_traffic_controller()
        )

        # httpx client (sync)
        base_url_value = base_url or ""
        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
        }
        if base_url_value:
            client_kwargs["base_url"] = base_url_value
        self._client = httpx.Client(**client_kwargs)

        # httpx async client
        async_client_kwargs: dict[str, Any] = {
            "timeout": timeout,
        }
        if base_url_value:
            async_client_kwargs["base_url"] = base_url_value
        self._async_client = httpx.AsyncClient(**async_client_kwargs)

    @staticmethod
    def _resolve_traffic_controller() -> TrafficController:
        """
        Zwraca domyślny kontroler ruchu.

        W testach (`PYTEST_CURRENT_TEST`) używa świeżej konfiguracji per-client,
        aby uniknąć przeciekania stanu limiterów/circuit-breakera pomiędzy testami.
        """
        if os.getenv("PYTEST_CURRENT_TEST"):
            return TrafficController(TrafficControlConfig())
        return get_traffic_controller()

    def request(
        self,
        method: str,
        url: str,
        *,
        raise_for_status: bool = True,
        disable_retry: bool = False,
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
        retry_policy = self._resolve_retry_policy(method)
        execute_request = self._build_sync_executor(
            method=method,
            url=url,
            raise_for_status=raise_for_status,
            kwargs=kwargs,
        )

        if disable_retry:
            return self._execute_sync_without_retry(
                execute_request=execute_request,
                method=method,
            )

        _, response, error = retry_policy.execute_with_retry(
            execute_request,
            is_retriable=is_retriable_http_error,
            on_retry=self._build_retry_logger(method=method, url=url),
        )

        if response is not None:
            return self._record_outbound_success(response=response, method=method)
        self._raise_request_failure(error=error, method=method, url=url)
        raise RuntimeError("unreachable")

    async def arequest(
        self,
        method: str,
        url: str,
        *,
        raise_for_status: bool = True,
        disable_retry: bool = False,
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
        retry_policy = self._resolve_retry_policy(method)
        last_exception: Exception | None = None
        max_attempts = 1 if disable_retry else retry_policy.max_attempts
        for attempt in range(max_attempts):
            try:
                response = await self._execute_async_request_once(
                    method=method,
                    url=url,
                    raise_for_status=raise_for_status,
                    kwargs=kwargs,
                )
                return self._record_outbound_success(response=response, method=method)
            except Exception as exc:
                last_exception = exc
                if not is_retriable_http_error(exc):
                    self._record_outbound_error_and_raise(exc, method=method)
                if attempt >= max_attempts - 1:
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

    @asynccontextmanager
    async def astream(
        self,
        method: str,
        url: str,
        *,
        raise_for_status: bool = True,
        disable_retry: bool = False,
        **kwargs: Any,
    ) -> AsyncIterator[httpx.Response]:
        """
        Wykonuje streaming HTTP request z traffic control (async).

        Użycie:
        `async with client.astream("POST", url, json=payload) as response: ...`
        """
        retry_policy = self._resolve_retry_policy(method)
        last_exception: Exception | None = None
        max_attempts = 1 if disable_retry else retry_policy.max_attempts
        for attempt in range(max_attempts):
            try:
                async with self._stream_once(
                    method=method,
                    url=url,
                    raise_for_status=raise_for_status,
                    kwargs=kwargs,
                ) as response:
                    yield response
                return
            except Exception as exc:
                last_exception = exc
                if not is_retriable_http_error(exc):
                    self._record_outbound_error_and_raise(exc, method=method)
                if attempt >= max_attempts - 1:
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
        if isinstance(
            error,
            (httpx.HTTPError, RuntimeError, TypeError, ValueError, AttributeError),
        ):
            raise error
        raise RuntimeError(
            f"Outbound request failed for provider '{self.provider}'"
        ) from error

    def _check_outbound_allowed(self, method: str) -> None:
        allowed, reason, wait_seconds = self.traffic_controller.check_outbound_request(
            self.provider,
            method=method,
        )
        if not allowed:
            self._raise_if_blocked(reason, wait_seconds)

    def _resolve_retry_policy(self, method: str) -> RetryPolicy:
        self._check_outbound_allowed(method)
        scope = self.traffic_controller._build_outbound_scope(self.provider, method)
        policy = self.traffic_controller._get_or_create_outbound_policy(scope)
        retry_policy = policy.retry_policy
        if retry_policy is None:
            raise RuntimeError(
                f"Retry policy not configured for provider scope: {scope}"
            )
        return retry_policy

    def _record_outbound_success(
        self, *, response: httpx.Response, method: str
    ) -> httpx.Response:
        response_status = getattr(response, "status_code", None)
        status_code = response_status if isinstance(response_status, int) else None
        self.traffic_controller.record_outbound_response(
            self.provider, status_code, method=method
        )
        return response

    def _build_sync_executor(
        self,
        *,
        method: str,
        url: str,
        raise_for_status: bool,
        kwargs: dict[str, Any],
    ):
        def _execute() -> httpx.Response:
            response = self._client.request(method, url, **kwargs)
            status_code = getattr(response, "status_code", None)
            if not isinstance(status_code, int):
                raise TypeError(
                    "Invalid response object received from httpx client: "
                    f"{type(response)}"
                )
            if raise_for_status:
                response.raise_for_status()
            return response

        return _execute

    def _build_retry_logger(self, *, method: str, url: str):
        def _on_retry(attempt: int, exc: Exception, delay: float) -> None:
            if not self.traffic_controller.config.enable_logging:
                return
            logger.warning(
                "Retry %s for %s %s %s: %s. Waiting %.1fs",
                attempt + 1,
                self.provider,
                method,
                url,
                exc,
                delay,
            )

        return _on_retry

    def _execute_sync_without_retry(
        self, *, execute_request, method: str
    ) -> httpx.Response:
        try:
            response = execute_request()
            return self._record_outbound_success(response=response, method=method)
        except Exception as exc:
            self._record_outbound_error_and_raise(exc, method=method)
            raise RuntimeError("unreachable")

    def _raise_request_failure(
        self, *, error: Exception | None, method: str, url: str
    ) -> None:
        if isinstance(error, Exception):
            self._record_outbound_error_and_raise(error, method=method)
        self._record_outbound_error_and_raise(
            RuntimeError(
                f"Request failed without response for {self.provider} {method} {url}"
            ),
            method=method,
        )

    async def _execute_async_request_once(
        self,
        *,
        method: str,
        url: str,
        raise_for_status: bool,
        kwargs: dict[str, Any],
    ) -> httpx.Response:
        request_handler = getattr(self._async_client, "request", None)
        if callable(request_handler):
            request_result = request_handler(method, url, **kwargs)
        else:
            method_handler = getattr(self._async_client, method.lower(), None)
            if not callable(method_handler):
                raise AttributeError(
                    f"Async client does not support method '{method.lower()}'"
                )
            request_result = method_handler(url, **kwargs)

        response = (
            await request_result
            if inspect.isawaitable(request_result)
            else request_result
        )
        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int):
            raise TypeError(
                "Invalid response object received from httpx async client: "
                f"{type(response)}"
            )
        if raise_for_status:
            raise_result = response.raise_for_status()
            if inspect.isawaitable(raise_result):
                await raise_result
        return response

    @asynccontextmanager
    async def _stream_once(
        self,
        *,
        method: str,
        url: str,
        raise_for_status: bool,
        kwargs: dict[str, Any],
    ) -> AsyncIterator[httpx.Response]:
        async with self._async_client.stream(method, url, **kwargs) as response:
            if raise_for_status:
                raise_result = response.raise_for_status()
                if inspect.isawaitable(raise_result):
                    await raise_result
            self._record_outbound_success(response=response, method=method)
            yield response

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
        close_handler = getattr(self._async_client, "aclose", None)
        if not callable(close_handler):
            return
        close_result = close_handler()
        if inspect.isawaitable(close_result):
            await close_result

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

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        """Context manager exit."""
        self.close()

    async def __aenter__(self):
        """Async context manager."""
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Async context manager exit."""
        await self.aclose()
