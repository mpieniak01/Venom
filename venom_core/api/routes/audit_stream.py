"""Canonical audit stream API."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from venom_core.services.audit_stream import AuditStreamEntry, get_audit_stream

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditStreamRecord(BaseModel):
    id: str
    timestamp: datetime
    source: str
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


def _serialize_entry(entry: AuditStreamEntry) -> AuditStreamRecord:
    return AuditStreamRecord(
        id=entry.id,
        timestamp=entry.timestamp,
        source=entry.source,
        action=entry.action,
        actor=entry.actor,
        status=entry.status,
        context=entry.context,
        details=entry.details,
    )


@router.get("/stream", response_model=AuditStreamResponse)
async def get_audit_stream_entries(
    source: str | None = Query(default=None),
    action: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> AuditStreamResponse:
    stream = get_audit_stream()
    entries = stream.get_entries(
        source=source,
        action=action,
        actor=actor,
        status=status,
        limit=limit,
    )
    payload = [_serialize_entry(entry) for entry in entries]
    return AuditStreamResponse(count=len(payload), entries=payload)


@router.post("/stream", response_model=AuditStreamPublishResponse)
async def publish_audit_stream_entry(
    request: AuditStreamPublishRequest,
    x_venom_audit_token: str | None = Header(default=None),
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
