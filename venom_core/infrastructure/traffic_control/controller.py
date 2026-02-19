"""Traffic controller - orchestrator dla globalnej kontroli ruchu API."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, Optional

from .circuit_breaker import CircuitBreaker, CircuitState
from .config import (
    InboundPolicyConfig,
    OutboundPolicyConfig,
    TrafficControlConfig,
)
from .retry_policy import RetryPolicy
from .token_bucket import TokenBucket


@dataclass
class TrafficMetrics:
    """Metryki ruchu dla telemetrii."""

    total_requests: int = 0
    total_2xx: int = 0
    total_4xx: int = 0
    total_5xx: int = 0
    total_429: int = 0
    total_retries: int = 0
    total_circuit_open: int = 0


@dataclass
class ScopePolicy:
    """Polityka dla danego scope (provider/endpoint)."""

    scope: str
    rate_limiter: TokenBucket
    circuit_breaker: Optional[CircuitBreaker] = None
    retry_policy: Optional[RetryPolicy] = None
    metrics: TrafficMetrics = field(default_factory=TrafficMetrics)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)


class TrafficController:
    """
    Globalny kontroler ruchu API - outbound i inbound.

    Odpowiada za:
    1. Rate limiting per scope (provider/endpoint/group)
    2. Circuit breaker dla ochrony przed degradacją
    3. Retry policy z exponential backoff
    4. Telemetria i metryki
    5. Anti-loop protection
    """

    def __init__(self, config: Optional[TrafficControlConfig] = None):
        """
        Inicjalizacja traffic controllera.

        Args:
            config: Konfiguracja (default: from_env())
        """
        self.config = config or TrafficControlConfig.from_env()
        self._outbound_policies: Dict[str, ScopePolicy] = {}
        self._inbound_policies: Dict[str, ScopePolicy] = {}
        self._lock = threading.Lock()

        # Global metrics
        self.global_metrics = TrafficMetrics()

    def _get_or_create_outbound_policy(self, scope: str) -> ScopePolicy:
        """
        Pobiera lub tworzy politykę outbound dla danego scope.

        Args:
            scope: Scope (np. 'openai', 'github', 'reddit')

        Returns:
            ScopePolicy dla danego scope
        """
        with self._lock:
            if scope not in self._outbound_policies:
                # Sprawdź czy jest custom policy dla tego providera
                provider_config = self.config.provider_policies.get(
                    scope, self.config.global_outbound
                )

                rate_limiter = TokenBucket(
                    capacity=provider_config.rate_limit.capacity,
                    refill_rate=provider_config.rate_limit.refill_rate,
                )

                circuit_breaker = CircuitBreaker(
                    failure_threshold=provider_config.circuit_breaker.failure_threshold,
                    success_threshold=provider_config.circuit_breaker.success_threshold,
                    timeout_seconds=provider_config.circuit_breaker.timeout_seconds,
                    half_open_max_calls=provider_config.circuit_breaker.half_open_max_calls,
                )

                retry_policy = RetryPolicy(
                    max_attempts=provider_config.retry_policy.max_attempts,
                    initial_delay_seconds=provider_config.retry_policy.initial_delay_seconds,
                    max_delay_seconds=provider_config.retry_policy.max_delay_seconds,
                    exponential_base=provider_config.retry_policy.exponential_base,
                    jitter_factor=provider_config.retry_policy.jitter_factor,
                )

                self._outbound_policies[scope] = ScopePolicy(
                    scope=scope,
                    rate_limiter=rate_limiter,
                    circuit_breaker=circuit_breaker,
                    retry_policy=retry_policy,
                )

            return self._outbound_policies[scope]

    def _get_or_create_inbound_policy(self, scope: str) -> ScopePolicy:
        """
        Pobiera lub tworzy politykę inbound dla danego scope.

        Args:
            scope: Scope (np. 'chat', 'memory', 'workflow')

        Returns:
            ScopePolicy dla danego scope
        """
        with self._lock:
            if scope not in self._inbound_policies:
                # Sprawdź czy jest custom policy dla tego endpoint group
                endpoint_config = self.config.endpoint_group_policies.get(
                    scope, self.config.global_inbound
                )

                rate_limiter = TokenBucket(
                    capacity=endpoint_config.rate_limit.capacity,
                    refill_rate=endpoint_config.rate_limit.refill_rate,
                )

                # Inbound nie używa circuit breaker ani retry (to dla klienta)
                self._inbound_policies[scope] = ScopePolicy(
                    scope=scope,
                    rate_limiter=rate_limiter,
                    circuit_breaker=None,
                    retry_policy=None,
                )

            return self._inbound_policies[scope]

    def check_outbound_request(
        self, provider: str, tokens: int = 1
    ) -> tuple[bool, Optional[str], Optional[float]]:
        """
        Sprawdza czy outbound request może przejść (rate limit + circuit breaker).

        Args:
            provider: Nazwa providera (np. 'openai', 'github')
            tokens: Liczba tokenów do pobrania (default: 1)

        Returns:
            (allowed: bool, reason: Optional[str], wait_seconds: Optional[float])
            - allowed: True jeśli request może być wykonany
            - reason: Powód odrzucenia (jeśli allowed=False)
            - wait_seconds: Sugerowany czas oczekiwania (jeśli rate limit)
        """
        policy = self._get_or_create_outbound_policy(provider)

        # Check circuit breaker first
        if policy.circuit_breaker and not policy.circuit_breaker.is_request_allowed():
            with policy._lock:
                policy.metrics.total_circuit_open += 1
            return False, "circuit_breaker_open", None

        # Check rate limit
        success, wait_seconds = policy.rate_limiter.try_acquire(tokens)
        if not success:
            return False, "rate_limit_exceeded", wait_seconds

        with policy._lock:
            policy.metrics.total_requests += 1

        return True, None, None

    def record_outbound_response(
        self, provider: str, status_code: Optional[int], exception: Optional[Exception] = None
    ) -> None:
        """
        Rejestruje odpowiedź outbound request (dla circuit breaker i metryk).

        Args:
            provider: Nazwa providera
            status_code: Kod statusu HTTP (lub None jeśli exception)
            exception: Exception jeśli wystąpił błąd
        """
        policy = self._get_or_create_outbound_policy(provider)

        # Update metrics
        with policy._lock:
            if status_code is not None:
                if 200 <= status_code < 300:
                    policy.metrics.total_2xx += 1
                elif 400 <= status_code < 500:
                    policy.metrics.total_4xx += 1
                    if status_code == 429:
                        policy.metrics.total_429 += 1
                elif 500 <= status_code < 600:
                    policy.metrics.total_5xx += 1

        # Circuit breaker logic
        if policy.circuit_breaker:
            # Success: 2xx responses
            if status_code is not None and 200 <= status_code < 300:
                policy.circuit_breaker.record_success()
            # Failure: 5xx, timeout, connection errors
            elif exception or (status_code and status_code >= 500):
                policy.circuit_breaker.record_failure()

    def check_inbound_request(
        self, endpoint_group: str, tokens: int = 1
    ) -> tuple[bool, Optional[str], Optional[float]]:
        """
        Sprawdza czy inbound request może przejść (rate limit).

        Args:
            endpoint_group: Grupa endpointów (np. 'chat', 'memory', 'workflow')
            tokens: Liczba tokenów do pobrania (default: 1)

        Returns:
            (allowed: bool, reason: Optional[str], wait_seconds: Optional[float])
        """
        policy = self._get_or_create_inbound_policy(endpoint_group)

        success, wait_seconds = policy.rate_limiter.try_acquire(tokens)
        if not success:
            return False, "rate_limit_exceeded", wait_seconds

        with policy._lock:
            policy.metrics.total_requests += 1

        return True, None, None

    def get_metrics(self, scope: Optional[str] = None) -> Dict[str, Any]:
        """
        Zwraca metryki dla danego scope lub globalne.

        Args:
            scope: Scope (provider/endpoint) lub None dla globalnych

        Returns:
            Dict z metrykami
        """
        if scope is None:
            # Global metrics
            return {
                "global": {
                    "total_requests": self.global_metrics.total_requests,
                    "total_2xx": self.global_metrics.total_2xx,
                    "total_4xx": self.global_metrics.total_4xx,
                    "total_5xx": self.global_metrics.total_5xx,
                    "total_429": self.global_metrics.total_429,
                    "total_retries": self.global_metrics.total_retries,
                },
                "outbound_scopes": list(self._outbound_policies.keys()),
                "inbound_scopes": list(self._inbound_policies.keys()),
            }

        # Scope-specific metrics
        policy = self._outbound_policies.get(scope) or self._inbound_policies.get(scope)
        if not policy:
            return {"error": f"Unknown scope: {scope}"}

        with policy._lock:
            result = {
                "scope": scope,
                "metrics": {
                    "total_requests": policy.metrics.total_requests,
                    "total_2xx": policy.metrics.total_2xx,
                    "total_4xx": policy.metrics.total_4xx,
                    "total_5xx": policy.metrics.total_5xx,
                    "total_429": policy.metrics.total_429,
                    "total_retries": policy.metrics.total_retries,
                    "total_circuit_open": policy.metrics.total_circuit_open,
                },
                "rate_limit": {
                    "available_tokens": policy.rate_limiter.available_tokens(),
                    "capacity": policy.rate_limiter.capacity,
                    "refill_rate": policy.rate_limiter.refill_rate,
                },
            }

            if policy.circuit_breaker:
                result["circuit_breaker"] = policy.circuit_breaker.get_stats()

            return result


# Singleton instance
_traffic_controller: Optional[TrafficController] = None
_tc_lock = threading.Lock()


def get_traffic_controller() -> TrafficController:
    """
    Zwraca singleton instance TrafficController (thread-safe).

    Returns:
        TrafficController instance
    """
    global _traffic_controller
    if _traffic_controller is None:
        with _tc_lock:
            if _traffic_controller is None:
                _traffic_controller = TrafficController()
    return _traffic_controller
