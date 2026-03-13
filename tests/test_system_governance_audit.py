from __future__ import annotations

from types import SimpleNamespace

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


def test_extract_actor_from_request_prefers_state_user() -> None:
    class _State:
        user = "state-user"

    class _Request:
        state = _State()
        headers = {"X-Actor": "header-actor", "X-User-Id": "user-id"}

    assert system_governance._extract_actor_from_request(_Request()) == "state-user"


def test_extract_actor_from_request_uses_headers_fallback() -> None:
    class _State:
        user = None

    class _Request:
        state = _State()
        headers = {"X-Actor": "header-actor"}

    assert system_governance._extract_actor_from_request(_Request()) == "header-actor"


def test_get_system_autonomy_returns_500_when_level_info_missing(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(permission_guard, "get_level_info", lambda level: None)
    response = client.get("/api/v1/system/autonomy")
    assert response.status_code == 500
    assert "Nie można pobrać informacji o poziomie" in response.json()["detail"]


def test_post_system_autonomy_returns_500_when_new_level_info_missing(
    monkeypatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setattr(permission_guard, "get_current_level", lambda: 0)
    monkeypatch.setattr(permission_guard, "set_level", lambda level: True)
    monkeypatch.setattr(
        permission_guard,
        "get_level_info",
        lambda level: SimpleNamespace(name="ISOLATED") if level == 0 else None,
    )

    response = client.post("/api/v1/system/autonomy", json={"level": 10})
    assert response.status_code == 500
    assert (
        "Nie można pobrać informacji o poziomie po zmianie" in response.json()["detail"]
    )


def test_get_system_autonomy_levels_returns_500_on_guard_exception(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(
        permission_guard,
        "get_all_levels",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    response = client.get("/api/v1/system/autonomy/levels")
    assert response.status_code == 500
    assert "Błąd wewnętrzny" in response.json()["detail"]


def test_get_system_autonomy_observability_returns_policy_snapshot(monkeypatch) -> None:
    client = TestClient(app)

    class _Collector:
        def get_metrics(self):
            return {
                "policy": {
                    "blocked_count": 7,
                    "deny_rate": 12.34,
                    "top_reason_codes": [
                        {
                            "reason_code": "POLICY_TOOL_RESTRICTED",
                            "count": 4,
                            "share_rate": 57.14,
                        }
                    ],
                    "false_positive_triage": {
                        "candidate_count": 2,
                        "candidate_rate": 28.57,
                        "top_candidate_reasons": [
                            {
                                "reason_code": "POLICY_TOOL_RESTRICTED",
                                "count": 1,
                                "share_rate": 50.0,
                            }
                        ],
                    },
                }
            }

    monkeypatch.setattr(
        system_governance.tasks_service,
        "get_metrics_collector",
        lambda: _Collector(),
    )

    response = client.get("/api/v1/system/autonomy/observability")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["source"] == "runtime_policy_gate"
    assert payload["policy"]["blocked_count"] == 7
    assert payload["policy"]["deny_rate"] == 12.34
    assert (
        payload["policy"]["top_reason_codes"][0]["reason_code"]
        == "POLICY_TOOL_RESTRICTED"
    )
    assert payload["policy"]["false_positive_triage"]["candidate_count"] == 2


def test_get_system_autonomy_observability_returns_503_without_metrics_collector(
    monkeypatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setattr(
        system_governance.tasks_service,
        "get_metrics_collector",
        lambda: None,
    )

    response = client.get("/api/v1/system/autonomy/observability")
    assert response.status_code == 503
    assert "Metrics collector nie jest dostępny" in response.json()["detail"]


def test_get_system_autonomy_rollout_status_ready(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setenv("ENABLE_POLICY_GATE", "true")
    monkeypatch.setattr(
        system_governance.tasks_service,
        "get_metrics_collector",
        lambda: object(),
    )

    response = client.get("/api/v1/system/autonomy/rollout-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"] == "ready"
    assert payload["runtime_only_architecture"] is True
    assert payload["legacy_submit_stage_removed"] is True
    assert payload["policy_gate_enabled"] is True
    assert payload["observability_endpoint_available"] is True
    assert isinstance(payload["required_next_actions"], list)


def test_get_system_autonomy_rollout_status_attention_required(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setenv("ENABLE_POLICY_GATE", "false")
    monkeypatch.setattr(
        system_governance.tasks_service,
        "get_metrics_collector",
        lambda: None,
    )

    response = client.get("/api/v1/system/autonomy/rollout-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"] == "attention_required"
    assert payload["policy_gate_enabled"] is False
    assert payload["observability_endpoint_available"] is False
    assert any(
        "ENABLE_POLICY_GATE=true" in item for item in payload["required_next_actions"]
    )
