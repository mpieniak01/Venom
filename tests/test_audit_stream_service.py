from __future__ import annotations

from datetime import datetime, timedelta, timezone

import venom_core.services.audit_stream as audit_stream_module


def test_env_int_parses_and_falls_back(monkeypatch):
    monkeypatch.setenv("AUDIT_TEST_INT", "42")
    assert audit_stream_module._env_int("AUDIT_TEST_INT", default=7) == 42

    monkeypatch.setenv("AUDIT_TEST_INT", "invalid")
    assert audit_stream_module._env_int("AUDIT_TEST_INT", default=7) == 7

    monkeypatch.delenv("AUDIT_TEST_INT", raising=False)
    assert audit_stream_module._env_int("AUDIT_TEST_INT", default=7) == 7


def test_publish_normalizes_fields_and_context():
    stream = audit_stream_module.AuditStream(max_entries=100)
    entry = stream.publish(
        source="  ",
        action="",
        actor="",
        status="",
        context="   ",
        details=None,
    )

    assert entry.source == "unknown"
    assert entry.action == "unknown"
    assert entry.actor == "unknown"
    assert entry.status == "unknown"
    assert entry.context is None
    assert entry.details == {}


def test_get_entries_filters_case_insensitive_and_enforces_limits():
    stream = audit_stream_module.AuditStream(max_entries=100)
    now = datetime.now(timezone.utc)
    stream.publish(
        source="core.http",
        action="http.get",
        actor="tester",
        status="success",
        timestamp=now - timedelta(seconds=3),
    )
    stream.publish(
        source="module.brand_studio",
        action="queue.publish",
        actor="Tester",
        status="Queued",
        timestamp=now - timedelta(seconds=2),
    )
    stream.publish(
        source="module.brand_studio",
        action="queue.publish",
        actor="tester",
        status="queued",
        timestamp=now - timedelta(seconds=1),
    )

    entries = stream.get_entries(
        source="MODULE.BRAND_STUDIO",
        action="QUEUE.PUBLISH",
        actor="TESTER",
        status="QUEUED",
        limit=0,
    )
    assert len(entries) == 1
    assert entries[0].status.lower() == "queued"

    assert len(stream.get_entries(limit=9999)) == 3


def test_publish_trims_entries_after_max_capacity_floor():
    stream = audit_stream_module.AuditStream(max_entries=1)
    for idx in range(105):
        stream.publish(
            source="core.http",
            action="http.get",
            actor="tester",
            status="success",
            context=f"ctx-{idx}",
            timestamp=datetime.now(timezone.utc) + timedelta(seconds=idx),
        )

    entries = stream.get_entries(limit=500)
    assert len(entries) == 100
    assert entries[0].context == "ctx-104"
    assert entries[-1].context == "ctx-5"


def test_get_audit_stream_singleton_and_env_limit(monkeypatch):
    previous_stream = audit_stream_module._audit_stream
    try:
        monkeypatch.setenv("VENOM_AUDIT_STREAM_MAX_ENTRIES", "invalid")
        audit_stream_module._audit_stream = None
        first = audit_stream_module.get_audit_stream()
        second = audit_stream_module.get_audit_stream()
        assert first is second
        assert first._max_entries == 5000
    finally:
        audit_stream_module._audit_stream = previous_stream
