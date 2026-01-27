"""Moduł: event_broadcaster - cienki adapter do broadcastu zdarzeń."""

from __future__ import annotations

from typing import Any, Optional

from venom_core.core.flows.base import EventBroadcaster


class EventBroadcasterClient:
    """Adapter umożliwiający bezpieczne broadcastowanie zdarzeń."""

    def __init__(self, broadcaster: Optional[EventBroadcaster]):
        self._broadcaster = broadcaster

    async def broadcast(
        self,
        event_type: str,
        message: str,
        agent: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        if self._broadcaster:
            await self._broadcaster.broadcast_event(
                event_type=event_type, message=message, agent=agent, data=data
            )
