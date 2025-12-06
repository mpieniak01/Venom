"""Moduł: stream - WebSocket server i EventBroadcaster dla real-time telemetry."""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class EventType:
    """Typy zdarzeń w systemie telemetrii."""

    # Zdarzenia agentów
    AGENT_ACTION = "AGENT_ACTION"
    AGENT_THOUGHT = "AGENT_THOUGHT"
    AGENT_ERROR = "AGENT_ERROR"

    # Zdarzenia Architekta
    PLAN_CREATED = "PLAN_CREATED"
    PLAN_STEP_STARTED = "PLAN_STEP_STARTED"
    PLAN_STEP_COMPLETED = "PLAN_STEP_COMPLETED"

    # Zdarzenia narzędzi
    TOOL_USAGE = "TOOL_USAGE"
    FILE_CHANGE = "FILE_CHANGE"
    WEB_BROWSING = "WEB_BROWSING"

    # Zdarzenia zadań
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"

    # Logi systemowe
    SYSTEM_LOG = "SYSTEM_LOG"


class Event(BaseModel):
    """Model zdarzenia WebSocket."""

    type: str
    agent: Optional[str] = None
    message: str
    timestamp: str
    data: Optional[Dict[str, Any]] = None


class ConnectionManager:
    """Zarządza połączeniami WebSocket."""

    def __init__(self):
        """Inicjalizacja managera połączeń."""
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """
        Akceptuje nowe połączenie WebSocket.

        Args:
            websocket: Połączenie WebSocket do dodania
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(
            f"Nowe połączenie WebSocket. Aktywne połączenia: {len(self.active_connections)}"
        )

    async def disconnect(self, websocket: WebSocket):
        """
        Usuwa połączenie WebSocket.

        Args:
            websocket: Połączenie WebSocket do usunięcia
        """
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(
            f"Zamknięto połączenie WebSocket. Aktywne połączenia: {len(self.active_connections)}"
        )

    async def broadcast(self, event: Event):
        """
        Wysyła zdarzenie do wszystkich podłączonych klientów.

        Args:
            event: Zdarzenie do wysłania
        """
        if not self.active_connections:
            return

        message = event.model_dump_json()
        disconnected = []

        async with self._lock:
            connections = self.active_connections.copy()

        for connection in connections:
            try:
                await connection.send_text(message)
            except WebSocketDisconnect:
                disconnected.append(connection)
            except Exception as e:
                logger.error(f"Błąd podczas wysyłania do WebSocket: {e}")
                disconnected.append(connection)

        # Usuń nieaktywne połączenia
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)


class EventBroadcaster:
    """Broadcaster zdarzeń do klientów WebSocket."""

    def __init__(self, connection_manager: ConnectionManager):
        """
        Inicjalizacja broadcastera.

        Args:
            connection_manager: Manager połączeń WebSocket
        """
        self.connection_manager = connection_manager

    async def broadcast_event(
        self,
        event_type: str,
        message: str,
        agent: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        """
        Wysyła zdarzenie do wszystkich podłączonych klientów.

        Args:
            event_type: Typ zdarzenia (z EventType)
            message: Treść wiadomości
            agent: Opcjonalnie nazwa agenta
            data: Opcjonalne dodatkowe dane
        """
        event = Event(
            type=event_type,
            agent=agent,
            message=message,
            timestamp=datetime.now().isoformat(),
            data=data,
        )

        await self.connection_manager.broadcast(event)
        logger.debug(f"Broadcast: [{event_type}] {message}")

    async def broadcast_log(self, level: str, message: str):
        """
        Wysyła log systemowy do klientów.

        Args:
            level: Poziom loga (INFO, WARNING, ERROR)
            message: Treść loga
        """
        await self.broadcast_event(
            event_type=EventType.SYSTEM_LOG,
            message=message,
            data={"level": level},
        )


# Globalna instancja (będzie inicjalizowana w main.py)
connection_manager = ConnectionManager()
event_broadcaster = EventBroadcaster(connection_manager)
