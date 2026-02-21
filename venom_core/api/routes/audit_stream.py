"""Canonical audit stream API."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from venom_core.services.audit_stream import AuditStreamEntry, get_audit_stream

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditStreamRecord(BaseModel):
    id: str
    timestamp: datetime
    source: str
    api_channel: str
    action: str
    actor: str
    status: str
    context: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditStreamResponse(BaseModel):
    status: Literal["success"] = "success"
    count: int
    entries: list[AuditStreamRecord]


class AuditStreamPublishRequest(BaseModel):
    source: str = Field(min_length=1, max_length=120)
    action: str = Field(min_length=1, max_length=120)
    actor: str = Field(min_length=1, max_length=120)
    status: str = Field(min_length=1, max_length=80)
    context: str | None = Field(default=None, max_length=512)
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None
    id: str | None = Field(default=None, max_length=64)


class AuditStreamPublishResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    entry: AuditStreamRecord


def _required_ingest_token() -> str:
    return (os.getenv("VENOM_AUDIT_STREAM_INGEST_TOKEN") or "").strip()


_ACTION_PREFIX_CHANNEL_MAP: tuple[tuple[str, str], ...] = (
    ("queue.", "Queue API"),
    ("draft.", "Frontend (Next.js)"),
    ("strategy.", "Strategy API"),
    ("campaign.", "Tasks API"),
    ("monitoring.", "Tasks API"),
    ("agent.", "Agents API"),
    ("memory.", "Memory API"),
    ("node.", "Nodes API"),
    ("feedback.", "Feedback API"),
)


def _channel_from_action(action: str) -> str | None:
    action_n = (action or "").strip().lower()
    if not action_n:
        return None
    if action_n in {"provider_activate", "test_connection", "preflight_check"}:
        return "Governance API"
    if action_n.startswith("provider_"):
        return "Governance API"
    if action_n.startswith("config."):
        return "System Services API"
    for prefix, channel in _ACTION_PREFIX_CHANNEL_MAP:
        if action_n.startswith(prefix):
            return channel
    return None


def _infer_api_channel(
    source: str, action: str, details: dict[str, Any] | None = None
) -> str:
    details = details or {}
    details_channel = details.get("api_channel")
    if isinstance(details_channel, str) and details_channel.strip():
        return details_channel.strip()

    source_n = (source or "").strip().lower()
    source_head = source_n.split(".", maxsplit=1)[0] if source_n else ""

    if source_n == "core.admin":
        return "Governance API"

    if source_n.startswith("core.technical."):
        suffix = source_n.removeprefix("core.technical.")
        if suffix.startswith("github_publish"):
            return "Queue API"
        channel = _channel_from_action(action)
        return channel or "System Services API"

    if source_n.startswith("module.brand_studio") or source_n.startswith(
        "brand_studio"
    ):
        channel = _channel_from_action(action)
        return channel or "Frontend (Next.js)"

    if source_n.startswith("core."):
        channel = _channel_from_action(action)
        return channel or "System Services API"

    channel = _channel_from_action(action)
    if channel:
        return channel

    if source_head == "module":
        return "Frontend (Next.js)"
    if source_head == "core":
        return "System Services API"

    return "Unknown API"


def _serialize_entry(entry: AuditStreamEntry) -> AuditStreamRecord:
    return AuditStreamRecord(
        id=entry.id,
        timestamp=entry.timestamp,
        source=entry.source,
        api_channel=_infer_api_channel(entry.source, entry.action, entry.details),
        action=entry.action,
        actor=entry.actor,
        status=entry.status,
        context=entry.context,
        details=entry.details,
    )


@router.get("/stream")
async def get_audit_stream_entries(
    source: Annotated[str | None, Query()] = None,
    api_channel: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    actor: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> AuditStreamResponse:
    stream = get_audit_stream()
    lookup_limit = 500 if api_channel else limit
    entries = stream.get_entries(
        source=source,
        action=action,
        actor=actor,
        status=status,
        limit=lookup_limit,
    )
    payload = [_serialize_entry(entry) for entry in entries]
    if api_channel:
        api_channel_n = api_channel.strip().lower()
        payload = [
            entry for entry in payload if entry.api_channel.lower() == api_channel_n
        ]
        payload = payload[: max(1, min(limit, 500))]
    return AuditStreamResponse(count=len(payload), entries=payload)


@router.post("/stream")
async def publish_audit_stream_entry(
    request: AuditStreamPublishRequest,
    x_venom_audit_token: Annotated[str | None, Header()] = None,
) -> AuditStreamPublishResponse:
    required_token = _required_ingest_token()
    if required_token and (x_venom_audit_token or "") != required_token:
        raise HTTPException(status_code=403, detail="audit_stream_ingest_forbidden")

    stream = get_audit_stream()
    entry = stream.publish(
        source=request.source,
        action=request.action,
        actor=request.actor,
        status=request.status,
        context=request.context,
        details=request.details,
        timestamp=request.timestamp,
        entry_id=request.id,
    )
    return AuditStreamPublishResponse(entry=_serialize_entry(entry))
