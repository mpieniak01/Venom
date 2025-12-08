"""Moduł: protocol - Protokół komunikacji roju (WebSocket)."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Typy wiadomości w protokole roju."""

    HANDSHAKE = "HANDSHAKE"  # Rejestracja węzła
    EXECUTE_SKILL = "EXECUTE_SKILL"  # Zlecenie wykonania skilla
    HEARTBEAT = "HEARTBEAT"  # Monitorowanie statusu
    RESPONSE = "RESPONSE"  # Odpowiedź na wykonanie
    DISCONNECT = "DISCONNECT"  # Rozłączenie węzła
    ERROR = "ERROR"  # Błąd w komunikacji


class Capabilities(BaseModel):
    """Możliwości węzła (capabilities)."""

    skills: List[str] = Field(
        default_factory=list, description="Lista dostępnych skill'ów"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tagi opisujące węzeł (np. location:server_room, gpu, camera)",
    )
    cpu_cores: int = Field(default=1, description="Liczba rdzeni CPU")
    memory_mb: int = Field(default=1024, description="Dostępna pamięć RAM w MB")
    has_gpu: bool = Field(default=False, description="Czy węzeł ma GPU")
    has_docker: bool = Field(default=False, description="Czy węzeł ma Docker")
    platform: str = Field(default="linux", description="System operacyjny")


class NodeHandshake(BaseModel):
    """Wiadomość rejestracji węzła."""

    message_type: MessageType = MessageType.HANDSHAKE
    node_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unikalny ID węzła"
    )
    node_name: str = Field(description="Nazwa węzła")
    capabilities: Capabilities = Field(description="Możliwości węzła")
    token: str = Field(description="Token autoryzacyjny")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="Timestamp"
    )


class SkillExecutionRequest(BaseModel):
    """Zlecenie wykonania skilla na węźle."""

    message_type: MessageType = MessageType.EXECUTE_SKILL
    request_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unikalny ID żądania"
    )
    node_id: str = Field(description="ID węzła docelowego")
    skill_name: str = Field(description="Nazwa skilla do wykonania")
    method_name: str = Field(description="Nazwa metody skilla")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Parametry wywołania"
    )
    timeout: int = Field(default=30, description="Timeout w sekundach")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="Timestamp"
    )


class HeartbeatMessage(BaseModel):
    """Wiadomość heartbeat od węzła."""

    message_type: MessageType = MessageType.HEARTBEAT
    node_id: str = Field(description="ID węzła")
    cpu_usage: float = Field(default=0.0, description="Użycie CPU (0.0-1.0)")
    memory_usage: float = Field(default=0.0, description="Użycie pamięci (0.0-1.0)")
    active_tasks: int = Field(default=0, description="Liczba aktywnych zadań")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="Timestamp"
    )


class NodeResponse(BaseModel):
    """Odpowiedź węzła na żądanie."""

    message_type: MessageType = MessageType.RESPONSE
    request_id: str = Field(description="ID żądania, na które odpowiadamy")
    node_id: str = Field(description="ID węzła")
    success: bool = Field(description="Czy operacja się powiodła")
    result: Optional[Any] = Field(default=None, description="Wynik wykonania")
    error: Optional[str] = Field(default=None, description="Opis błędu jeśli wystąpił")
    execution_time: float = Field(default=0.0, description="Czas wykonania w sekundach")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="Timestamp"
    )


class NodeMessage(BaseModel):
    """Uniwersalny kontener wiadomości węzła."""

    message_type: MessageType = Field(description="Typ wiadomości")
    payload: Dict[str, Any] = Field(description="Dane wiadomości")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="Timestamp"
    )

    @classmethod
    def from_handshake(cls, handshake: NodeHandshake) -> "NodeMessage":
        """Tworzy NodeMessage z NodeHandshake."""
        return cls(
            message_type=MessageType.HANDSHAKE,
            payload=handshake.model_dump(),
        )

    @classmethod
    def from_execution_request(cls, request: SkillExecutionRequest) -> "NodeMessage":
        """Tworzy NodeMessage z SkillExecutionRequest."""
        return cls(
            message_type=MessageType.EXECUTE_SKILL,
            payload=request.model_dump(),
        )

    @classmethod
    def from_heartbeat(cls, heartbeat: HeartbeatMessage) -> "NodeMessage":
        """Tworzy NodeMessage z HeartbeatMessage."""
        return cls(
            message_type=MessageType.HEARTBEAT,
            payload=heartbeat.model_dump(),
        )

    @classmethod
    def from_response(cls, response: NodeResponse) -> "NodeMessage":
        """Tworzy NodeMessage z NodeResponse."""
        return cls(
            message_type=MessageType.RESPONSE,
            payload=response.model_dump(),
        )
