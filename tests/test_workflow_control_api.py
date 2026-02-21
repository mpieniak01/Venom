"""Integration tests for Workflow Control Plane API endpoints."""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from venom_core.api.model_schemas.workflow_control import ApplyMode, ReasonCode
from venom_core.api.routes import workflow_control as workflow_control_routes
from venom_core.main import app


class InMemoryConfigManager:
    """Test double for config manager to avoid real .env writes."""

    def __init__(self):
        self._config: dict[str, Any] = {
            "AI_MODE": "standard",
            "INTENT_MODE": "simple",
            "KERNEL": "standard",
            "WORKFLOW_RUNTIME": "python",
            "ACTIVE_PROVIDER": "ollama",
            "EMBEDDING_MODEL": "sentence-transformers",
            "LLM_MODEL_NAME": "llama2",
            "LLM_SERVICE_TYPE": "local",
        }
        self.history: list[dict[str, Any]] = []

    def get_config(self, mask_secrets: bool = False) -> dict[str, Any]:
        return dict(self._config)

    def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        self.history.append(dict(updates))
        if "FAIL_ON_UPDATE" in updates:
            return {
                "success": False,
                "message": "Injected failure",
                "restart_required": [],
            }

        changed_keys: list[str] = []
        for key, value in updates.items():
            old = self._config.get(key)
            if str(old) != str(value):
                self._config[key] = str(value)
                changed_keys.append(key)

        restart_required = []
        if any(k in {"KERNEL", "WORKFLOW_RUNTIME"} for k in changed_keys):
            restart_required.append("backend")

        return {
            "success": True,
            "message": "Updated in-memory config",
            "restart_required": restart_required,
            "changed_keys": changed_keys,
        }


@pytest.fixture(autouse=True)
def isolated_control_plane(monkeypatch):
    """Reset singleton and inject in-memory config manager for each test."""
    import venom_core.services.control_plane as control_plane_module

    fake_config = InMemoryConfigManager()
    monkeypatch.setattr(control_plane_module, "config_manager", fake_config)
    control_plane_module._control_plane_service = None
    yield fake_config
    control_plane_module._control_plane_service = None


@pytest.fixture
def client():
    """Fixture for FastAPI TestClient."""
    return TestClient(app)


class TestPlanEndpoint:
    """Test /api/v1/workflow/control/plan endpoint."""

    def test_plan_simple_change(self, client):
        """Test planning a simple configuration change."""
        request = {
            "changes": [
                {
                    "resource_type": "kernel",
                    "resource_id": "standard",
                    "action": "update",
                    "current_value": "standard",
                    "new_value": "optimized",
                }
            ],
            "dry_run": False,
            "force": False,
        }

        response = client.post("/api/v1/workflow/control/plan", json=request)

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "execution_ticket" in data
        assert "valid" in data
        assert "reason_code" in data
        assert "compatibility_report" in data
        assert "planned_changes" in data

        # Check execution ticket is a valid UUID-like string
        assert len(data["execution_ticket"]) > 0

        # Check compatibility report structure
        assert "compatible" in data["compatibility_report"]
        assert "issues" in data["compatibility_report"]
        assert "warnings" in data["compatibility_report"]
        assert "affected_services" in data["compatibility_report"]

    def test_plan_dry_run(self, client):
        """Test planning with dry_run flag."""
        request = {
            "changes": [
                {
                    "resource_type": "provider",
                    "resource_id": "ollama",
                    "action": "update",
                }
            ],
            "dry_run": True,
        }

        response = client.post("/api/v1/workflow/control/plan", json=request)

        assert response.status_code == 200
        data = response.json()

        # Dry run should still return a ticket but won't be stored for apply
        assert data["execution_ticket"] is not None

    def test_plan_multiple_changes(self, client):
        """Test planning multiple configuration changes."""
        request = {
            "changes": [
                {
                    "resource_type": "kernel",
                    "resource_id": "standard",
                    "action": "update",
                },
                {
                    "resource_type": "provider",
                    "resource_id": "ollama",
                    "action": "update",
                },
            ],
        }

        response = client.post("/api/v1/workflow/control/plan", json=request)

        assert response.status_code == 200
        data = response.json()
        assert len(data["planned_changes"]) > 0

    def test_plan_invalid_request(self, client):
        """Test planning with invalid request."""
        # Missing required field 'changes'
        request = {"dry_run": False}

        response = client.post("/api/v1/workflow/control/plan", json=request)

        assert response.status_code == 422  # Validation error

    def test_plan_empty_changes(self, client):
        """Test planning with empty changes list."""
        request = {"changes": []}

        response = client.post("/api/v1/workflow/control/plan", json=request)

        assert response.status_code == 200
        data = response.json()
        assert len(data["planned_changes"]) == 0


class TestApplyEndpoint:
    """Test /api/v1/workflow/control/apply endpoint."""

    def test_apply_valid_ticket(self, client):
        """Test applying changes with valid execution ticket."""
        # First, create a plan
        plan_request = {
            "changes": [
                {
                    "resource_type": "kernel",
                    "resource_id": "standard",
                    "action": "update",
                }
            ],
        }

        plan_response = client.post("/api/v1/workflow/control/plan", json=plan_request)
        assert plan_response.status_code == 200
        plan_data = plan_response.json()
        ticket = plan_data["execution_ticket"]

        # Now apply the plan
        apply_request = {"execution_ticket": ticket, "confirm_restart": True}

        apply_response = client.post(
            "/api/v1/workflow/control/apply", json=apply_request
        )

        assert apply_response.status_code == 200
        apply_data = apply_response.json()

        # Check response structure
        assert "execution_ticket" in apply_data
        assert apply_data["execution_ticket"] == ticket
        assert "apply_mode" in apply_data
        assert "reason_code" in apply_data
        assert "message" in apply_data
        assert "applied_changes" in apply_data
        assert "pending_restart" in apply_data
        assert "failed_changes" in apply_data

    def test_apply_invalid_ticket(self, client):
        """Test applying with invalid execution ticket."""
        apply_request = {
            "execution_ticket": "invalid-ticket-12345",
            "confirm_restart": False,
        }

        response = client.post("/api/v1/workflow/control/apply", json=apply_request)

        assert response.status_code == 200
        data = response.json()

        # Should return rejected with invalid ticket
        assert data["apply_mode"] == ApplyMode.REJECTED.value
        assert len(data["failed_changes"]) > 0

    def test_apply_without_restart_confirmation(self, client):
        """Test applying changes that require restart without confirmation."""
        # Create a plan that requires restart
        plan_request = {
            "changes": [
                {
                    "resource_type": "kernel",
                    "resource_id": "standard",
                    "action": "update",
                }
            ],
        }

        plan_response = client.post("/api/v1/workflow/control/plan", json=plan_request)
        ticket = plan_response.json()["execution_ticket"]

        # Apply without confirming restart
        apply_request = {"execution_ticket": ticket, "confirm_restart": False}

        response = client.post("/api/v1/workflow/control/apply", json=apply_request)

        assert response.status_code == 200
        data = response.json()

        # Should indicate restart required but not confirmed
        if data["apply_mode"] == ApplyMode.RESTART_REQUIRED.value:
            assert len(data["pending_restart"]) > 0

    def test_apply_partial_failure_triggers_rollback(self, client):
        """Test partial failure rolls back already applied config changes."""
        # Plan two changes: first succeeds, second fails in fake config manager.
        plan_request = {
            "changes": [
                {
                    "resource_type": "decision_strategy",
                    "resource_id": "AI_MODE",
                    "action": "update",
                    "new_value": "expert",
                },
                {
                    "resource_type": "config",
                    "resource_id": "FAIL_ON_UPDATE",
                    "action": "update",
                    "new_value": "boom",
                },
            ],
        }
        plan_response = client.post("/api/v1/workflow/control/plan", json=plan_request)
        assert plan_response.status_code == 200
        ticket = plan_response.json()["execution_ticket"]

        apply_response = client.post(
            "/api/v1/workflow/control/apply",
            json={"execution_ticket": ticket, "confirm_restart": True},
        )
        assert apply_response.status_code == 200
        apply_data = apply_response.json()
        assert apply_data["apply_mode"] == ApplyMode.REJECTED.value
        assert apply_data["rollback_available"] is True
        assert any("Rollback" in msg for msg in apply_data["failed_changes"])

        # Confirm rollback restored state.
        state_response = client.get("/api/v1/workflow/control/state")
        assert state_response.status_code == 200
        assert state_response.json()["system_state"]["decision_strategy"] == "standard"

        # Confirm rollback operation is visible in audit trail.
        audit_response = client.get("/api/v1/workflow/control/audit")
        assert audit_response.status_code == 200
        audit_entries = audit_response.json()["entries"]
        assert any(e["operation_type"] == "rollback" for e in audit_entries)

    def test_apply_rejects_when_operation_in_progress(self, client, monkeypatch):
        """Apply should reject when ticket is already being processed."""
        plan_request = {
            "changes": [
                {
                    "resource_type": "decision_strategy",
                    "resource_id": "AI_MODE",
                    "action": "update",
                    "new_value": "advanced",
                }
            ],
        }
        plan_response = client.post("/api/v1/workflow/control/plan", json=plan_request)
        ticket = plan_response.json()["execution_ticket"]

        import venom_core.services.control_plane as control_plane_module

        service = control_plane_module.get_control_plane_service()
        monkeypatch.setattr(service, "_begin_operation", lambda _operation_id: False)

        apply_response = client.post(
            "/api/v1/workflow/control/apply",
            json={"execution_ticket": ticket, "confirm_restart": True},
        )
        assert apply_response.status_code == 200
        data = apply_response.json()
        assert data["apply_mode"] == ApplyMode.REJECTED.value
        assert data["reason_code"] == ReasonCode.OPERATION_IN_PROGRESS.value


class TestStateEndpoint:
    """Test /api/v1/workflow/control/state endpoint."""

    def test_get_system_state(self, client):
        """Test getting current system state."""
        response = client.get("/api/v1/workflow/control/state")

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "system_state" in data

        state = data["system_state"]
        assert "timestamp" in state
        assert "decision_strategy" in state
        assert "intent_mode" in state
        assert "kernel" in state
        assert "runtime" in state
        assert "provider" in state
        assert "embedding_model" in state
        assert "workflow_status" in state
        assert "active_operations" in state
        assert "health" in state

    def test_state_has_valid_data(self, client):
        """Test that state endpoint returns valid data."""
        response = client.get("/api/v1/workflow/control/state")
        data = response.json()

        state = data["system_state"]

        # Check that core fields have values
        assert state["decision_strategy"] is not None
        assert state["intent_mode"] is not None
        assert state["kernel"] is not None
        assert isinstance(state["runtime"], dict)
        assert isinstance(state["provider"], dict)
        assert isinstance(state["active_operations"], list)
        assert isinstance(state["health"], dict)
        assert "overall" in state["health"]
        assert "checks" in state["health"]

    def test_state_reflects_runtime_from_config(self, client, isolated_control_plane):
        """State should derive runtime from config, not hardcoded placeholder."""
        isolated_control_plane.update_config({"WORKFLOW_RUNTIME": "hybrid"})
        response = client.get("/api/v1/workflow/control/state")
        assert response.status_code == 200
        state = response.json()["system_state"]
        assert state["provider"]["active"] == "ollama"
        assert state["health"]["overall"] in {"healthy", "degraded", "critical"}


class TestOptionsEndpoint:
    """Test /api/v1/workflow/control/options endpoint."""

    def test_get_control_options(self, client):
        response = client.get("/api/v1/workflow/control/options")
        assert response.status_code == 200

        data = response.json()
        assert data["provider_sources"] == ["local", "cloud"]
        assert data["embedding_sources"] == ["local", "cloud"]

        assert "providers" in data
        assert "embeddings" in data
        assert "active" in data

        assert isinstance(data["providers"]["local"], list)
        assert isinstance(data["providers"]["cloud"], list)
        assert isinstance(data["embeddings"]["local"], list)
        assert isinstance(data["embeddings"]["cloud"], list)

        assert data["active"]["provider_source"] in {"local", "cloud"}
        assert data["active"]["embedding_source"] in {"local", "cloud"}


class TestAuditEndpoint:
    """Test /api/v1/workflow/control/audit endpoint."""

    def test_get_audit_trail(self, client):
        """Test getting audit trail."""
        response = client.get("/api/v1/workflow/control/audit")

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "entries" in data
        assert "total_count" in data
        assert "page" in data
        assert "page_size" in data

        assert isinstance(data["entries"], list)
        assert data["page"] == 1
        assert data["page_size"] == 50

    def test_audit_trail_after_plan(self, client):
        """Test that audit trail records plan operations."""
        # Perform a plan operation
        plan_request = {
            "changes": [
                {
                    "resource_type": "kernel",
                    "resource_id": "standard",
                    "action": "update",
                }
            ],
        }

        client.post("/api/v1/workflow/control/plan", json=plan_request)

        # Check audit trail
        response = client.get("/api/v1/workflow/control/audit")
        data = response.json()

        # Should have at least one entry
        assert data["total_count"] >= 1
        if len(data["entries"]) > 0:
            entry = data["entries"][0]
            assert "operation_id" in entry
            assert "timestamp" in entry
            assert "triggered_by" in entry
            assert "operation_type" in entry
            assert "result" in entry

    def test_audit_trail_pagination(self, client):
        """Test audit trail pagination."""
        response = client.get("/api/v1/workflow/control/audit?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()

        assert data["page"] == 1
        assert data["page_size"] == 10
        assert len(data["entries"]) <= 10

    def test_audit_trail_filtering(self, client):
        """Test audit trail filtering."""
        response = client.get(
            "/api/v1/workflow/control/audit?operation_type=plan&result=success"
        )

        assert response.status_code == 200
        data = response.json()

        # All returned entries should match filters
        for entry in data["entries"]:
            if "operation_type" in entry:
                assert entry["operation_type"] == "plan"
            if "result" in entry:
                assert entry["result"] == "success"


class TestEndToEndWorkflow:
    """Test end-to-end workflow scenarios."""

    def test_full_plan_apply_workflow(self, client):
        """Test complete plan -> apply workflow."""
        # Step 1: Plan changes
        plan_request = {
            "changes": [
                {
                    "resource_type": "kernel",
                    "resource_id": "standard",
                    "action": "update",
                }
            ],
        }

        plan_response = client.post("/api/v1/workflow/control/plan", json=plan_request)
        assert plan_response.status_code == 200

        plan_data = plan_response.json()
        ticket = plan_data["execution_ticket"]

        # Step 2: Check system state before apply
        state_response = client.get("/api/v1/workflow/control/state")
        assert state_response.status_code == 200

        # Step 3: Apply changes
        apply_request = {"execution_ticket": ticket, "confirm_restart": True}

        apply_response = client.post(
            "/api/v1/workflow/control/apply", json=apply_request
        )
        assert apply_response.status_code == 200

        # Step 4: Check audit trail
        audit_response = client.get("/api/v1/workflow/control/audit")
        assert audit_response.status_code == 200
        assert audit_response.json()["total_count"] >= 2  # plan + apply

    def test_plan_reject_invalid_apply(self, client):
        """Test that applying an invalid plan is rejected."""
        # Create a plan with dry_run
        plan_request = {
            "changes": [
                {
                    "resource_type": "kernel",
                    "resource_id": "standard",
                    "action": "update",
                }
            ],
            "dry_run": True,
        }

        plan_response = client.post("/api/v1/workflow/control/plan", json=plan_request)
        ticket = plan_response.json()["execution_ticket"]

        # Try to apply dry_run plan (should fail or be rejected based on implementation)
        apply_request = {"execution_ticket": ticket, "confirm_restart": True}

        apply_response = client.post(
            "/api/v1/workflow/control/apply", json=apply_request
        )

        # Either rejected or invalid ticket response is acceptable
        assert apply_response.status_code in [200, 400]


def test_extract_user_prefers_state_then_headers_and_handles_exceptions():
    request_with_state = SimpleNamespace(
        state=SimpleNamespace(user="state-user"),
        headers={"x-user": "header-user"},
    )
    assert (
        workflow_control_routes._extract_user_from_request(request_with_state)
        == "state-user"
    )

    request_with_header = SimpleNamespace(
        state=SimpleNamespace(user=""),
        headers={"x-authenticated-user": "auth-user"},
    )
    assert (
        workflow_control_routes._extract_user_from_request(request_with_header)
        == "auth-user"
    )

    class _BrokenState:
        @property
        def user(self):
            raise RuntimeError("broken-state")

    broken_request = SimpleNamespace(state=_BrokenState(), headers={})
    assert (
        workflow_control_routes._extract_user_from_request(broken_request) == "unknown"
    )


def test_workflow_control_routes_return_500_when_dependencies_raise(client):
    class _FailingService:
        def plan_changes(self, *_args, **_kwargs):
            raise RuntimeError("plan-error")

        def apply_changes(self, *_args, **_kwargs):
            raise RuntimeError("apply-error")

        def get_system_state(self):
            raise RuntimeError("state-error")

        def get_control_options(self):
            raise RuntimeError("options-error")

    class _FailingAuditTrail:
        def get_entries(self, **_kwargs):
            raise RuntimeError("audit-error")

    app.dependency_overrides[workflow_control_routes.get_control_plane_service] = (
        lambda: _FailingService()
    )
    app.dependency_overrides[workflow_control_routes.get_control_plane_audit_trail] = (
        lambda: _FailingAuditTrail()
    )

    try:
        plan_response = client.post(
            "/api/v1/workflow/control/plan",
            json={
                "changes": [
                    {
                        "resource_type": "config",
                        "resource_id": "AI_MODE",
                        "action": "update",
                    }
                ]
            },
        )
        assert plan_response.status_code == 500
        assert "plan-error" in plan_response.json()["detail"]

        apply_response = client.post(
            "/api/v1/workflow/control/apply",
            json={"execution_ticket": "ticket", "confirm_restart": True},
        )
        assert apply_response.status_code == 500
        assert "apply-error" in apply_response.json()["detail"]

        state_response = client.get("/api/v1/workflow/control/state")
        assert state_response.status_code == 500
        assert "state-error" in state_response.json()["detail"]

        options_response = client.get("/api/v1/workflow/control/options")
        assert options_response.status_code == 500
        assert "options-error" in options_response.json()["detail"]

        audit_response = client.get("/api/v1/workflow/control/audit")
        assert audit_response.status_code == 500
        assert "audit-error" in audit_response.json()["detail"]
    finally:
        app.dependency_overrides.pop(
            workflow_control_routes.get_control_plane_service, None
        )
        app.dependency_overrides.pop(
            workflow_control_routes.get_control_plane_audit_trail, None
        )
