"""
Routing contract module for Venom AI system.

This module defines the formal contract for routing decisions, including:
- Runtime target enums
- Reason codes for routing decisions
- Routing decision dataclass
- KPI thresholds and limits

Related ADR: docs/adr/ADR-001-runtime-strategy-llm-first.md
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class RuntimeTarget(Enum):
    """Target runtime environment for AI workload execution."""
    
    LOCAL_OLLAMA = "ollama"
    LOCAL_VLLM = "vllm"
    CLOUD_OPENAI = "openai"
    CLOUD_GOOGLE = "google"
    CLOUD_AZURE = "azure"  # Future support
    
    def is_local(self) -> bool:
        """Check if runtime is local (privacy-preserving)."""
        return self in (RuntimeTarget.LOCAL_OLLAMA, RuntimeTarget.LOCAL_VLLM)
    
    def is_cloud(self) -> bool:
        """Check if runtime is cloud (paid, requires API key)."""
        return not self.is_local()


class ReasonCode(Enum):
    """Reason codes for routing decisions (observability and debugging)."""
    
    # Primary routing reasons
    DEFAULT_ECO_MODE = "default_eco_mode"
    TASK_COMPLEXITY_LOW = "task_complexity_low"
    TASK_COMPLEXITY_HIGH = "task_complexity_high"
    SENSITIVE_CONTENT_OVERRIDE = "sensitive_content_override"
    
    # Fallback reasons (from provider governance)
    FALLBACK_TIMEOUT = "fallback_timeout"
    FALLBACK_AUTH_ERROR = "fallback_auth_error"
    FALLBACK_BUDGET_EXCEEDED = "fallback_budget_exceeded"
    FALLBACK_PROVIDER_DEGRADED = "fallback_provider_degraded"
    FALLBACK_PROVIDER_OFFLINE = "fallback_provider_offline"
    FALLBACK_RATE_LIMIT = "fallback_rate_limit"
    
    # Policy blocks (from policy gate)
    POLICY_BLOCKED_BUDGET = "policy_blocked_budget"
    POLICY_BLOCKED_RATE_LIMIT = "policy_blocked_rate_limit"
    POLICY_BLOCKED_NO_PROVIDER = "policy_blocked_no_provider"
    POLICY_BLOCKED_CONTENT = "policy_blocked_content"
    
    # User override
    USER_PREFERENCE = "user_preference"


@dataclass
class RoutingDecision:
    """
    Formal contract for routing decision output.
    
    This dataclass represents the complete routing decision made by the system,
    including the target provider, reasoning, governance state, and observability data.
    
    Attributes:
        target_runtime: The selected runtime environment (local or cloud)
        provider: Provider name (ollama, vllm, openai, google)
        model: Specific model name/identifier
        reason_code: Primary reason for this routing decision
        complexity_score: Task complexity score (0-10)
        is_sensitive: Whether task contains sensitive data
        fallback_applied: Whether fallback to alternate provider occurred
        fallback_chain: List of providers attempted before success
        policy_gate_passed: Whether policy gate approved this decision
        estimated_cost_usd: Estimated cost for this request (0 for local)
        budget_remaining_usd: Remaining budget after this request (None if eco mode)
        decision_timestamp: ISO 8601 timestamp of decision
        decision_latency_ms: Time taken to make routing decision
        error_message: Optional error message if decision failed
    """
    
    # Primary decision
    target_runtime: Optional[RuntimeTarget]
    provider: Optional[str]
    model: Optional[str]
    
    # Decision metadata
    reason_code: ReasonCode
    complexity_score: float = 0.0
    is_sensitive: bool = False
    
    # Governance state
    fallback_applied: bool = False
    fallback_chain: List[str] = field(default_factory=list)
    policy_gate_passed: bool = True
    
    # Cost/budget tracking
    estimated_cost_usd: float = 0.0
    budget_remaining_usd: Optional[float] = None
    
    # Observability
    decision_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    decision_latency_ms: float = 0.0
    
    # Error handling
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert routing decision to dictionary for serialization."""
        return {
            "target_runtime": self.target_runtime.value if self.target_runtime else None,
            "provider": self.provider,
            "model": self.model,
            "reason_code": self.reason_code.value,
            "complexity_score": self.complexity_score,
            "is_sensitive": self.is_sensitive,
            "fallback_applied": self.fallback_applied,
            "fallback_chain": self.fallback_chain,
            "policy_gate_passed": self.policy_gate_passed,
            "estimated_cost_usd": self.estimated_cost_usd,
            "budget_remaining_usd": self.budget_remaining_usd,
            "decision_timestamp": self.decision_timestamp,
            "decision_latency_ms": self.decision_latency_ms,
            "error_message": self.error_message,
        }
    
    def is_successful(self) -> bool:
        """Check if routing decision resulted in a usable provider."""
        return (
            self.target_runtime is not None 
            and self.provider is not None 
            and self.policy_gate_passed
            and self.error_message is None
        )
    
    def is_cost_free(self) -> bool:
        """Check if this routing decision incurs no cost."""
        # Local runtimes are always cost-free
        if self.target_runtime is not None and self.target_runtime.is_local():
            return True
        # For cloud runtimes, check if cost is negligible (< $0.0001)
        return abs(self.estimated_cost_usd) < 1e-4


class RoutingKPIs:
    """Key Performance Indicators and thresholds for routing decisions."""
    
    # Cost KPIs
    DAILY_COST_ECO_TARGET_USD = 0.0
    DAILY_COST_PAID_TARGET_USD = 5.0
    DAILY_COST_SOFT_LIMIT_USD = 10.0
    DAILY_COST_HARD_LIMIT_USD = 50.0
    COST_PER_REQUEST_TARGET_USD = 0.01
    COST_PER_REQUEST_ALERT_USD = 0.05
    CLOUD_USAGE_RATIO_TARGET = 0.2  # 20% of requests
    CLOUD_USAGE_RATIO_ALERT = 0.5   # 50% of requests
    
    # Latency KPIs (in seconds)
    ROUTING_DECISION_TARGET_MS = 100
    ROUTING_DECISION_ALERT_MS = 200
    LOCAL_INFERENCE_P50_TARGET_S = 1.5
    LOCAL_INFERENCE_P95_TARGET_S = 3.0
    LOCAL_INFERENCE_ALERT_S = 5.0
    CLOUD_INFERENCE_P95_TARGET_S = 2.0
    CLOUD_INFERENCE_ALERT_S = 4.0
    TOTAL_REQUEST_P99_TARGET_S = 5.0
    TOTAL_REQUEST_ALERT_S = 10.0
    
    # Quality KPIs (as percentages)
    TASK_SUCCESS_RATE_TARGET = 0.95  # 95%
    TASK_SUCCESS_RATE_ALERT = 0.90   # 90%
    STRUCTURED_OUTPUT_VALIDITY_TARGET = 0.98  # 98%
    STRUCTURED_OUTPUT_VALIDITY_ALERT = 0.95   # 95%
    FALLBACK_SUCCESS_RATE_TARGET = 0.90  # 90%
    FALLBACK_SUCCESS_RATE_ALERT = 0.80   # 80%
    SENSITIVE_DATA_LEAK_RATE = 0.0  # Zero tolerance
    
    # Reliability KPIs (as percentages)
    PROVIDER_AVAILABILITY_LOCAL_TARGET = 0.99   # 99%
    PROVIDER_AVAILABILITY_LOCAL_ALERT = 0.95    # 95%
    PROVIDER_AVAILABILITY_CLOUD_TARGET = 0.999  # 99.9%
    PROVIDER_AVAILABILITY_CLOUD_ALERT = 0.99    # 99%
    FALLBACK_CHAIN_EXHAUSTION_TARGET = 0.01  # 1%
    FALLBACK_CHAIN_EXHAUSTION_ALERT = 0.05   # 5%


class ComplexityThresholds:
    """Thresholds for task complexity scoring and routing."""
    
    # Complexity score ranges (0-10)
    LOW_COMPLEXITY_MAX = 5
    HIGH_COMPLEXITY_MIN = 6
    
    # Complexity scoring weights
    CHARS_PER_POINT = 500  # +1 point per 500 characters
    CODE_BLOCK_BONUS = 2   # +2 points if prompt contains code
    STRUCTURED_OUTPUT_BONUS = 1  # +1 point if structured output required
    
    # Task type base complexity scores
    TASK_COMPLEXITY_BASE = {
        "STANDARD": 2,
        "CHAT": 3,
        "CODING_SIMPLE": 4,
        "CODING_COMPLEX": 7,
        "ANALYSIS": 6,
        "GENERATION": 5,
        "RESEARCH": 7,
        "SENSITIVE": 0,  # Always local, complexity irrelevant
    }


class FallbackPolicy:
    """Fallback policy configuration for provider selection."""
    
    # Default fallback order (preferred → fallback → last resort)
    DEFAULT_FALLBACK_ORDER = ["ollama", "vllm", "openai", "google"]
    
    # Eco mode fallback order (local only)
    ECO_MODE_FALLBACK_ORDER = ["ollama", "vllm"]
    
    # Paid mode - low complexity (prefer local for cost savings)
    PAID_LOW_COMPLEXITY_FALLBACK = ["ollama", "vllm"]
    
    # Paid mode - high complexity (cloud preferred for quality)
    PAID_HIGH_COMPLEXITY_FALLBACK = ["openai", "google", "ollama", "vllm"]
    
    # Sensitive content (local only, never cloud)
    SENSITIVE_CONTENT_FALLBACK = ["ollama", "vllm"]
    
    # Fallback behavior flags
    ENABLE_TIMEOUT_FALLBACK = True
    ENABLE_AUTH_FALLBACK = True
    ENABLE_BUDGET_FALLBACK = True
    ENABLE_DEGRADED_FALLBACK = True
    TIMEOUT_THRESHOLD_SECONDS = 30.0
    
    @classmethod
    def get_fallback_order(
        cls, 
        is_eco_mode: bool,
        is_sensitive: bool,
        complexity_score: float
    ) -> List[str]:
        """
        Get appropriate fallback order based on mode and task characteristics.
        
        Args:
            is_eco_mode: Whether system is in eco (local-only) mode
            is_sensitive: Whether task contains sensitive data
            complexity_score: Task complexity score (0-10)
        
        Returns:
            List of provider names in fallback order
        """
        if is_sensitive:
            return cls.SENSITIVE_CONTENT_FALLBACK
        
        if is_eco_mode:
            return cls.ECO_MODE_FALLBACK_ORDER
        
        if complexity_score < ComplexityThresholds.HIGH_COMPLEXITY_MIN:
            return cls.PAID_LOW_COMPLEXITY_FALLBACK
        else:
            return cls.PAID_HIGH_COMPLEXITY_FALLBACK
