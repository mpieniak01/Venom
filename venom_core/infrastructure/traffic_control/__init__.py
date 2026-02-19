"""Moduł: traffic_control - globalna kontrola ruchu API (zewnętrzne + wewnętrzne).

Ten moduł zapewnia:
1. Rate limiting (token bucket) dla API zewnętrznych i wewnętrznych
2. Circuit breaker dla ochrony przed degradacją providerów
3. Retry policy z exponential backoff i jitter
4. Telemetria i audyt ruchu
5. Ochrona przed zapętleniami
"""

from .circuit_breaker import CircuitBreaker, CircuitState
from .config import (
    CircuitBreakerConfig,
    InboundPolicyConfig,
    OutboundPolicyConfig,
    RetryPolicyConfig,
    TokenBucketConfig,
    TrafficControlConfig,
)
from .controller import TrafficController, get_traffic_controller
from .http_client import TrafficControlledHttpClient
from .retry_policy import RetryPolicy, RetryResult
from .token_bucket import TokenBucket

__all__ = [
    # Core components
    "TokenBucket",
    "CircuitBreaker",
    "CircuitState",
    "RetryPolicy",
    "RetryResult",
    "TrafficController",
    "TrafficControlledHttpClient",
    # Configuration
    "TokenBucketConfig",
    "CircuitBreakerConfig",
    "RetryPolicyConfig",
    "OutboundPolicyConfig",
    "InboundPolicyConfig",
    "TrafficControlConfig",
    # Factory
    "get_traffic_controller",
]
