from __future__ import annotations

from fastapi.testclient import TestClient

from venom_core.core.admin_audit import get_audit_trail
from venom_core.main import app
from venom_core.services.audit_stream import get_audit_stream


def _reset_audit_streams() -> None:
    get_audit_stream().clear()
    get_audit_trail().clear()


def test_audit_stream_publish_and_read_roundtrip() -> None:
    _reset_audit_streams()
    client = TestClient(app)

    response = client.post(
        "/api/v1/audit/stream",
        json={
            "source": "module.brand_studio",
            "action": "draft.generate",
            "actor": "tester",
            "status": "ok",
            "context": "queue-123",
            "details": {"channel": "github"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["entry"]["source"] == "module.brand_studio"
    assert payload["entry"]["api_channel"] == "Frontend (Next.js)"

    listing = client.get("/api/v1/audit/stream?limit=20")
    assert listing.status_code == 200
    listed_payload = listing.json()
    assert listed_payload["status"] == "success"
    assert listed_payload["count"] >= 1
    assert listed_payload["entries"][0]["action"] == "draft.generate"
    assert listed_payload["entries"][0]["api_channel"] == "Frontend (Next.js)"


def test_audit_stream_filters_by_source() -> None:
    _reset_audit_streams()
    client = TestClient(app)

    client.post(
        "/api/v1/audit/stream",
        json={
            "source": "core.admin",
            "action": "provider_activate",
            "actor": "admin",
            "status": "success",
        },
    )
    client.post(
        "/api/v1/audit/stream",
        json={
            "source": "module.brand_studio",
            "action": "queue.publish",
            "actor": "tester",
            "status": "published",
        },
    )

    filtered = client.get("/api/v1/audit/stream?source=module.brand_studio")
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["count"] == 1
    assert payload["entries"][0]["source"] == "module.brand_studio"
    assert payload["entries"][0]["api_channel"] == "Queue API"


def test_audit_stream_filters_by_api_channel() -> None:
    _reset_audit_streams()
    client = TestClient(app)

    client.post(
        "/api/v1/audit/stream",
        json={
            "source": "core.admin",
            "action": "provider_activate",
            "actor": "admin",
            "status": "success",
        },
    )
    client.post(
        "/api/v1/audit/stream",
        json={
            "source": "module.brand_studio",
            "action": "queue.publish",
            "actor": "tester",
            "status": "published",
        },
    )

    filtered = client.get("/api/v1/audit/stream?api_channel=Governance%20API")
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["count"] == 1
    assert payload["entries"][0]["source"] == "core.admin"
    assert payload["entries"][0]["api_channel"] == "Governance API"


def test_audit_stream_uses_details_api_channel_override() -> None:
    _reset_audit_streams()
    client = TestClient(app)

    response = client.post(
        "/api/v1/audit/stream",
        json={
            "source": "core.http",
            "action": "http.get",
            "actor": "tester",
            "status": "success",
            "details": {"api_channel": "System Status API"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["entry"]["api_channel"] == "System Status API"

    filtered = client.get("/api/v1/audit/stream?api_channel=system%20status%20api")
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["count"] == 1
    assert filtered_payload["entries"][0]["api_channel"] == "System Status API"


def test_audit_stream_infers_queue_and_unknown_channels() -> None:
    _reset_audit_streams()
    client = TestClient(app)

    client.post(
        "/api/v1/audit/stream",
        json={
            "source": "core.technical.github_publish",
            "action": "queue.publish",
            "actor": "tester",
            "status": "published",
        },
    )
    client.post(
        "/api/v1/audit/stream",
        json={
            "source": "external.service",
            "action": "custom.action",
            "actor": "tester",
            "status": "ok",
        },
    )

    listing = client.get("/api/v1/audit/stream?limit=10")
    assert listing.status_code == 200
    channels = {entry["api_channel"] for entry in listing.json()["entries"]}
    assert "Queue API" in channels
    assert "Unknown API" in channels


def test_audit_stream_ingest_token_guard(monkeypatch) -> None:
    _reset_audit_streams()
    monkeypatch.setenv("VENOM_AUDIT_STREAM_INGEST_TOKEN", "secret-token")
    client = TestClient(app)

    forbidden = client.post(
        "/api/v1/audit/stream",
        json={
            "source": "module.brand_studio",
            "action": "draft.generate",
            "actor": "tester",
            "status": "ok",
        },
    )
    assert forbidden.status_code == 403

    allowed = client.post(
        "/api/v1/audit/stream",
        headers={"X-Venom-Audit-Token": "secret-token"},
        json={
            "source": "module.brand_studio",
            "action": "draft.generate",
            "actor": "tester",
            "status": "ok",
        },
    )
    assert allowed.status_code == 200


def test_admin_audit_entries_are_mirrored_into_canonical_stream() -> None:
    _reset_audit_streams()
    client = TestClient(app)

    audit_trail = get_audit_trail()
    audit_trail.log_action(
        action="test_connection",
        user="admin",
        provider="ollama",
        result="success",
    )

    response = client.get(
        "/api/v1/audit/stream?source=core.admin&action=test_connection"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert payload["entries"][0]["source"] == "core.admin"
    assert payload["entries"][0]["actor"] == "admin"
    assert payload["entries"][0]["api_channel"] == "Governance API"
