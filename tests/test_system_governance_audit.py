from __future__ import annotations

from fastapi.testclient import TestClient

from venom_core.api.routes import system_governance
from venom_core.core.permission_guard import permission_guard
from venom_core.main import app
from venom_core.services.audit_stream import get_audit_stream


def test_post_system_autonomy_publishes_level_changed_event() -> None:
    audit_stream = get_audit_stream()
    audit_stream.clear()
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(0)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/system/autonomy",
            json={"level": 10},
            headers={"X-Actor": "governance-tester"},
        )
        assert response.status_code == 200

        entries = audit_stream.get_entries(action="autonomy.level_changed", limit=5)
        assert entries
        entry = entries[0]
        assert entry.source == "core.governance"
        assert entry.status == "success"
        assert entry.actor == "governance-tester"
        assert entry.details["old_level"] == 0
        assert entry.details["new_level"] == 10
        assert entry.details["request_path"] == "/api/v1/system/autonomy"
    finally:
        permission_guard.set_level(previous_level)
        audit_stream.clear()


def test_post_system_autonomy_invalid_level_publishes_failure_event(
    monkeypatch,
) -> None:
    audit_stream = get_audit_stream()
    audit_stream.clear()
    previous_level = permission_guard.get_current_level()
    permission_guard.set_level(0)

    original_get_level_info = permission_guard.get_level_info
    monkeypatch.setattr(
        permission_guard,
        "get_level_info",
        lambda level: None if level == 0 else original_get_level_info(level),
    )
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/system/autonomy",
            json={"level": 99},
            headers={"X-User-Id": "governance-failure-tester"},
        )
        assert response.status_code == 400

        entries = audit_stream.get_entries(action="autonomy.level_changed", limit=5)
        assert entries
        entry = entries[0]
        assert entry.source == "core.governance"
        assert entry.status == "failure"
        assert entry.actor == "governance-failure-tester"
        assert entry.details["old_level"] == 0
        assert entry.details["old_level_name"] == "UNKNOWN"
        assert entry.details["new_level"] == 99
        assert entry.details["new_level_name"] == "UNKNOWN"
    finally:
        permission_guard.set_level(previous_level)
        audit_stream.clear()


def test_extract_actor_from_request_handles_internal_errors() -> None:
    class _BrokenRequest:
        @property
        def state(self):
            raise RuntimeError("broken-state")

    assert system_governance._extract_actor_from_request(_BrokenRequest()) == "unknown"
