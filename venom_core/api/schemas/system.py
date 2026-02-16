from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ConnectionProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    WS = "ws"
    SSE = "sse"
    TCP = "tcp"


class ConnectionDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BIDIRECTIONAL = "bidirectional"


class AuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    SERVICE_TOKEN = "service_token"


class SourceType(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


class ConnectionStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class ApiConnection(BaseModel):
    source_component: str = Field(..., description="Nazwa komponentu źródłowego")
    target_component: str = Field(
        ..., description="Nazwa komponentu docelowego lub providera"
    )
    protocol: ConnectionProtocol = Field(..., description="Protokół komunikacji")
    direction: ConnectionDirection = Field(..., description="Kierunek połączenia")
    auth_type: AuthType = Field(..., description="Typ uwierzytelniania")
    source_type: SourceType = Field(..., description="Typ źródła (lokalne/chmura)")
    status: ConnectionStatus = Field(..., description="Status połączenia")
    description: Optional[str] = Field(None, description="Opis biznesowy połączenia")
    is_critical: bool = Field(
        False, description="Czy połączenie jest krytyczne dla działania systemu"
    )
    methods: List[str] = Field(
        default_factory=list, description="Lista dostępnych metod/endpointów"
    )


class ApiMapResponse(BaseModel):
    internal_connections: List[ApiConnection] = Field(
        ..., description="Lista połączeń wewnętrznych"
    )
    external_connections: List[ApiConnection] = Field(
        ..., description="Lista połączeń zewnętrznych"
    )
