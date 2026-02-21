"""Circuit breaker pattern - ochrona przed degradacją providerów."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CircuitState(str, Enum):
    """Stan circuit breakera."""

    CLOSED = "closed"  # Normalna praca, requesty przepuszczane
    OPEN = "open"  # Circuit otwarty, requesty blokowane
    HALF_OPEN = "half_open"  # Test recovery, limited requests


@dataclass
class CircuitBreaker:
    """
    Circuit breaker pattern z states: CLOSED -> OPEN -> HALF_OPEN -> CLOSED.

    Algorytm:
    - CLOSED: Przepuszcza requesty, liczy failures
    - failure_count >= failure_threshold -> OPEN
    - OPEN: Blokuje requesty, czeka timeout_seconds
    - Po timeout -> HALF_OPEN
    - HALF_OPEN: Przepuszcza limited requests (half_open_max_calls)
    - success_count >= success_threshold -> CLOSED
    - failure -> OPEN again
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 3

    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failure_count: int = field(default=0, init=False)
    success_count: int = field(default=0, init=False)
    last_failure_time: Optional[float] = field(default=None, init=False)
    half_open_calls: int = field(default=0, init=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def is_request_allowed(self) -> bool:
        """
        Sprawdza czy request może przejść przez circuit.

        Returns:
            True jeśli request może być wykonany, False jeśli circuit otwarty
        """
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Sprawdź czy timeout minął
                if self.last_failure_time is None:
                    return False

                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.timeout_seconds:
                    # Przejdź do HALF_OPEN
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    self.success_count = 0
                    return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                # Limitowana liczba wywołań w half-open
                if self.half_open_calls < self.half_open_max_calls:
                    self.half_open_calls += 1
                    return True
                return False

            return False

    def record_success(self) -> None:
        """Rejestruje udany request."""
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    # Recovery complete -> CLOSED
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.half_open_calls = 0
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.failure_count = 0

    def record_failure(self) -> None:
        """Rejestruje nieudany request."""
        with self._lock:
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # Failure podczas testu recovery -> wróć do OPEN
                self.state = CircuitState.OPEN
                self.failure_count = 0
                self.success_count = 0
                self.half_open_calls = 0
            elif self.state == CircuitState.CLOSED:
                self.failure_count += 1
                if self.failure_count >= self.failure_threshold:
                    # Too many failures -> OPEN
                    self.state = CircuitState.OPEN

    def reset(self) -> None:
        """Resetuje circuit breaker do stanu CLOSED."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.half_open_calls = 0
            self.last_failure_time = None

    def get_state(self) -> CircuitState:
        """Zwraca aktualny stan circuit breakera."""
        with self._lock:
            return self.state

    def get_stats(self) -> dict:
        """
        Zwraca statystyki circuit breakera.

        Returns:
            Dict ze stanem i licznikami
        """
        with self._lock:
            return {
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "half_open_calls": self.half_open_calls,
                "last_failure_time": self.last_failure_time,
            }
