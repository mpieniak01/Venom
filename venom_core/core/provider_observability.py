"""Moduł: provider_observability - SLO tracking, health scoring, i alerting dla providerów."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class HealthStatus(str, Enum):
    """Status zdrowia providera."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    """Poziom ważności alertu."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Typ alertu."""

    HIGH_LATENCY = "HIGH_LATENCY"
    ERROR_SPIKE = "ERROR_SPIKE"
    BUDGET_WARNING = "BUDGET_WARNING"
    BUDGET_CRITICAL = "BUDGET_CRITICAL"
    AVAILABILITY_DROP = "AVAILABILITY_DROP"
    SLO_BREACH = "SLO_BREACH"


@dataclass
class SLOTarget:
    """Definicja SLO dla providera."""

    provider: str
    availability_target: float = 0.99  # 99% availability
    latency_p99_ms: float = 1000.0  # p99 < 1000ms
    error_rate_target: float = 0.01  # < 1% error rate
    cost_budget_usd: float = 50.0  # Monthly budget
    period_start: datetime = field(default_factory=datetime.now)


@dataclass
class SLOStatus:
    """Aktualny status SLO providera."""

    provider: str
    availability: float  # Current availability %
    latency_p99_ms: Optional[float]  # Current p99 latency
    error_rate: float  # Current error rate %
    cost_usage_usd: float  # Current cost usage
    slo_target: SLOTarget
    breaches: List[str] = field(default_factory=list)  # List of SLO breaches
    health_score: float = 100.0  # 0-100 health score
    health_status: HealthStatus = HealthStatus.HEALTHY


@dataclass
class Alert:
    """Alert dla providera."""

    id: str  # Unique alert ID
    severity: AlertSeverity
    alert_type: AlertType
    provider: str
    message: str  # Human-readable message (i18n key)
    technical_details: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    fingerprint: str = ""  # For deduplication
    expires_at: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)  # Additional context

    def __post_init__(self):
        """Generate fingerprint and expiry after init."""
        if not self.fingerprint:
            # Generate fingerprint based on provider, alert_type, and hour
            hour_key = self.timestamp.strftime("%Y%m%d%H")
            fp_str = f"{self.provider}:{self.alert_type.value}:{hour_key}"
            # Plain deterministic key is enough for alert deduplication and avoids
            # cryptographic-hash security hotspots.
            self.fingerprint = fp_str

        if not self.expires_at:
            # Default expiry: 1 hour for info, 3 hours for warning, 6 hours for critical
            hours = {"info": 1, "warning": 3, "critical": 6}[self.severity.value]
            self.expires_at = self.timestamp + timedelta(hours=hours)


class ProviderObservability:
    """
    Manager dla observability providerów: SLO tracking, health scoring, alerting.

    Integruje się z MetricsCollector i ProviderGovernance.
    """

    def __init__(self):
        """Inicjalizacja observability managera."""
        self.slo_targets: Dict[str, SLOTarget] = {}
        self.active_alerts: Dict[str, Alert] = {}  # fingerprint -> Alert
        self.alert_history: List[Alert] = []  # Last 100 alerts
        # Reentrant lock prevents self-deadlocks when helper methods call each other
        # under synchronization (e.g. get_alert_summary -> get_active_alerts).
        self._lock = threading.RLock()

        # Initialize default SLO targets for common providers
        self._init_default_slo_targets()

        logger.info("ProviderObservability initialized")

    def _init_default_slo_targets(self) -> None:
        """Inicjalizuj domyślne SLO targets dla providerów."""
        # Cloud providers - stricter SLO
        for provider in ["openai", "google"]:
            self.slo_targets[provider] = SLOTarget(
                provider=provider,
                availability_target=0.99,
                latency_p99_ms=2000.0,
                error_rate_target=0.01,
                cost_budget_usd=50.0,
            )

        # Local runtimes - more relaxed SLO
        for provider in ["ollama", "vllm"]:
            self.slo_targets[provider] = SLOTarget(
                provider=provider,
                availability_target=0.95,
                latency_p99_ms=3000.0,
                error_rate_target=0.05,
                cost_budget_usd=0.0,  # No cost for local
            )

        # Catalog integrators
        self.slo_targets["huggingface"] = SLOTarget(
            provider="huggingface",
            availability_target=0.98,
            latency_p99_ms=5000.0,  # Search can be slower
            error_rate_target=0.02,
            cost_budget_usd=0.0,
        )

    def set_slo_target(self, provider: str, target: SLOTarget) -> None:
        """
        Ustaw SLO target dla providera.

        Args:
            provider: Nazwa providera
            target: SLO target
        """
        with self._lock:
            self.slo_targets[provider] = target
            logger.info(f"SLO target set for {provider}")

    def calculate_slo_status(
        self, provider: str, provider_metrics: Optional[Dict]
    ) -> SLOStatus:
        """
        Oblicza aktualny status SLO providera.

        Args:
            provider: Nazwa providera
            provider_metrics: Metryki providera z MetricsCollector

        Returns:
            SLOStatus z obliczonym health score i statusem
        """
        with self._lock:
            target = self.slo_targets.get(provider, SLOTarget(provider=provider))

            if not provider_metrics:
                return SLOStatus(
                    provider=provider,
                    availability=0.0,
                    latency_p99_ms=None,
                    error_rate=0.0,
                    cost_usage_usd=0.0,
                    slo_target=target,
                    breaches=[],
                    health_score=0.0,
                    health_status=HealthStatus.UNKNOWN,
                )

            # Extract current metrics
            availability = provider_metrics.get("success_rate", 0.0) / 100.0
            latency_p99 = provider_metrics.get("latency", {}).get("p99_ms")
            error_rate = provider_metrics.get("error_rate", 0.0) / 100.0
            cost_usage = provider_metrics.get("cost", {}).get("total_usd", 0.0)

            # Check for SLO breaches
            breaches = []
            health_score = 100.0

            # Availability check
            if availability < target.availability_target:
                breach = f"availability_{availability * 100:.1f}%_below_{target.availability_target * 100:.1f}%"
                breaches.append(breach)
                health_score -= 30.0

            # Latency check
            if latency_p99 and latency_p99 > target.latency_p99_ms:
                breach = f"latency_p99_{latency_p99:.0f}ms_above_{target.latency_p99_ms:.0f}ms"
                breaches.append(breach)
                health_score -= 25.0

            # Error rate check
            if error_rate > target.error_rate_target:
                breach = f"error_rate_{error_rate * 100:.1f}%_above_{target.error_rate_target * 100:.1f}%"
                breaches.append(breach)
                health_score -= 25.0

            # Cost check
            if target.cost_budget_usd > 0 and cost_usage > target.cost_budget_usd:
                breach = f"cost_${cost_usage:.2f}_above_${target.cost_budget_usd:.2f}"
                breaches.append(breach)
                health_score -= 20.0

            # Determine health status
            health_score = max(0.0, health_score)
            if health_score >= 80:
                health_status = HealthStatus.HEALTHY
            elif health_score >= 50:
                health_status = HealthStatus.DEGRADED
            else:
                health_status = HealthStatus.CRITICAL

            return SLOStatus(
                provider=provider,
                availability=availability,
                latency_p99_ms=latency_p99,
                error_rate=error_rate,
                cost_usage_usd=cost_usage,
                slo_target=target,
                breaches=breaches,
                health_score=health_score,
                health_status=health_status,
            )

    def emit_alert(self, alert: Alert) -> bool:
        """
        Emituje alert z deduplication.

        Args:
            alert: Alert do wyemitowania

        Returns:
            True jeśli alert został dodany, False jeśli zdeduplikowany
        """
        with self._lock:
            # Check if alert with same fingerprint exists and is not expired
            existing = self.active_alerts.get(alert.fingerprint)
            if (
                existing
                and existing.expires_at
                and existing.expires_at > datetime.now()
            ):
                logger.debug(
                    f"Alert deduplicated: {alert.alert_type.value} for {alert.provider}"
                )
                return False

            # Add/update alert
            self.active_alerts[alert.fingerprint] = alert
            self.alert_history.append(alert)

            # Keep only last 100 alerts in history
            if len(self.alert_history) > 100:
                self.alert_history = self.alert_history[-100:]

            logger.warning(
                f"Alert emitted: {alert.severity.value} - {alert.alert_type.value} for {alert.provider}"
            )
            return True

    def check_and_emit_alerts(
        self, provider: str, slo_status: SLOStatus, provider_metrics: Dict
    ) -> List[Alert]:
        """
        Sprawdza warunki i emituje alerty dla providera.

        Args:
            provider: Nazwa providera
            slo_status: Aktualny status SLO
        Returns:
            Lista wyemitowanych alertów
        """
        if provider_metrics:
            logger.debug(
                f"Alert evaluation for {provider} with metrics: {', '.join(sorted(provider_metrics.keys()))}"
            )
        emitted_alerts: List[Alert] = []
        candidate_alerts = [
            self._build_high_latency_alert(provider, slo_status),
            self._build_error_spike_alert(provider, slo_status),
            self._build_budget_alert(provider, slo_status),
            self._build_availability_alert(provider, slo_status),
            self._build_slo_breach_alert(provider, slo_status),
        ]
        for alert in candidate_alerts:
            if alert and self.emit_alert(alert):
                emitted_alerts.append(alert)
        return emitted_alerts

    def _build_high_latency_alert(
        self, provider: str, slo_status: SLOStatus
    ) -> Optional[Alert]:
        latency_p99_ms = slo_status.latency_p99_ms
        if latency_p99_ms is None or not math.isfinite(latency_p99_ms):
            return None
        if latency_p99_ms <= slo_status.slo_target.latency_p99_ms:
            return None
        return Alert(
            id=f"{provider}_latency_{datetime.now().timestamp()}",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.HIGH_LATENCY,
            provider=provider,
            message="providers.alerts.highLatency",
            technical_details=(
                f"p99={latency_p99_ms:.0f}ms "
                f"threshold={slo_status.slo_target.latency_p99_ms:.0f}ms"
            ),
            metadata={
                "latency": latency_p99_ms,
                "threshold": slo_status.slo_target.latency_p99_ms,
            },
        )

    def _build_error_spike_alert(
        self, provider: str, slo_status: SLOStatus
    ) -> Optional[Alert]:
        if slo_status.error_rate <= slo_status.slo_target.error_rate_target:
            return None
        critical_threshold = slo_status.slo_target.error_rate_target * 2
        severity = (
            AlertSeverity.CRITICAL
            if slo_status.error_rate > critical_threshold
            else AlertSeverity.WARNING
        )
        return Alert(
            id=f"{provider}_error_{datetime.now().timestamp()}",
            severity=severity,
            alert_type=AlertType.ERROR_SPIKE,
            provider=provider,
            message="providers.alerts.errorSpike",
            technical_details=(
                f"error_rate={slo_status.error_rate * 100:.1f}% "
                f"threshold={slo_status.slo_target.error_rate_target * 100:.1f}%"
            ),
            metadata={
                "rate": slo_status.error_rate * 100,
                "threshold": slo_status.slo_target.error_rate_target * 100,
            },
        )

    def _build_budget_alert(
        self, provider: str, slo_status: SLOStatus
    ) -> Optional[Alert]:
        if slo_status.slo_target.cost_budget_usd <= 0:
            return None
        budget_usage_pct = (
            slo_status.cost_usage_usd / slo_status.slo_target.cost_budget_usd * 100
        )
        if budget_usage_pct <= 80:
            return None
        is_critical = budget_usage_pct > 100
        severity = AlertSeverity.CRITICAL if is_critical else AlertSeverity.WARNING
        alert_type = (
            AlertType.BUDGET_CRITICAL if is_critical else AlertType.BUDGET_WARNING
        )
        return Alert(
            id=f"{provider}_budget_{datetime.now().timestamp()}",
            severity=severity,
            alert_type=alert_type,
            provider=provider,
            message="providers.alerts.budgetWarning",
            technical_details=(
                f"cost=${slo_status.cost_usage_usd:.2f} "
                f"budget=${slo_status.slo_target.cost_budget_usd:.2f}"
            ),
            metadata={
                "current": slo_status.cost_usage_usd,
                "limit": slo_status.slo_target.cost_budget_usd,
            },
        )

    def _build_availability_alert(
        self, provider: str, slo_status: SLOStatus
    ) -> Optional[Alert]:
        if slo_status.availability >= slo_status.slo_target.availability_target:
            return None
        return Alert(
            id=f"{provider}_availability_{datetime.now().timestamp()}",
            severity=AlertSeverity.CRITICAL,
            alert_type=AlertType.AVAILABILITY_DROP,
            provider=provider,
            message="providers.alerts.availabilityDrop",
            technical_details=(
                f"availability={slo_status.availability * 100:.1f}% "
                f"target={slo_status.slo_target.availability_target * 100:.1f}%"
            ),
            metadata={
                "availability": slo_status.availability * 100,
                "target": slo_status.slo_target.availability_target * 100,
            },
        )

    def _build_slo_breach_alert(
        self, provider: str, slo_status: SLOStatus
    ) -> Optional[Alert]:
        if not slo_status.breaches:
            return None
        return Alert(
            id=f"{provider}_slo_{datetime.now().timestamp()}",
            severity=AlertSeverity.WARNING,
            alert_type=AlertType.SLO_BREACH,
            provider=provider,
            message="providers.alerts.sloBreached",
            technical_details=f"breaches: {', '.join(slo_status.breaches)}",
            metadata={
                "metric": ", ".join(slo_status.breaches),
                "breaches": slo_status.breaches,
            },
        )

    def get_active_alerts(self, provider: Optional[str] = None) -> List[Alert]:
        """
        Zwraca aktywne (nie wygasłe) alerty.

        Args:
            provider: Opcjonalnie filtruj po providerze

        Returns:
            Lista aktywnych alertów
        """
        with self._lock:
            now = datetime.now()
            active = []

            # Clean up expired alerts
            expired_fingerprints = []
            for fingerprint, alert in self.active_alerts.items():
                if alert.expires_at and alert.expires_at <= now:
                    expired_fingerprints.append(fingerprint)
                elif provider is None or alert.provider == provider:
                    active.append(alert)

            # Remove expired
            for fp in expired_fingerprints:
                del self.active_alerts[fp]

            return sorted(active, key=lambda a: a.timestamp, reverse=True)

    def get_alert_summary(self) -> Dict[str, Any]:
        """
        Zwraca podsumowanie alertów.

        Returns:
            Dict z licznikami alertów per severity i provider
        """
        with self._lock:
            active = self.get_active_alerts()

            by_severity: Dict[str, int] = {
                "info": 0,
                "warning": 0,
                "critical": 0,
            }
            by_provider: Dict[str, int] = {}
            summary: Dict[str, Any] = {
                "total_active": len(active),
                "by_severity": by_severity,
                "by_provider": by_provider,
            }

            for alert in active:
                summary["by_severity"][alert.severity.value] += 1

                if alert.provider not in summary["by_provider"]:
                    summary["by_provider"][alert.provider] = 0
                summary["by_provider"][alert.provider] += 1

            return summary


# Global instance (singleton pattern)
_observability_instance: Optional[ProviderObservability] = None
_observability_lock = threading.Lock()


def get_provider_observability() -> ProviderObservability:
    """
    Zwraca globalną instancję ProviderObservability (singleton).

    Returns:
        ProviderObservability instance
    """
    global _observability_instance
    if _observability_instance is None:
        with _observability_lock:
            # Double-check locking pattern
            if _observability_instance is None:
                _observability_instance = ProviderObservability()
    return _observability_instance
