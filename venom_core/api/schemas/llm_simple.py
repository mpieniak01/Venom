"""Schemas for LLM simple API endpoints."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class SimpleChatRequest(BaseModel):
    """Request for simple chat streaming."""

    content: str = Field(..., min_length=1, max_length=50000)
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    response_format: Optional[dict[str, Any] | str] = None
    format: Optional[dict[str, Any] | str] = None
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[dict[str, Any] | str] = None
    think: Optional[bool] = None
    session_id: Optional[str] = None
