"""Token bucket rate limiter - thread-safe implementation."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenBucket:
    """
    Token bucket rate limiter z thread-safe refill.

    Algorytm:
    - Bucket ma capacity tokenów
    - Tokeny są uzupełniane w refill_rate per sekundę
    - acquire(n) pobiera n tokenów jeśli dostępne, inaczej False
    - Thread-safe dla concurrent requestów
    """

    capacity: int
    refill_rate: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Inicjalizacja bucketa - pełna pojemność na start."""
        self.tokens = float(self.capacity)
        self.last_refill = time.time()

    def _refill(self) -> None:
        """
        Uzupełnia tokeny na podstawie czasu od ostatniego refill.

        Wzór: tokens += (current_time - last_refill) * refill_rate
        """
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def acquire(self, tokens: int = 1) -> bool:
        """
        Próbuje pobrać `tokens` tokenów z bucketa.

        Args:
            tokens: Liczba tokenów do pobrania (default: 1)

        Returns:
            True jeśli tokeny dostępne i pobrane, False jeśli nie
        """
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def try_acquire(self, tokens: int = 1) -> tuple[bool, Optional[float]]:
        """
        Próbuje pobrać tokeny i zwraca sugerowany czas oczekiwania.

        Args:
            tokens: Liczba tokenów do pobrania

        Returns:
            (success: bool, wait_seconds: Optional[float])
            - success: True jeśli tokeny pobrane
            - wait_seconds: None jeśli success, inaczej sugerowany czas oczekiwania
        """
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, None

            # Oblicz czas potrzebny na uzupełnienie brakujących tokenów
            missing_tokens = tokens - self.tokens
            wait_seconds = missing_tokens / self.refill_rate
            return False, wait_seconds

    def available_tokens(self) -> float:
        """
        Zwraca liczbę dostępnych tokenów (po refill).

        Returns:
            Liczba dostępnych tokenów
        """
        with self._lock:
            self._refill()
            return self.tokens

    def reset(self) -> None:
        """Resetuje bucket do pełnej pojemności."""
        with self._lock:
            self.tokens = float(self.capacity)
            self.last_refill = time.time()
