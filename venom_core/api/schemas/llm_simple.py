"""Schemas for LLM simple API endpoints."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=50000)


class SimpleChatRequest(BaseModel):
    """Request for simple chat streaming."""

    content: str = Field(..., min_length=1, max_length=50000)
    model: Optional[str] = None
    expected_quote_hash: Optional[str] = Field(default=None, max_length=64)
    expected_runtime_id: Optional[str] = Field(default=None, max_length=1024)
    expected_config_hash: Optional[str] = Field(default=None, max_length=128)
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    seed: Optional[int] = Field(default=None, strict=True, ge=-(2**63), le=2**63 - 1)
    top_p: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = Field(default=None, ge=0, le=20)
    stream: Optional[bool] = None
    response_format: Optional[dict[str, Any] | str] = None
    format: Optional[dict[str, Any] | str] = None
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[dict[str, Any] | str] = None
    think: Optional[bool] = None
    session_id: Optional[str] = None
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)
