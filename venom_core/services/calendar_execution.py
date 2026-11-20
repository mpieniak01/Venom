"""Request-scoped evidence for an explicitly executed calendar insertion."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class CalendarCreate:
    request_id: UUID
    title: str
    start_time: str
    duration_minutes: int
    description: str = ""


@dataclass(frozen=True)
class CalendarReceipt:
    request: CalendarCreate
    event_id: str
    event_link: str | None
    status: str = "success"

    def confirms(self, current: CalendarCreate) -> bool:
        return (
            self.status == "success"
            and bool(self.event_id.strip())
            and self.request == current
        )


@dataclass(frozen=True)
class CalendarExecution:
    message: str
    receipt: CalendarReceipt | None = None

    def confirmed(self, current: CalendarCreate) -> CalendarReceipt | None:
        if self.receipt is not None and self.receipt.confirms(current):
            return self.receipt
        return None


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def _matches_event(operation: CalendarCreate, event: dict[str, Any]) -> bool:
    try:
        start = _utc(operation.start_time)
        return (
            event.get("summary") == operation.title
            and event.get("description", "") == operation.description
            and _utc(event["start"]["dateTime"]) == start
            and _utc(event["end"]["dateTime"])
            == start + timedelta(minutes=operation.duration_minutes)
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def confirm_insertion(
    operation: CalendarCreate, event: object
) -> CalendarReceipt | None:
    """Bind an actual provider result to the parameters passed to its executor."""
    if not isinstance(event, dict) or event.get("status") == "cancelled":
        return None
    event_id = event.get("id")
    if not (
        isinstance(event_id, str)
        and event_id.strip()
        and _matches_event(operation, event)
    ):
        return None
    link = event.get("htmlLink")
    return CalendarReceipt(operation, event_id, link if isinstance(link, str) else None)
