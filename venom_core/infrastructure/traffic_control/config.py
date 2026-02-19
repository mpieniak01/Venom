"""Konfiguracja dla globalnej kontroli ruchu API."""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


class TokenBucketConfig(BaseModel):
    """Konfiguracja token bucket rate limitera."""

    capacity: int = Field(default=100, description="Pojemność bucketa (max tokenów)")
    refill_rate: float = Field(
        default=10.0, description="Liczba tokenów uzupełnianych na sekundę"
    )
    burst_capacity: Optional[int] = Field(
        default=None,
        description="Maksymalna pojemność burst (None = capacity)",
    )


class CircuitBreakerConfig(BaseModel):
    """Konfiguracja circuit breakera."""

    failure_threshold: int = Field(
        default=5, description="Liczba błędów do otwarcia circuit"
    )
    success_threshold: int = Field(
        default=2, description="Liczba sukcesów do zamknięcia circuit (half-open)"
    )
    timeout_seconds: float = Field(
        default=60.0, description="Czas oczekiwania przed half-open (sekundy)"
    )
    half_open_max_calls: int = Field(
        default=3, description="Max wywołań w stanie half-open"
    )


class RetryPolicyConfig(BaseModel):
    """Konfiguracja polityki retry."""

    max_attempts: int = Field(default=3, description="Maksymalna liczba prób")
    initial_delay_seconds: float = Field(
        default=1.0, description="Początkowe opóźnienie (sekundy)"
    )
    max_delay_seconds: float = Field(
        default=60.0, description="Maksymalne opóźnienie (sekundy)"
    )
    exponential_base: float = Field(default=2.0, description="Baza dla exponential backoff")
    jitter_factor: float = Field(
        default=0.1, description="Współczynnik jitter (0.0-1.0)"
    )


class OutboundPolicyConfig(BaseModel):
    """Polityka dla ruchu wychodzącego (external APIs)."""

    rate_limit: TokenBucketConfig = Field(
        default_factory=TokenBucketConfig, description="Rate limiter config"
    )
    circuit_breaker: CircuitBreakerConfig = Field(
        default_factory=CircuitBreakerConfig, description="Circuit breaker config"
    )
    retry_policy: RetryPolicyConfig = Field(
        default_factory=RetryPolicyConfig, description="Retry policy config"
    )
    enabled: bool = Field(default=True, description="Czy polityka jest aktywna")


class InboundPolicyConfig(BaseModel):
    """Polityka dla ruchu przychodzącego (web-next -> venom_core)."""

    rate_limit: TokenBucketConfig = Field(
        default_factory=lambda: TokenBucketConfig(capacity=200, refill_rate=20.0),
        description="Rate limiter config (wyższe limity dla inbound)",
    )
    burst_protection_enabled: bool = Field(
        default=True, description="Włącz ochronę przed burstami"
    )
    enabled: bool = Field(default=True, description="Czy polityka jest aktywna")


class TrafficControlConfig(BaseModel):
    """Globalna konfiguracja kontroli ruchu."""

    # Global defaults
    global_outbound: OutboundPolicyConfig = Field(
        default_factory=OutboundPolicyConfig,
        description="Domyślna polityka outbound",
    )
    global_inbound: InboundPolicyConfig = Field(
        default_factory=InboundPolicyConfig,
        description="Domyślna polityka inbound",
    )

    # Per-provider overrides (outbound)
    provider_policies: Dict[str, OutboundPolicyConfig] = Field(
        default_factory=dict,
        description="Polityki per provider (np. 'openai', 'github', 'reddit')",
    )

    # Per-endpoint-group overrides (inbound)
    endpoint_group_policies: Dict[str, InboundPolicyConfig] = Field(
        default_factory=dict,
        description="Polityki per endpoint group (np. 'chat', 'memory', 'workflow')",
    )

    # Telemetry & logging
    enable_telemetry: bool = Field(
        default=True, description="Włącz zbieranie metryk"
    )
    enable_logging: bool = Field(
        default=False, description="Włącz szczegółowe logowanie (opt-in via .env)"
    )
    log_rotation_hours: int = Field(
        default=24, description="Rotacja logów co N godzin"
    )
    log_retention_days: int = Field(
        default=3, description="Retencja archiwów logów (dni)"
    )
    log_max_size_mb: int = Field(
        default=1024, description="Maksymalny rozmiar logów (MB)"
    )

    # Anti-loop protection
    max_requests_per_minute_global: int = Field(
        default=1000, description="Globalny cap requestów/min (ostatnia linia obrony)"
    )
    max_retries_per_operation: int = Field(
        default=5, description="Max retry dla pojedynczej operacji"
    )
    degraded_mode_enabled: bool = Field(
        default=True,
        description="Czy włączyć twardy hard-stop (degraded mode) po przekroczeniu limitów",
    )
    degraded_mode_failure_threshold: int = Field(
        default=10,
        description="Liczba kolejnych błędów, po której wymuszamy przejście w degraded mode",
    )

    def is_under_global_request_cap(self, requests_last_minute: int) -> bool:
        """
        Sprawdza, czy globalna liczba requestów w ostatniej minucie mieści się w twardym limicie.

        Ten helper powinien być wywoływany przez TrafficController / scheduler
        przed przyjęciem nowego requestu, aby zapobiec zapętleniu lub zalaniu systemu.
        """
        return requests_last_minute < self.max_requests_per_minute_global

    def can_retry_operation(self, retry_count: int) -> bool:
        """
        Sprawdza, czy można wykonać kolejny retry dla pojedynczej operacji.

        retry_count to dotychczasowa liczba prób (0-based). Gdy osiągnie
        max_retries_per_operation, kolejne próby powinny być twardo blokowane.
        """
        return retry_count < self.max_retries_per_operation

    def should_enter_degraded_state(
        self,
        requests_last_minute: int,
        consecutive_failures: int,
    ) -> bool:
        """
        Określa, czy system powinien przejść w degraded mode na podstawie:
        - przekroczenia globalnego limitu requestów/min,
        - liczby kolejnych niepowodzeń (failures).

        Args:
            requests_last_minute: Liczba requestów w ostatniej minucie
            consecutive_failures: Liczba kolejnych błędów bez sukcesu

        Returns:
            True jeśli system powinien przejść w degraded mode
        """
        if not self.degraded_mode_enabled:
            return False

        # Przekroczenie globalnego limitu
        if requests_last_minute >= self.max_requests_per_minute_global:
            return True

        # Zbyt wiele kolejnych niepowodzeń
        if consecutive_failures >= self.degraded_mode_failure_threshold:
            return True

        return False

    @classmethod
    def from_env(cls) -> TrafficControlConfig:
        """Tworzy konfigurację z zmiennych środowiskowych."""
        import os

        enable_logging = os.getenv("ENABLE_TRAFFIC_CONTROL_LOGGING", "false").lower() == "true"

        config = cls(enable_logging=enable_logging)

        # Provider-specific overrides (przykład: GitHub ma niższe limity)
        config.provider_policies["github"] = OutboundPolicyConfig(
            rate_limit=TokenBucketConfig(capacity=60, refill_rate=1.0),  # 60/min
            circuit_breaker=CircuitBreakerConfig(failure_threshold=3),
        )

        # Provider-specific overrides (przykład: Reddit ma niższe limity)
        config.provider_policies["reddit"] = OutboundPolicyConfig(
            rate_limit=TokenBucketConfig(capacity=60, refill_rate=1.0),  # 60/min
        )

        # OpenAI ma wyższe limity tier-dependent (przykład: tier 1)
        config.provider_policies["openai"] = OutboundPolicyConfig(
            rate_limit=TokenBucketConfig(capacity=500, refill_rate=8.33),  # ~500/min
        )

        # Endpoint group overrides (przykład: chat ma wyższe limity)
        config.endpoint_group_policies["chat"] = InboundPolicyConfig(
            rate_limit=TokenBucketConfig(capacity=300, refill_rate=30.0),
        )

        # Endpoint group overrides (przykład: memory ma niższe limity)
        config.endpoint_group_policies["memory"] = InboundPolicyConfig(
            rate_limit=TokenBucketConfig(capacity=100, refill_rate=10.0),
        )

        return config
