"""Schemas for nodes API endpoints."""

from pydantic import BaseModel


class NodeExecuteRequest(BaseModel):
    """Model żądania wykonania skilla na węźle."""

    skill_name: str
    method_name: str
    parameters: dict = {}
    timeout: int = 30


class NodesListResponse(BaseModel):
    """Response with list of nodes."""

    status: str
    count: int
    online_count: int
    nodes: list[dict]


class NodeInfoResponse(BaseModel):
    """Response with node information."""

    status: str
    node: dict


class NodeExecuteResponse(BaseModel):
    """Response from node execution."""

    status: str
    result: dict
