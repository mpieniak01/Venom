"""Traffic controller - orchestrator dla globalnej kontroli ruchu API."""

from __future__ import annotations

import logging
import os
import stat
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from venom_core.infrastructure.traffic_control.circuit_breaker import CircuitBreaker
from venom_core.infrastructure.traffic_control.config import TrafficControlConfig
from venom_core.infrastructure.traffic_control.retry_policy import RetryPolicy
from venom_core.infrastructure.traffic_control.token_bucket import TokenBucket


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
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )


class TrafficController:
    """
    Globalny kontroler ruchu API - outbound i inbound.

    Odpowiada za:
    1. Rate limiting per scope (provider/method/endpoint-group)
    2. Circuit breaker dla ochrony przed degradacją
    3. Retry policy z exponential backoff
    4. Telemetrię i metryki
    5. Anti-loop protection (global cap + degraded mode)
    """

    def __init__(self, config: Optional[TrafficControlConfig] = None):
        self.config = config or TrafficControlConfig.from_env()
        self._outbound_policies: Dict[str, ScopePolicy] = {}
        self._inbound_policies: Dict[str, ScopePolicy] = {}
        self._lock = threading.Lock()

        # Anti-loop state
        self._outbound_request_times: deque[float] = deque()
        self._degraded_until_ts: float = 0.0
        self._consecutive_failures: int = 0

        # Global metrics
        self.global_metrics = TrafficMetrics()

        self._setup_rotating_logging_if_enabled()

    def _setup_rotating_logging_if_enabled(self) -> None:
        """Konfiguruje dedykowaną rotację logów traffic-control (opt-in)."""
        if not self.config.enable_logging:
            return

        log_dir = self._resolve_safe_log_dir()
        log_path = log_dir / "traffic-control.log"
        tc_logger = logging.getLogger("venom_core.traffic_control")

        if any(
            isinstance(handler, TimedRotatingFileHandler)
            and getattr(handler, "baseFilename", "") == str(log_path)
            for handler in tc_logger.handlers
        ):
            return

        handler = TimedRotatingFileHandler(
            filename=str(log_path),
            when="h",
            interval=self.config.log_rotation_hours,
            backupCount=self.config.log_retention_days,
            encoding="utf-8",
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        tc_logger.addHandler(handler)
        tc_logger.setLevel(logging.INFO)
        tc_logger.propagate = False
        self._enforce_log_storage_budget(log_dir)

    def _resolve_safe_log_dir(self) -> Path:
        """
        Rozwiązuje bezpieczny katalog logów traffic-control.

        Jeśli bazowy katalog jest publicznie zapisywalny (np. /tmp), tworzony jest
        izolowany podkatalog per-user z uprawnieniami 0700.
        """
        raw_dir = self.config.log_dir
        base_dir = Path(raw_dir).expanduser().resolve()
        base_dir.mkdir(parents=True, exist_ok=True)

        try:
            base_stat = base_dir.stat()
        except OSError:
            return base_dir

        is_world_writable = bool(base_stat.st_mode & stat.S_IWOTH)
        is_sticky = bool(base_stat.st_mode & stat.S_ISVTX)
        if is_world_writable:
            uid = os.getuid() if hasattr(os, "getuid") else None
            scoped_name = f"user-{uid}" if uid is not None else "user-local"
            scoped_dir = base_dir / scoped_name
            scoped_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(scoped_dir, 0o700)
            except OSError:
                # Best-effort on platforms/filesystems without chmod support.
                pass
            return scoped_dir

        if not is_sticky:
            try:
                os.chmod(base_dir, 0o700)
            except OSError:
                pass
        return base_dir

    def _enforce_log_storage_budget(self, log_dir: Path) -> None:
        """Czyści najstarsze archiwa jeśli przekroczono budżet miejsca."""
        max_bytes = self.config.log_max_size_mb * 1024 * 1024
        files = sorted(
            (item for item in log_dir.glob("traffic-control.log*") if item.is_file()),
            key=lambda item: item.stat().st_mtime,
        )
        total_size = sum(item.stat().st_size for item in files)
        while files and total_size > max_bytes:
            oldest = files.pop(0)
            try:
                size = oldest.stat().st_size
                oldest.unlink()
                total_size -= size
            except OSError:
                break

    def _is_degraded_mode_active(self) -> bool:
        if not self.config.degraded_mode_enabled:
            return False
        return time.monotonic() < self._degraded_until_ts

    def _track_outbound_request_and_check_global_cap(self) -> bool:
        """
        Rejestruje request i sprawdza globalny cap/min.

        Zwraca False, gdy przekroczono limit i należy zablokować request.
        """
        now = time.monotonic()
        with self._lock:
            while (
                self._outbound_request_times
                and now - self._outbound_request_times[0] > 60
            ):
                self._outbound_request_times.popleft()
            requests_last_minute = len(self._outbound_request_times)
            if not self.config.is_under_global_request_cap(requests_last_minute):
                if self.config.should_enter_degraded_state(
                    requests_last_minute=requests_last_minute,
                    consecutive_failures=self._consecutive_failures,
                ):
                    self._degraded_until_ts = max(
                        self._degraded_until_ts,
                        now + self.config.degraded_mode_cooldown_seconds,
                    )
                return False
            self._outbound_request_times.append(now)
            return True

    def _build_outbound_scope(self, provider: str, method: Optional[str]) -> str:
        if not method:
            return provider
        return f"{provider}:{method.lower()}"

    def _build_inbound_scope(
        self,
        endpoint_group: str,
        actor: Optional[str],
        session_id: Optional[str],
        client_ip: Optional[str],
    ) -> str:
        if actor:
            return f"{endpoint_group}:actor:{actor}"
        if session_id:
            return f"{endpoint_group}:session:{session_id}"
        if client_ip:
            return f"{endpoint_group}:ip:{client_ip}"
        return endpoint_group

    def _get_or_create_outbound_policy(self, scope: str) -> ScopePolicy:
        with self._lock:
            if scope not in self._outbound_policies:
                base_provider = scope.split(":", 1)[0]
                provider_config = self.config.provider_policies.get(
                    base_provider, self.config.global_outbound
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
                    max_attempts=min(
                        provider_config.retry_policy.max_attempts,
                        self.config.max_retries_per_operation,
                    ),
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
        with self._lock:
            if scope not in self._inbound_policies:
                endpoint_group = scope.split(":", 1)[0]
                endpoint_config = self.config.endpoint_group_policies.get(
                    endpoint_group, self.config.global_inbound
                )
                rate_limiter = TokenBucket(
                    capacity=endpoint_config.rate_limit.capacity,
                    refill_rate=endpoint_config.rate_limit.refill_rate,
                )
                self._inbound_policies[scope] = ScopePolicy(
                    scope=scope,
                    rate_limiter=rate_limiter,
                    circuit_breaker=None,
                    retry_policy=None,
                )
            return self._inbound_policies[scope]

    def check_outbound_request(
        self,
        provider: str,
        tokens: int = 1,
        method: Optional[str] = None,
    ) -> tuple[bool, Optional[str], Optional[float]]:
        if self._is_degraded_mode_active():
            return False, "degraded_mode_active", None
        if not self._track_outbound_request_and_check_global_cap():
            return False, "global_request_cap_exceeded", 60.0

        scope = self._build_outbound_scope(provider, method)
        policy = self._get_or_create_outbound_policy(scope)

        if policy.circuit_breaker and not policy.circuit_breaker.is_request_allowed():
            with policy._lock:
                policy.metrics.total_circuit_open += 1
            return False, "circuit_breaker_open", None

        success, wait_seconds = policy.rate_limiter.try_acquire(tokens)
        if not success:
            return False, "rate_limit_exceeded", wait_seconds

        with policy._lock:
            policy.metrics.total_requests += 1
        return True, None, None

    @staticmethod
    def _is_success_status(status_code: Optional[int]) -> bool:
        return status_code is not None and 200 <= status_code < 300

    @staticmethod
    def _is_4xx_status(status_code: Optional[int]) -> bool:
        return status_code is not None and 400 <= status_code < 500

    @staticmethod
    def _is_5xx_status(status_code: Optional[int]) -> bool:
        return status_code is not None and 500 <= status_code < 600

    @staticmethod
    def _is_failure_outcome(
        status_code: Optional[int], exception: Optional[Exception]
    ) -> bool:
        return exception is not None or (status_code is not None and status_code >= 500)

    @staticmethod
    def _update_policy_metrics(policy: ScopePolicy, status_code: Optional[int]) -> None:
        if status_code is None:
            return
        if TrafficController._is_success_status(status_code):
            policy.metrics.total_2xx += 1
            return
        if TrafficController._is_4xx_status(status_code):
            policy.metrics.total_4xx += 1
            if status_code == 429:
                policy.metrics.total_429 += 1
            return
        if TrafficController._is_5xx_status(status_code):
            policy.metrics.total_5xx += 1

    def _update_circuit_breaker(
        self,
        policy: ScopePolicy,
        status_code: Optional[int],
        exception: Optional[Exception],
    ) -> None:
        if not policy.circuit_breaker:
            return
        if self._is_success_status(status_code):
            policy.circuit_breaker.record_success()
            return
        if self._is_failure_outcome(status_code, exception):
            policy.circuit_breaker.record_failure()

    def _update_degraded_state(
        self,
        *,
        status_code: Optional[int],
        exception: Optional[Exception],
    ) -> None:
        is_success = self._is_success_status(status_code)
        if is_success:
            self._consecutive_failures = 0
            return
        if not self._is_failure_outcome(status_code, exception):
            return
        self._consecutive_failures += 1
        requests_last_minute = len(self._outbound_request_times)
        if self.config.should_enter_degraded_state(
            requests_last_minute=requests_last_minute,
            consecutive_failures=self._consecutive_failures,
        ):
            self._degraded_until_ts = max(
                self._degraded_until_ts,
                time.monotonic() + self.config.degraded_mode_cooldown_seconds,
            )

    def record_outbound_response(
        self,
        provider: str,
        status_code: Optional[int],
        exception: Optional[Exception] = None,
        method: Optional[str] = None,
    ) -> None:
        scope = self._build_outbound_scope(provider, method)
        policy = self._get_or_create_outbound_policy(scope)

        with policy._lock:
            self._update_policy_metrics(policy, status_code)

        self._update_circuit_breaker(policy, status_code, exception)

        with self._lock:
            self._update_degraded_state(status_code=status_code, exception=exception)

    def check_inbound_request(
        self,
        endpoint_group: str,
        tokens: int = 1,
        actor: Optional[str] = None,
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> tuple[bool, Optional[str], Optional[float]]:
        scope = self._build_inbound_scope(endpoint_group, actor, session_id, client_ip)
        policy = self._get_or_create_inbound_policy(scope)

        success, wait_seconds = policy.rate_limiter.try_acquire(tokens)
        if not success:
            return False, "rate_limit_exceeded", wait_seconds

        with policy._lock:
            policy.metrics.total_requests += 1
        return True, None, None

    def get_metrics(self, scope: Optional[str] = None) -> Dict[str, Any]:
        if scope is None:
            with self._lock:
                requests_last_minute = len(self._outbound_request_times)
                degraded_active = self._is_degraded_mode_active()
                degraded_until_ts = self._degraded_until_ts
            return {
                "global": {
                    "total_requests": self.global_metrics.total_requests,
                    "total_2xx": self.global_metrics.total_2xx,
                    "total_4xx": self.global_metrics.total_4xx,
                    "total_5xx": self.global_metrics.total_5xx,
                    "total_429": self.global_metrics.total_429,
                    "total_retries": self.global_metrics.total_retries,
                    "requests_last_minute": requests_last_minute,
                    "degraded_mode_active": degraded_active,
                    "degraded_until_ts": degraded_until_ts,
                },
                "outbound_scopes": list(self._outbound_policies.keys()),
                "inbound_scopes": list(self._inbound_policies.keys()),
            }

        policy = self._outbound_policies.get(scope) or self._inbound_policies.get(scope)
        if not policy:
            method_scopes = {
                name: item
                for name, item in self._outbound_policies.items()
                if name.startswith(f"{scope}:")
            }
            if not method_scopes:
                return {"error": f"Unknown scope: {scope}"}
            return self._aggregate_scope_metrics(scope, method_scopes)

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

    def _aggregate_scope_metrics(
        self,
        scope: str,
        method_scopes: Dict[str, ScopePolicy],
    ) -> Dict[str, Any]:
        """Agreguje metryki provider-level z wielu scope'ów provider:method."""
        totals = TrafficMetrics()
        min_tokens = None
        capacity = 0
        refill_rate = 0.0
        for policy in method_scopes.values():
            with policy._lock:
                totals.total_requests += policy.metrics.total_requests
                totals.total_2xx += policy.metrics.total_2xx
                totals.total_4xx += policy.metrics.total_4xx
                totals.total_5xx += policy.metrics.total_5xx
                totals.total_429 += policy.metrics.total_429
                totals.total_retries += policy.metrics.total_retries
                totals.total_circuit_open += policy.metrics.total_circuit_open
                current_tokens = policy.rate_limiter.available_tokens()
                min_tokens = (
                    current_tokens
                    if min_tokens is None
                    else min(min_tokens, current_tokens)
                )
                capacity = max(capacity, policy.rate_limiter.capacity)
                refill_rate = max(refill_rate, policy.rate_limiter.refill_rate)

        return {
            "scope": scope,
            "aggregated_from": sorted(method_scopes.keys()),
            "metrics": {
                "total_requests": totals.total_requests,
                "total_2xx": totals.total_2xx,
                "total_4xx": totals.total_4xx,
                "total_5xx": totals.total_5xx,
                "total_429": totals.total_429,
                "total_retries": totals.total_retries,
                "total_circuit_open": totals.total_circuit_open,
            },
            "rate_limit": {
                "available_tokens": min_tokens if min_tokens is not None else 0.0,
                "capacity": capacity,
                "refill_rate": refill_rate,
            },
        }


# Singleton instance
_traffic_controller: Optional[TrafficController] = None
_tc_lock = threading.Lock()


def get_traffic_controller() -> TrafficController:
    """Zwraca singleton instance TrafficController (thread-safe)."""
    global _traffic_controller
    if _traffic_controller is None:
        with _tc_lock:
            if _traffic_controller is None:
                _traffic_controller = TrafficController()
    return _traffic_controller
