"""Retry policy z exponential backoff i jitter."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, TypeVar


class RetryResult(str, Enum):
    """Wynik próby retry."""

    SUCCESS = "success"  # Operacja zakończona sukcesem
    FAILED = "failed"  # Operacja nie powiodła się (exhausted retries)
    CIRCUIT_OPEN = "circuit_open"  # Circuit otwarty, nie próbowano


T = TypeVar("T")


@dataclass
class RetryPolicy:
    """
    Retry policy z exponential backoff i jitter.

    Algorytm backoff:
    delay = min(initial_delay * (exponential_base ^ attempt), max_delay)
    actual_delay = delay * (1 + random.uniform(-jitter_factor, jitter_factor))
    """

    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter_factor: float = 0.1

    def calculate_delay(self, attempt: int) -> float:
        """
        Oblicza opóźnienie dla danej próby (z jitter).

        Args:
            attempt: Numer próby (0-indexed: 0, 1, 2, ...)

        Returns:
            Opóźnienie w sekundach
        """
        # Exponential backoff
        delay = self.initial_delay_seconds * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay_seconds)

        # Add jitter
        jitter_range = delay * self.jitter_factor
        jitter = random.uniform(-jitter_range, jitter_range)
        actual_delay = max(0.0, delay + jitter)

        return actual_delay

    def execute_with_retry(
        self,
        func: Callable[[], T],
        is_retriable: Optional[Callable[[Exception], bool]] = None,
        on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    ) -> tuple[RetryResult, Optional[T], Optional[Exception]]:
        """
        Wykonuje funkcję z retry policy.

        Args:
            func: Funkcja do wykonania
            is_retriable: Funkcja sprawdzająca czy błąd jest retriable (default: wszystkie)
            on_retry: Callback wywoływany przed retry (attempt, exception, delay)

        Returns:
            (result: RetryResult, value: Optional[T], error: Optional[Exception])
        """
        last_exception: Optional[Exception] = None

        for attempt in range(self.max_attempts):
            try:
                result = func()
                return RetryResult.SUCCESS, result, None
            except Exception as e:
                last_exception = e

                # Sprawdź czy błąd jest retriable
                if is_retriable and not is_retriable(e):
                    return RetryResult.FAILED, None, e

                # Jeśli to ostatnia próba, nie czekaj
                if attempt >= self.max_attempts - 1:
                    break

                # Oblicz delay i czekaj
                delay = self.calculate_delay(attempt)
                if on_retry:
                    on_retry(attempt, e, delay)
                time.sleep(delay)

        return RetryResult.FAILED, None, last_exception


def is_retriable_http_error(exception: Exception) -> bool:
    """
    Sprawdza czy błąd HTTP jest retriable.

    Retriable: 429, 500, 502, 503, 504, timeout, connection errors
    Non-retriable: 4xx (poza 429), 401, 403
    """
    # Check for common HTTP client exceptions
    error_str = str(exception).lower()
    error_type = type(exception).__name__.lower()

    # Timeout i connection errors są retriable
    if any(
        keyword in error_str or keyword in error_type
        for keyword in ["timeout", "connection", "network", "unreachable"]
    ):
        return True

    # Status code checks (dla httpx/requests exceptions)
    if hasattr(exception, "response") and hasattr(exception.response, "status_code"):
        status_code = exception.response.status_code
        # 429 (rate limit), 5xx (server errors) są retriable
        if status_code == 429 or 500 <= status_code < 600:
            return True
        # 4xx (poza 429) nie są retriable
        if 400 <= status_code < 500:
            return False

    # Dla status code w stringu błędu
    import re

    status_match = re.search(r"\b(429|5\d{2})\b", error_str)
    if status_match:
        return True

    # Non-retriable: authorization/authentication errors
    if any(
        keyword in error_str or keyword in error_type
        for keyword in ["unauthorized", "forbidden", "auth", "401", "403"]
    ):
        return False

    # Default: większość błędów jest retriable
    return True
