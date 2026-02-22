"""Moduł: traffic_control - globalna kontrola ruchu API (zewnętrzne + wewnętrzne).

Ten moduł zapewnia:
1. Rate limiting (token bucket) dla API zewnętrznych i wewnętrznych
2. Circuit breaker dla ochrony przed degradacją providerów
3. Retry policy z exponential backoff i jitter
4. Telemetria i audyt ruchu
5. Ochrona przed zapętleniami
"""

from venom_core.infrastructure.traffic_control.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)
from venom_core.infrastructure.traffic_control.config import (
    CircuitBreakerConfig,
    InboundPolicyConfig,
    OutboundPolicyConfig,
    RetryPolicyConfig,
    TokenBucketConfig,
    TrafficControlConfig,
)
from venom_core.infrastructure.traffic_control.controller import (
    TrafficController,
    get_traffic_controller,
)
from venom_core.infrastructure.traffic_control.http_client import (
    TrafficControlledHttpClient,
)
from venom_core.infrastructure.traffic_control.retry_policy import (
    RetryPolicy,
    RetryResult,
)
from venom_core.infrastructure.traffic_control.token_bucket import TokenBucket

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
