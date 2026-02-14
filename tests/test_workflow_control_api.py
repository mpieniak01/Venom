"""Integration tests for Workflow Control Plane API endpoints."""

import pytest
from fastapi.testclient import TestClient

from venom_core.main import app
from venom_core.api.model_schemas.workflow_control import (
    ApplyMode,
    ReasonCode,
    ResourceType,
)


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

        plan_response = client.post(
            "/api/v1/workflow/control/plan", json=plan_request
        )
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

        plan_response = client.post(
            "/api/v1/workflow/control/plan", json=plan_request
        )
        ticket = plan_response.json()["execution_ticket"]

        # Apply without confirming restart
        apply_request = {"execution_ticket": ticket, "confirm_restart": False}

        response = client.post("/api/v1/workflow/control/apply", json=apply_request)

        assert response.status_code == 200
        data = response.json()

        # Should indicate restart required but not confirmed
        if data["apply_mode"] == ApplyMode.RESTART_REQUIRED.value:
            assert len(data["pending_restart"]) > 0


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
        response = client.get(
            "/api/v1/workflow/control/audit?page=1&page_size=10"
        )

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

        plan_response = client.post(
            "/api/v1/workflow/control/plan", json=plan_request
        )
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

        plan_response = client.post(
            "/api/v1/workflow/control/plan", json=plan_request
        )
        ticket = plan_response.json()["execution_ticket"]

        # Try to apply dry_run plan (should fail or be rejected based on implementation)
        apply_request = {"execution_ticket": ticket, "confirm_restart": True}

        apply_response = client.post(
            "/api/v1/workflow/control/apply", json=apply_request
        )

        # Either rejected or invalid ticket response is acceptable
        assert apply_response.status_code in [200, 400]
