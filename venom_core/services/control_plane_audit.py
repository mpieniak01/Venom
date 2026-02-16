"""Audit trail service for Workflow Control Plane operations.

This module tracks all control plane operations for compliance and debugging.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional

from venom_core.api.schemas.workflow_control import ReasonCode, ResourceType
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ControlPlaneAuditEntry:
    """Audit entry for a control plane operation."""

    operation_id: str
    timestamp: datetime
    triggered_by: str
    operation_type: str  # plan, apply, workflow_operation, etc.
    resource_type: ResourceType
    resource_id: str
    params: dict[str, Any]
    result: str  # success, failure, cancelled
    reason_code: ReasonCode
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None


class ControlPlaneAuditTrail:
    """Thread-safe audit trail for control plane operations."""

    def __init__(self, max_entries: int = 1000):
        """Initialize audit trail.

        Args:
            max_entries: Maximum number of entries to keep in memory
        """
        self._entries: list[ControlPlaneAuditEntry] = []
        self._lock = Lock()
        self._max_entries = max_entries

    def log_operation(
        self,
        triggered_by: str,
        operation_type: str,
        resource_type: ResourceType,
        resource_id: str,
        params: dict[str, Any],
        result: str,
        reason_code: ReasonCode,
        duration_ms: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> str:
        """Log a control plane operation.

        Args:
            triggered_by: User or system that triggered the operation
            operation_type: Type of operation (plan, apply, etc.)
            resource_type: Type of resource affected
            resource_id: ID of the resource
            params: Operation parameters
            result: Operation result (success, failure, cancelled)
            reason_code: Reason code for the result
            duration_ms: Operation duration in milliseconds
            error_message: Error message if operation failed

        Returns:
            operation_id: Unique ID for this operation
        """
        operation_id = str(uuid.uuid4())

        entry = ControlPlaneAuditEntry(
            operation_id=operation_id,
            timestamp=datetime.now(timezone.utc),
            triggered_by=triggered_by,
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
            params=params,
            result=result,
            reason_code=reason_code,
            duration_ms=duration_ms,
            error_message=error_message,
        )

        with self._lock:
            self._entries.append(entry)
            # Keep only the most recent entries
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]

        logger.info(
            "Control plane operation logged",
            extra={
                "operation_id": operation_id,
                "operation_type": operation_type,
                "resource_type": resource_type.value,
                "resource_id": resource_id,
                "result": result,
                "reason_code": reason_code.value,
            },
        )

        return operation_id

    def get_entries(
        self,
        operation_type: Optional[str] = None,
        resource_type: Optional[ResourceType] = None,
        triggered_by: Optional[str] = None,
        result: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[ControlPlaneAuditEntry]:
        """Get audit entries with optional filtering.

        Args:
            operation_type: Filter by operation type
            resource_type: Filter by resource type
            triggered_by: Filter by user
            result: Filter by result (success, failure, cancelled)
            limit: Maximum number of entries to return

        Returns:
            List of matching audit entries
        """
        with self._lock:
            entries = list(self._entries)

        # Apply filters
        if operation_type:
            entries = [e for e in entries if e.operation_type == operation_type]
        if resource_type:
            entries = [e for e in entries if e.resource_type == resource_type]
        if triggered_by:
            entries = [e for e in entries if e.triggered_by == triggered_by]
        if result:
            entries = [e for e in entries if e.result == result]

        # Sort by timestamp descending (most recent first)
        entries.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply limit
        if limit:
            entries = entries[:limit]

        return entries

    def get_recent_failures(self, limit: int = 10) -> list[ControlPlaneAuditEntry]:
        """Get recent failed operations.

        Args:
            limit: Maximum number of failures to return

        Returns:
            List of recent failed operations
        """
        return self.get_entries(result="failure", limit=limit)

    def get_operation(self, operation_id: str) -> Optional[ControlPlaneAuditEntry]:
        """Get a specific operation by ID.

        Args:
            operation_id: Operation ID to find

        Returns:
            Audit entry if found, None otherwise
        """
        with self._lock:
            for entry in reversed(self._entries):
                if entry.operation_id == operation_id:
                    return entry
        return None

    def clear_old_entries(self, days: int = 30):
        """Clear audit entries older than specified days.

        Args:
            days: Keep entries from last N days
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with self._lock:
            self._entries = [e for e in self._entries if e.timestamp >= cutoff]

        logger.info(
            f"Cleared audit entries older than {days} days",
            extra={"remaining_entries": len(self._entries)},
        )


# Singleton instance
_audit_trail: ControlPlaneAuditTrail | None = None


def get_control_plane_audit_trail() -> ControlPlaneAuditTrail:
    """Get singleton audit trail instance.

    Returns:
        ControlPlaneAuditTrail instance
    """
    global _audit_trail
    if _audit_trail is None:
        _audit_trail = ControlPlaneAuditTrail()
    return _audit_trail
