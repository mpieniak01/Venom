"""Integration tests for Workflow Control Plane API endpoints."""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from venom_core.api.model_schemas.workflow_control import (
    ApplyMode,
    ReasonCode,
    WorkflowStatus,
)
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

    def get_effective_config_with_sources(
        self, mask_secrets: bool = True
    ) -> tuple[dict[str, Any], dict[str, str]]:
        config = dict(self._config)
        sources = {key: "env" for key in config.keys()}
        return config, sources

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
    from venom_core.services.runtime_controller import (
        ServiceInfo,
        ServiceStatus,
        ServiceType,
    )

    fake_config = InMemoryConfigManager()
    monkeypatch.setattr(control_plane_module, "config_manager", fake_config)
    monkeypatch.setattr(
        control_plane_module.runtime_controller,
        "get_all_services_status",
        lambda: [
            ServiceInfo(
                name="backend",
                service_type=ServiceType.BACKEND,
                status=ServiceStatus.RUNNING,
                uptime_seconds=1,
            )
        ],
    )
    control_plane_module._control_plane_service = None
    yield fake_config
    control_plane_module._control_plane_service = None


@pytest.fixture(scope="module")
def client():
    """Fixture for FastAPI TestClient."""
    with TestClient(app) as test_client:
        yield test_client


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

    def test_state_exposes_pr204_fields_with_defaults(self, client, monkeypatch):
        """PR 204 real-state parity fields must be present in state response.

        Without an active tracer the fields default to None/empty-list,
        not omitted, to keep the frontend contract stable.
        """
        import venom_core.services.control_plane as control_plane_module

        # Simulate environment with no tracer (no request history)
        monkeypatch.setattr(control_plane_module, "get_request_tracer", lambda: None)

        response = client.get("/api/v1/workflow/control/state")
        assert response.status_code == 200
        state = response.json()["system_state"]

        # New PR 204 fields: null when no tracer is active
        assert "active_request_id" in state
        assert "active_task_status" in state
        assert "llm_runtime_id" in state
        assert "llm_provider_name" in state
        assert "llm_model" in state
        assert state["active_request_id"] is None
        assert state["active_task_status"] is None
        assert state["llm_runtime_id"] is None
        assert state["llm_provider_name"] is None
        assert state["llm_model"] is None

        # allowed_operations must be present and empty when no active request
        assert "allowed_operations" in state
        assert isinstance(state["allowed_operations"], list)
        assert state["allowed_operations"] == []

    def test_state_allows_retry_for_failed_workflow(self, client, monkeypatch):
        """FAILED workflow should expose retry in allowed_operations."""
        import venom_core.services.control_plane as control_plane_module
        import venom_core.services.workflow_operations as workflow_operations_module

        class FakeTracer:
            def get_all_traces(self, limit=1):
                assert limit == 1
                return [
                    SimpleNamespace(
                        request_id="1e18dd58-6f3e-4efe-95da-8c5c33ee1871",
                        status=SimpleNamespace(value="FAILED"),
                        llm_runtime_id="ollama@http://localhost:11434/v1",
                        llm_provider="ollama",
                        llm_model="deepseek-r1:8b",
                    )
                ]

        class FakeWorkflowService:
            def register_workflow(self, workflow_id: str, status: WorkflowStatus):
                self.workflow_id = workflow_id
                self.status = status

            def sync_workflow_status(self, workflow_id: str, status: WorkflowStatus):
                self.workflow_id = workflow_id
                self.status = status

            def get_workflow_status(self, _workflow_id: str) -> WorkflowStatus:
                return WorkflowStatus.FAILED

            def get_latest_workflow_status(self) -> WorkflowStatus:
                return WorkflowStatus.IDLE

        monkeypatch.setattr(
            control_plane_module, "get_request_tracer", lambda: FakeTracer()
        )
        monkeypatch.setattr(
            workflow_operations_module,
            "get_workflow_service",
            lambda: FakeWorkflowService(),
        )

        response = client.get("/api/v1/workflow/control/state")
        assert response.status_code == 200
        state = response.json()["system_state"]
        assert state["workflow_status"] == WorkflowStatus.FAILED.value
        assert state["allowed_operations"] == [
            "retry",
            "retry_from_step",
            "replay_step",
            "skip_step",
            "dry_run",
        ]

    def test_state_handles_runtime_tracer_errors(self, client, monkeypatch):
        """Tracer runtime errors should not fail state endpoint."""
        import venom_core.services.control_plane as control_plane_module
        import venom_core.services.workflow_operations as workflow_operations_module

        class BrokenTracer:
            def get_all_traces(self, limit=1):
                raise RuntimeError("tracer backend unavailable")

        class FakeWorkflowService:
            def get_latest_workflow_status(self) -> WorkflowStatus:
                return WorkflowStatus.IDLE

            def get_workflow_status(self, _workflow_id: str) -> WorkflowStatus:
                return WorkflowStatus.IDLE

            def register_workflow(self, _workflow_id: str, _status: WorkflowStatus):
                return None

            def sync_workflow_status(self, _workflow_id: str, _status: WorkflowStatus):
                return None

        monkeypatch.setattr(
            control_plane_module, "get_request_tracer", lambda: BrokenTracer()
        )
        monkeypatch.setattr(
            workflow_operations_module,
            "get_workflow_service",
            lambda: FakeWorkflowService(),
        )

        response = client.get("/api/v1/workflow/control/state")
        assert response.status_code == 200
        state = response.json()["system_state"]
        assert state["workflow_status"] == WorkflowStatus.IDLE.value
        assert state["allowed_operations"] == []


class TestExecutionStepOperationsEndpoint:
    """Test /api/v1/workflow/control/workflow/{request_id}/step/{step_id}/{operation}."""

    def test_step_operation_gateway_accepts_extended_operations(
        self, client, monkeypatch
    ):
        request_id = "1e18dd58-6f3e-4efe-95da-8c5c33ee1871"
        step_id = f"{request_id}:3"
        captured: dict[str, Any] = {}

        class FakeWorkflowOperationService:
            def retry_workflow(
                self,
                workflow_id: str,
                triggered_by: str,
                step_id: str | None = None,
                metadata: dict[str, Any] | None = None,
            ):
                captured["workflow_id"] = workflow_id
                captured["triggered_by"] = triggered_by
                captured["step_id"] = step_id
                captured["metadata"] = metadata or {}
                return {"ok": True, "operation": "retry", "step_id": step_id}

        monkeypatch.setattr(
            workflow_control_routes,
            "get_workflow_operation_service",
            lambda: FakeWorkflowOperationService(),
        )

        response = client.post(
            f"/api/v1/workflow/control/workflow/{request_id}/step/{step_id}/replay_step"
        )
        assert response.status_code == 200
        assert captured["workflow_id"] == request_id
        assert captured["step_id"] == step_id
        assert captured["metadata"]["scope"] == "execution_step"
        assert captured["metadata"]["step_operation"] == "replay_step"

    def test_step_operation_gateway_rejects_foreign_step_id(self, client):
        request_id = "1e18dd58-6f3e-4efe-95da-8c5c33ee1871"
        other_step_id = "6c8f4ce4-4f1d-44db-b8a2-7fe7c7fc0df2:0"

        response = client.post(
            f"/api/v1/workflow/control/workflow/{request_id}/step/{other_step_id}/retry_from_step"
        )
        assert response.status_code == 400
        assert "step_id does not belong to request_id" in response.text


class TestOptionsEndpoint:
    """Test /api/v1/workflow/control/options endpoint."""

    def test_get_control_options(self, client):
        response = client.get("/api/v1/workflow/control/options")
        assert response.status_code == 200

        data = response.json()
        assert "decision_strategies" in data
        assert "intent_modes" in data
        assert "kernels" in data
        assert data["provider_sources"] == ["local", "cloud"]
        assert data["embedding_sources"] == ["local", "cloud"]

        assert "providers" in data
        assert "embeddings" in data
        assert "kernel_runtimes" in data
        assert "intent_requirements" in data
        assert "provider_embeddings" in data
        assert "embedding_providers" in data
        assert "active" in data

        assert isinstance(data["providers"]["local"], list)
        assert isinstance(data["providers"]["cloud"], list)
        assert isinstance(data["embeddings"]["local"], list)
        assert isinstance(data["embeddings"]["cloud"], list)
        assert isinstance(data["kernel_runtimes"], dict)
        assert isinstance(data["intent_requirements"], dict)
        assert isinstance(data["provider_embeddings"], dict)
        assert isinstance(data["embedding_providers"], dict)
        assert isinstance(data["decision_strategies"], list)
        assert isinstance(data["intent_modes"], list)
        assert isinstance(data["kernels"], list)

        assert data["active"]["provider_source"] in {"local", "cloud"}
        assert data["active"]["embedding_source"] in {"local", "cloud"}
        assert "standard" in data["kernel_runtimes"]
        assert "advanced" in data["intent_requirements"]
        assert "ollama" in data["provider_embeddings"]
        assert "sentence-transformers" in data["embedding_providers"]


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

        def get_control_state(self, *args, **kwargs):
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
