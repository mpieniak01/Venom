"""Moduł: provider_governance - bezpieczeństwo kluczy, limity kosztów i fallback policy."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CredentialStatus(str, Enum):
    """Status konfiguracji credentiali providera."""

    CONFIGURED = "configured"
    MISSING_CREDENTIALS = "missing_credentials"
    INVALID_CREDENTIALS = "invalid_credentials"


class FallbackReasonCode(str, Enum):
    """Kody przyczyn przełączenia providera."""

    TIMEOUT = "TIMEOUT"
    AUTH_ERROR = "AUTH_ERROR"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    PROVIDER_DEGRADED = "PROVIDER_DEGRADED"
    PROVIDER_OFFLINE = "PROVIDER_OFFLINE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"


class LimitType(str, Enum):
    """Typ limitu kosztowego/ruchu."""

    GLOBAL = "global"
    PER_PROVIDER = "per_provider"
    PER_MODEL = "per_model"


@dataclass
class CostLimit:
    """Definicja limitu kosztowego."""

    limit_type: LimitType
    scope: str  # "global", provider name, or model name
    soft_limit_usd: float
    hard_limit_usd: float
    current_usage_usd: float = 0.0
    period_start: datetime = field(default_factory=datetime.now)


@dataclass
class RateLimit:
    """Definicja limitu częstotliwości requestów."""

    limit_type: LimitType
    scope: str
    max_requests_per_minute: int
    max_tokens_per_minute: int
    current_requests: int = 0
    current_tokens: int = 0
    period_start: datetime = field(default_factory=datetime.now)


@dataclass
class FallbackEvent:
    """Zdarzenie przełączenia providera."""

    timestamp: datetime
    from_provider: str
    to_provider: str
    reason_code: FallbackReasonCode
    message: str
    technical_details: Optional[str] = None


class FallbackPolicy(BaseModel):
    """Polityka fallback dla providerów."""

    preferred_provider: str = Field(
        default="ollama", description="Preferowany provider"
    )
    fallback_order: List[str] = Field(
        default_factory=lambda: ["ollama", "vllm", "openai", "google"],
        description="Kolejność awaryjna providerów",
    )
    enable_timeout_fallback: bool = Field(
        default=True, description="Włącz fallback przy timeout"
    )
    enable_auth_fallback: bool = Field(
        default=True, description="Włącz fallback przy błędzie autoryzacji"
    )
    enable_budget_fallback: bool = Field(
        default=True, description="Włącz fallback przy przekroczeniu budżetu"
    )
    enable_degraded_fallback: bool = Field(
        default=True, description="Włącz fallback przy degradacji providera"
    )
    timeout_threshold_seconds: float = Field(
        default=30.0, description="Próg timeout w sekundach"
    )


class GovernanceDecision(BaseModel):
    """Decyzja governance dla requestu."""

    allowed: bool = Field(..., description="Czy request jest dozwolony")
    provider: Optional[str] = Field(None, description="Wybrany provider")
    reason_code: Optional[str] = Field(None, description="Kod przyczyny decyzji")
    user_message: str = Field(
        default="", description="Komunikat dla użytkownika (i18n ready)"
    )
    technical_details: Optional[str] = Field(
        None, description="Szczegóły techniczne (dla logów)"
    )
    fallback_applied: bool = Field(
        default=False, description="Czy zastosowano fallback"
    )


class ProviderGovernance:
    """
    Warstwa zarządzania ryzykiem dla providerów modeli.

    Odpowiada za:
    1. Bezpieczne zarządzanie credentialami
    2. Limity kosztowe i rate-limit per provider/model
    3. Przewidywalne fallbacki z pełnym audytem decyzji
    """

    def __init__(
        self,
        fallback_policy: Optional[FallbackPolicy] = None,
    ):
        """
        Inicjalizacja Provider Governance.

        Args:
            fallback_policy: Polityka fallback (opcjonalne, domyślna jeśli None)
        """
        self.fallback_policy = fallback_policy or FallbackPolicy()
        self.cost_limits: Dict[str, CostLimit] = {}
        self.rate_limits: Dict[str, RateLimit] = {}
        self.fallback_history: List[FallbackEvent] = []
        self._lock = threading.Lock()  # Thread safety for concurrent access

        # Inicjalizuj domyślne limity globalne
        self._init_default_limits()

        logger.info(
            f"ProviderGovernance zainicjalizowany - preferred_provider: {self.fallback_policy.preferred_provider}"
        )

    def _init_default_limits(self) -> None:
        """Inicjalizuj domyślne limity kosztowe i rate."""
        # Global cost limit
        self.cost_limits["global"] = CostLimit(
            limit_type=LimitType.GLOBAL,
            scope="global",
            soft_limit_usd=10.0,  # Soft warning at $10
            hard_limit_usd=50.0,  # Hard block at $50
        )

        # Global rate limit
        self.rate_limits["global"] = RateLimit(
            limit_type=LimitType.GLOBAL,
            scope="global",
            max_requests_per_minute=100,
            max_tokens_per_minute=100000,
        )

    def validate_credentials(self, provider: str) -> CredentialStatus:
        """
        Waliduje credentiale providera bez ujawniania sekretów.

        Args:
            provider: Nazwa providera

        Returns:
            Status konfiguracji credentiali
        """
        # Implementacja walidacji dla każdego providera
        if provider == "openai":
            api_key = SETTINGS.OPENAI_API_KEY
            if not api_key or api_key.strip() == "":
                return CredentialStatus.MISSING_CREDENTIALS
            # W produkcji: testuj connection z masked key
            return CredentialStatus.CONFIGURED

        elif provider == "google":
            api_key = SETTINGS.GOOGLE_API_KEY
            if not api_key or api_key.strip() == "":
                return CredentialStatus.MISSING_CREDENTIALS
            return CredentialStatus.CONFIGURED

        elif provider in ("ollama", "vllm"):
            # Lokalne runtimes nie wymagają credentials
            return CredentialStatus.CONFIGURED

        elif provider == "huggingface":
            # HuggingFace działa jako catalog, credentials opcjonalne
            return CredentialStatus.CONFIGURED

        logger.warning(f"Unknown provider for credential validation: {provider}")
        return CredentialStatus.MISSING_CREDENTIALS

    def mask_secret(self, secret: str) -> str:
        """
        Maskuje sekret do bezpiecznego logowania.

        Args:
            secret: Sekret do zamaskowania

        Returns:
            Zamaskowany sekret
        """
        if not secret or len(secret) < 8:
            return "***"
        return f"{secret[:4]}...{secret[-4:]}"

    def check_cost_limit(
        self, provider: str, estimated_cost_usd: float
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Sprawdza czy request mieści się w limitach kosztowych.

        Args:
            provider: Nazwa providera
            estimated_cost_usd: Szacowany koszt w USD

        Returns:
            Tuple (allowed, reason_code, message)
        """
        # Check global limit
        global_limit = self.cost_limits.get("global")
        if global_limit:
            total_cost = global_limit.current_usage_usd + estimated_cost_usd

            if total_cost > global_limit.hard_limit_usd:
                return (
                    False,
                    "BUDGET_HARD_LIMIT_EXCEEDED",
                    f"Global hard limit exceeded: ${total_cost:.2f} > ${global_limit.hard_limit_usd:.2f}",
                )

            if total_cost > global_limit.soft_limit_usd:
                logger.warning(
                    f"Global soft limit warning: ${total_cost:.2f} > ${global_limit.soft_limit_usd:.2f}"
                )

        # Check per-provider limit
        provider_limit = self.cost_limits.get(f"provider:{provider}")
        if provider_limit:
            total_cost = provider_limit.current_usage_usd + estimated_cost_usd

            if total_cost > provider_limit.hard_limit_usd:
                return (
                    False,
                    "PROVIDER_BUDGET_EXCEEDED",
                    f"Provider {provider} hard limit exceeded: ${total_cost:.2f} > ${provider_limit.hard_limit_usd:.2f}",
                )

        return (True, None, None)

    def check_rate_limit(
        self, provider: str, estimated_tokens: int
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Sprawdza czy request mieści się w limitach częstotliwości.

        Args:
            provider: Nazwa providera
            estimated_tokens: Szacowana liczba tokenów

        Returns:
            Tuple (allowed, reason_code, message)
        """
        with self._lock:
            # Reset counters if period expired (1 minute window)
            global_limit = self.rate_limits.get("global")
            if global_limit:
                if (datetime.now() - global_limit.period_start) > timedelta(minutes=1):
                    global_limit.current_requests = 0
                    global_limit.current_tokens = 0
                    global_limit.period_start = datetime.now()

                if global_limit.current_requests + 1 > global_limit.max_requests_per_minute:
                    return (
                        False,
                        "RATE_LIMIT_REQUESTS_EXCEEDED",
                        f"Global request rate limit exceeded: {global_limit.current_requests + 1} > {global_limit.max_requests_per_minute}/min",
                    )

                if (
                    global_limit.current_tokens + estimated_tokens
                    > global_limit.max_tokens_per_minute
                ):
                    return (
                        False,
                        "RATE_LIMIT_TOKENS_EXCEEDED",
                        f"Global token rate limit exceeded: {global_limit.current_tokens + estimated_tokens} > {global_limit.max_tokens_per_minute}/min",
                    )

            return (True, None, None)

    def record_usage(
        self, provider: str, cost_usd: float, tokens: int, requests: int = 1
    ) -> None:
        """
        Rejestruje zużycie zasobów.

        Args:
            provider: Nazwa providera
            cost_usd: Koszt w USD
            tokens: Liczba tokenów
            requests: Liczba requestów (domyślnie 1)
        """
        with self._lock:
            # Update global cost
            global_cost = self.cost_limits.get("global")
            if global_cost:
                global_cost.current_usage_usd += cost_usd

            # Update provider cost
            provider_key = f"provider:{provider}"
            if provider_key not in self.cost_limits:
                self.cost_limits[provider_key] = CostLimit(
                    limit_type=LimitType.PER_PROVIDER,
                    scope=provider,
                    soft_limit_usd=5.0,
                    hard_limit_usd=25.0,
                )
            self.cost_limits[provider_key].current_usage_usd += cost_usd

            # Update global rate
            global_rate = self.rate_limits.get("global")
            if global_rate:
                global_rate.current_requests += requests
                global_rate.current_tokens += tokens

    def select_provider_with_fallback(
        self, preferred_provider: Optional[str] = None, reason: Optional[str] = None
    ) -> GovernanceDecision:
        """
        Wybiera provider z uwzględnieniem fallback policy.

        Args:
            preferred_provider: Preferowany provider (None = użyj policy default)
            reason: Powód fallback (jeśli znany)

        Returns:
            GovernanceDecision z wybranym providerem
        """
        target_provider = preferred_provider or self.fallback_policy.preferred_provider

        # Check credential status
        cred_status = self.validate_credentials(target_provider)
        if cred_status != CredentialStatus.CONFIGURED:
            # Try fallback
            fallback_provider = self._find_fallback_provider(
                target_provider, FallbackReasonCode.AUTH_ERROR
            )
            if fallback_provider:
                self._record_fallback_event(
                    target_provider,
                    fallback_provider,
                    FallbackReasonCode.AUTH_ERROR,
                    f"Credentials not configured for {target_provider}",
                )
                return GovernanceDecision(
                    allowed=True,
                    provider=fallback_provider,
                    reason_code="FALLBACK_AUTH_ERROR",
                    user_message=f"Switched to {fallback_provider} due to missing credentials",
                    fallback_applied=True,
                )
            else:
                return GovernanceDecision(
                    allowed=False,
                    provider=None,
                    reason_code="NO_PROVIDER_AVAILABLE",
                    user_message=f"No provider available: {target_provider} credentials missing and no fallback",
                )

        return GovernanceDecision(
            allowed=True,
            provider=target_provider,
            user_message=f"Using provider: {target_provider}",
        )

    def _find_fallback_provider(
        self, failed_provider: str, reason: FallbackReasonCode
    ) -> Optional[str]:
        """
        Znajduje alternatywny provider zgodnie z fallback policy.

        Args:
            failed_provider: Provider który zawiódł
            reason: Powód awarii

        Returns:
            Nazwa alternatywnego providera lub None
        """
        # Check if fallback enabled for this reason
        if reason == FallbackReasonCode.TIMEOUT and not self.fallback_policy.enable_timeout_fallback:
            return None
        if reason == FallbackReasonCode.AUTH_ERROR and not self.fallback_policy.enable_auth_fallback:
            return None
        if reason == FallbackReasonCode.BUDGET_EXCEEDED and not self.fallback_policy.enable_budget_fallback:
            return None
        if reason == FallbackReasonCode.PROVIDER_DEGRADED and not self.fallback_policy.enable_degraded_fallback:
            return None

        # Find next available provider in fallback order
        fallback_candidates = [
            p for p in self.fallback_policy.fallback_order if p != failed_provider
        ]

        for candidate in fallback_candidates:
            if self.validate_credentials(candidate) == CredentialStatus.CONFIGURED:
                return candidate

        return None

    def _record_fallback_event(
        self,
        from_provider: str,
        to_provider: str,
        reason_code: FallbackReasonCode,
        message: str,
        technical_details: Optional[str] = None,
    ) -> None:
        """
        Rejestruje zdarzenie fallback w audycie.

        Args:
            from_provider: Provider źródłowy
            to_provider: Provider docelowy
            reason_code: Kod przyczyny
            message: Komunikat
            technical_details: Szczegóły techniczne
        """
        event = FallbackEvent(
            timestamp=datetime.now(),
            from_provider=from_provider,
            to_provider=to_provider,
            reason_code=reason_code,
            message=message,
            technical_details=technical_details,
        )
        self.fallback_history.append(event)

        # Keep only last 100 events
        if len(self.fallback_history) > 100:
            self.fallback_history = self.fallback_history[-100:]

        logger.info(
            f"Fallback event: {from_provider} -> {to_provider} (reason: {reason_code.value})"
        )

    def get_governance_status(self) -> Dict[str, Any]:
        """
        Zwraca aktualny status governance.

        Returns:
            Dict ze statusem limitów, zużycia i fallbacków
        """
        return {
            "cost_limits": {
                scope: {
                    "soft_limit_usd": limit.soft_limit_usd,
                    "hard_limit_usd": limit.hard_limit_usd,
                    "current_usage_usd": limit.current_usage_usd,
                    "usage_percentage": (
                        limit.current_usage_usd / limit.hard_limit_usd * 100
                        if limit.hard_limit_usd > 0
                        else 0
                    ),
                }
                for scope, limit in self.cost_limits.items()
            },
            "rate_limits": {
                scope: {
                    "max_requests_per_minute": limit.max_requests_per_minute,
                    "max_tokens_per_minute": limit.max_tokens_per_minute,
                    "current_requests": limit.current_requests,
                    "current_tokens": limit.current_tokens,
                }
                for scope, limit in self.rate_limits.items()
            },
            "recent_fallbacks": [
                {
                    "timestamp": event.timestamp.isoformat(),
                    "from_provider": event.from_provider,
                    "to_provider": event.to_provider,
                    "reason_code": event.reason_code.value,
                    "message": event.message,
                }
                for event in self.fallback_history[-10:]  # Last 10 events
            ],
            "fallback_policy": {
                "preferred_provider": self.fallback_policy.preferred_provider,
                "fallback_order": self.fallback_policy.fallback_order,
            },
        }


# Global instance (singleton pattern)
_governance_instance: Optional[ProviderGovernance] = None
_governance_lock = threading.Lock()


def get_provider_governance() -> ProviderGovernance:
    """
    Zwraca globalną instancję ProviderGovernance (singleton).

    Returns:
        ProviderGovernance instance
    """
    global _governance_instance
    if _governance_instance is None:
        with _governance_lock:
            # Double-check locking pattern
            if _governance_instance is None:
                _governance_instance = ProviderGovernance()
    return _governance_instance
