"""Audit trail for admin actions on providers."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AuditEntry:
    """Single audit log entry for admin action."""

    timestamp: datetime
    action: str  # e.g., "provider_activate", "config_update", "test_connection"
    user: str  # user identifier (e.g., IP, username, "system")
    provider: Optional[str] = None  # affected provider if applicable
    details: Dict[str, Any] = field(default_factory=dict)  # action-specific details
    result: str = "success"  # success, failure, partial
    error_message: Optional[str] = None


class AdminAuditTrail:
    """
    Audit trail for admin actions.

    Thread-safe implementation with in-memory storage and optional persistence.
    """

    def __init__(self, max_entries: int = 1000):
        """
        Initialize audit trail.

        Args:
            max_entries: Maximum number of entries to keep in memory
        """
        self._entries: List[AuditEntry] = []
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def log_action(
        self,
        action: str,
        user: str,
        provider: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        result: str = "success",
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log an admin action.

        Args:
            action: Action identifier (e.g., "provider_activate")
            user: User identifier
            provider: Provider name if applicable
            details: Additional action details
            result: Action result (success, failure, partial)
            error_message: Error message if result is failure
        """
        entry = AuditEntry(
            timestamp=datetime.now(tz=timezone.utc),
            action=action,
            user=user,
            provider=provider,
            details=details or {},
            result=result,
            error_message=error_message,
        )

        with self._lock:
            self._entries.append(entry)
            # Trim if exceeds max
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]

        logger.info(
            f"Admin audit: {action} by {user} on provider={provider} -> {result}"
        )

    def get_entries(
        self,
        action: Optional[str] = None,
        provider: Optional[str] = None,
        user: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """
        Get audit entries with optional filtering.

        Args:
            action: Filter by action type
            provider: Filter by provider
            user: Filter by user
            limit: Maximum number of entries to return

        Returns:
            List of matching audit entries (newest first)
        """
        with self._lock:
            entries = list(reversed(self._entries))  # newest first

        # Apply filters
        if action:
            entries = [e for e in entries if e.action == action]
        if provider:
            entries = [e for e in entries if e.provider == provider]
        if user:
            entries = [e for e in entries if e.user == user]

        return entries[:limit]

    def get_recent_failures(
        self, provider: Optional[str] = None, limit: int = 10
    ) -> List[AuditEntry]:
        """
        Get recent failed actions.

        Args:
            provider: Optional provider filter
            limit: Maximum number of entries

        Returns:
            List of failed audit entries (newest first)
        """
        with self._lock:
            entries = [e for e in reversed(self._entries) if e.result == "failure"]

        if provider:
            entries = [e for e in entries if e.provider == provider]

        return entries[:limit]

    def clear(self) -> None:
        """Clear all audit entries (for testing)."""
        with self._lock:
            self._entries.clear()


# Global singleton instance
_audit_trail: Optional[AdminAuditTrail] = None
_audit_trail_lock = threading.Lock()


def get_audit_trail() -> AdminAuditTrail:
    """Get the global audit trail instance."""
    global _audit_trail
    if _audit_trail is None:
        with _audit_trail_lock:
            if _audit_trail is None:
                _audit_trail = AdminAuditTrail()
    return _audit_trail
