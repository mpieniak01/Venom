"""Contract/unit tests for 8 API route modules — PR-172C-09 coverage wave.

Covers:
- venom_core/api/routes/workflow_operations.py
- venom_core/api/routes/workflow_control.py
- venom_core/api/routes/nodes.py
- venom_core/api/routes/queue.py
- venom_core/api/routes/agents.py
- venom_core/api/routes/system_scheduler.py
- venom_core/api/routes/system_governance.py
- venom_core/api/routes/system_config.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(*routers) -> FastAPI:
    """Create a minimal FastAPI app with the given routers."""
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return app


def _client(*routers) -> TestClient:
    return TestClient(_make_app(*routers))


# ===========================================================================
# 1. workflow_operations.py
# ===========================================================================


class TestWorkflowOperations:
    """Contract tests for /api/v1/workflow/operations/* endpoints."""

    def _make_response(self, workflow_id, operation="pause", status="running"):
        """Build a mock WorkflowOperationResponse-compatible dict."""
        return SimpleNamespace(
            workflow_id=workflow_id,
            operation=operation,
            status=status,
            reason_code="operation_completed",
            message="OK",
            timestamp=datetime.now(timezone.utc),
            metadata={},
        )

    @pytest.fixture(autouse=True)
    def _setup(self):
        from venom_core.api.routes import workflow_operations as mod

        self.mod = mod

    def _client_with_mock(self, method_name, return_value=None, side_effect=None):
        from venom_core.api.routes import workflow_operations as mod

        mock_service = MagicMock()
        target = getattr(mock_service, method_name)
        if side_effect is not None:
            target.side_effect = side_effect
        else:
            target.return_value = return_value

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_service,
        ):
            yield _client(mod.router), mock_service

    # --- pause ---

    def test_pause_workflow_success(self):
        wid = str(uuid4())
        resp_obj = self._make_response(wid, operation="pause", status="paused")
        mock_svc = MagicMock()
        mock_svc.pause_workflow.return_value = resp_obj

        from venom_core.api.routes import workflow_operations as mod

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/pause",
                json={"workflow_id": wid, "operation": "pause"},
            )

        assert response.status_code == 200
        mock_svc.pause_workflow.assert_called_once()

    def test_pause_workflow_500_on_exception(self):
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.pause_workflow.side_effect = RuntimeError("db down")

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/pause",
                json={"workflow_id": wid, "operation": "pause"},
            )

        assert response.status_code == 500
        assert "db down" in response.json()["detail"]

    def test_pause_workflow_with_user_header(self):
        """Ensure x-authenticated-user header is extracted and forwarded."""
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.pause_workflow.return_value = self._make_response(wid)

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/pause",
                json={"workflow_id": wid, "operation": "pause"},
                headers={"x-authenticated-user": "alice"},
            )

        assert response.status_code == 200
        call_kwargs = mock_svc.pause_workflow.call_args[1]
        assert call_kwargs["triggered_by"] == "alice"

    def test_pause_workflow_x_user_header_fallback(self):
        """x-user header used when x-authenticated-user absent."""
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.pause_workflow.return_value = self._make_response(wid)

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/pause",
                json={"workflow_id": wid, "operation": "pause"},
                headers={"x-user": "bob"},
            )

        assert response.status_code == 200
        call_kwargs = mock_svc.pause_workflow.call_args[1]
        assert call_kwargs["triggered_by"] == "bob"

    # --- resume ---

    def test_resume_workflow_success(self):
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.resume_workflow.return_value = self._make_response(wid, "resume")

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/resume",
                json={"workflow_id": wid, "operation": "resume"},
            )

        assert response.status_code == 200

    def test_resume_workflow_500_on_exception(self):
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.resume_workflow.side_effect = ValueError("bad state")

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/resume",
                json={"workflow_id": wid, "operation": "resume"},
            )

        assert response.status_code == 500

    # --- cancel ---

    def test_cancel_workflow_success(self):
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.cancel_workflow.return_value = self._make_response(wid, "cancel")

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/cancel",
                json={"workflow_id": wid, "operation": "cancel"},
            )

        assert response.status_code == 200

    def test_cancel_workflow_500_on_exception(self):
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.cancel_workflow.side_effect = RuntimeError("oops")

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/cancel",
                json={"workflow_id": wid, "operation": "cancel"},
            )

        assert response.status_code == 500

    # --- retry ---

    def test_retry_workflow_success(self):
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.retry_workflow.return_value = self._make_response(wid, "retry")

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/retry",
                json={"workflow_id": wid, "operation": "retry", "step_id": "step_1"},
            )

        assert response.status_code == 200
        call_kwargs = mock_svc.retry_workflow.call_args[1]
        assert call_kwargs["step_id"] == "step_1"

    def test_retry_workflow_500_on_exception(self):
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.retry_workflow.side_effect = Exception("retry fail")

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/retry",
                json={"workflow_id": wid, "operation": "retry"},
            )

        assert response.status_code == 500

    # --- dry-run ---

    def test_dry_run_workflow_success(self):
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.dry_run.return_value = self._make_response(wid, "dry_run")

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/dry-run",
                json={"workflow_id": wid, "operation": "dry_run"},
            )

        assert response.status_code == 200
        mock_svc.dry_run.assert_called_once()

    def test_dry_run_workflow_500_on_exception(self):
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.dry_run.side_effect = RuntimeError("simulation error")

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/dry-run",
                json={"workflow_id": wid, "operation": "dry_run"},
            )

        assert response.status_code == 500

    def test_invalid_payload_returns_422(self):
        """Missing required fields should return 422 Unprocessable Entity."""
        from venom_core.api.routes import workflow_operations as mod

        client = _client(mod.router)
        response = client.post("/api/v1/workflow/operations/pause", json={})
        assert response.status_code == 422

    def test_x_admin_user_header_used(self):
        """x-admin-user header is used when other headers absent."""
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.pause_workflow.return_value = self._make_response(wid)

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/pause",
                json={"workflow_id": wid, "operation": "pause"},
                headers={"x-admin-user": "admin"},
            )

        assert response.status_code == 200
        call_kwargs = mock_svc.pause_workflow.call_args[1]
        assert call_kwargs["triggered_by"] == "admin"

    def test_no_user_header_falls_back_to_unknown(self):
        """When no user header present, triggered_by should be 'unknown'."""
        from venom_core.api.routes import workflow_operations as mod

        wid = str(uuid4())
        mock_svc = MagicMock()
        mock_svc.pause_workflow.return_value = self._make_response(wid)

        with patch(
            "venom_core.api.routes.workflow_operations.get_workflow_operation_service",
            return_value=mock_svc,
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/workflow/operations/pause",
                json={"workflow_id": wid, "operation": "pause"},
            )

        assert response.status_code == 200
        call_kwargs = mock_svc.pause_workflow.call_args[1]
        assert call_kwargs["triggered_by"] == "unknown"


# ===========================================================================
# 2. workflow_control.py
# ===========================================================================


class TestWorkflowControl:
    """Contract tests for /api/v1/workflow/control/* endpoints."""

    @pytest.fixture()
    def app_and_client(self):
        from venom_core.api.dependencies import (
            get_control_plane_audit_trail,
            get_control_plane_service,
        )
        from venom_core.api.routes import workflow_control as mod

        mock_service = MagicMock()
        mock_audit = MagicMock()

        app = _make_app(mod.router)
        app.dependency_overrides[get_control_plane_service] = lambda: mock_service
        app.dependency_overrides[get_control_plane_audit_trail] = lambda: mock_audit

        return TestClient(app), mock_service, mock_audit

    # --- plan ---

    def _plan_request_body(self):
        """Valid ControlPlanRequest payload."""
        return {
            "changes": [
                {
                    "resource_type": "config",
                    "resource_id": "AI_MODE",
                    "action": "update",
                    "new_value": "HYBRID",
                }
            ],
            "dry_run": False,
        }

    def _make_plan_response(self):
        """Build a valid ControlPlanResponse instance."""
        from venom_core.api.schemas.workflow_control import (
            CompatibilityReport,
            ControlPlanResponse,
            ReasonCode,
        )

        return ControlPlanResponse(
            execution_ticket="ticket-abc",
            valid=True,
            reason_code=ReasonCode.SUCCESS_HOT_SWAP,
            compatibility_report=CompatibilityReport(compatible=True, issues=[]),
            planned_changes=[],
        )

    def _make_apply_response(self):
        """Build a valid ControlApplyResponse instance."""
        from venom_core.api.schemas.workflow_control import (
            ApplyMode,
            ControlApplyResponse,
            ReasonCode,
        )

        return ControlApplyResponse(
            execution_ticket="ticket-abc",
            apply_mode=ApplyMode.HOT_SWAP,
            reason_code=ReasonCode.OPERATION_COMPLETED,
            message="Applied successfully",
            applied_changes=[],
        )

    def _make_system_state(self):
        """Build a valid SystemState instance."""
        from venom_core.api.schemas.workflow_control import SystemState, WorkflowStatus

        return SystemState(
            timestamp=datetime.now(timezone.utc),
            decision_strategy="sequential",
            intent_mode="simple",
            kernel="standard",
            runtime={"type": "python"},
            provider={"name": "ollama"},
            embedding_model="sentence-transformers",
            workflow_status=WorkflowStatus.IDLE,
        )

    def test_plan_changes_success(self, app_and_client):
        client, mock_svc, _ = app_and_client
        mock_svc.plan_changes.return_value = self._make_plan_response()

        response = client.post(
            "/api/v1/workflow/control/plan",
            json=self._plan_request_body(),
        )
        assert response.status_code == 200
        mock_svc.plan_changes.assert_called_once()

    def test_plan_changes_500_on_exception(self, app_and_client):
        client, mock_svc, _ = app_and_client
        mock_svc.plan_changes.side_effect = RuntimeError("plan error")

        response = client.post(
            "/api/v1/workflow/control/plan",
            json=self._plan_request_body(),
        )
        assert response.status_code == 500
        assert "plan error" in response.json()["detail"]

    def test_plan_passes_user_from_header(self, app_and_client):
        client, mock_svc, _ = app_and_client
        mock_svc.plan_changes.return_value = self._make_plan_response()

        response = client.post(
            "/api/v1/workflow/control/plan",
            json=self._plan_request_body(),
            headers={"x-authenticated-user": "alice"},
        )
        assert response.status_code == 200
        call_kwargs = mock_svc.plan_changes.call_args[1]
        assert call_kwargs["triggered_by"] == "alice"

    def test_plan_invalid_payload_returns_422(self, app_and_client):
        """Missing required fields should return 422 Unprocessable Entity."""
        client, _, _ = app_and_client
        response = client.post("/api/v1/workflow/control/plan", json={})
        assert response.status_code == 422

    # --- apply ---

    def test_apply_changes_success(self, app_and_client):
        client, mock_svc, _ = app_and_client
        mock_svc.apply_changes.return_value = self._make_apply_response()

        response = client.post(
            "/api/v1/workflow/control/apply",
            json={"execution_ticket": "ticket-123"},
        )
        assert response.status_code == 200

    def test_apply_changes_500_on_exception(self, app_and_client):
        client, mock_svc, _ = app_and_client
        mock_svc.apply_changes.side_effect = Exception("apply failed")

        response = client.post(
            "/api/v1/workflow/control/apply",
            json={"execution_ticket": "ticket-abc"},
        )
        assert response.status_code == 500

    # --- state ---

    def test_get_system_state_success(self, app_and_client):
        client, mock_svc, _ = app_and_client
        mock_svc.get_system_state.return_value = self._make_system_state()

        response = client.get("/api/v1/workflow/control/state")
        assert response.status_code == 200
        data = response.json()
        assert "system_state" in data

    def test_get_system_state_500_on_exception(self, app_and_client):
        client, mock_svc, _ = app_and_client
        mock_svc.get_system_state.side_effect = RuntimeError("state error")

        response = client.get("/api/v1/workflow/control/state")
        assert response.status_code == 500

    # --- options ---

    def test_get_control_options_success(self, app_and_client):
        client, mock_svc, _ = app_and_client
        # Must match ControlOptionsResponse fields (providers, embeddings, active required)
        mock_svc.get_control_options.return_value = {
            "providers": {"local": ["ollama"], "cloud": ["openai"]},
            "embeddings": {"local": ["sentence-transformers"], "cloud": []},
            "active": {"provider_source": "local", "embedding_source": "local"},
        }

        response = client.get("/api/v1/workflow/control/options")
        assert response.status_code == 200

    def test_get_control_options_500_on_exception(self, app_and_client):
        client, mock_svc, _ = app_and_client
        mock_svc.get_control_options.side_effect = RuntimeError("options error")

        response = client.get("/api/v1/workflow/control/options")
        assert response.status_code == 500

    # --- audit ---

    def _make_audit_entry(self, i: int = 0):
        """Build an audit entry SimpleNamespace matching AuditEntry schema."""
        from venom_core.api.schemas.workflow_control import ReasonCode, ResourceType

        return SimpleNamespace(
            operation_id=f"op{i}",
            timestamp=datetime.now(timezone.utc),
            triggered_by="alice",
            operation_type="plan",
            resource_type=ResourceType.CONFIG,
            resource_id="AI_MODE",
            params={},
            result="success",
            reason_code=ReasonCode.OPERATION_COMPLETED,
            duration_ms=10.0,
            error_message=None,
        )

    def test_get_audit_trail_success(self, app_and_client):
        client, _, mock_audit = app_and_client
        mock_audit.get_entries.return_value = [self._make_audit_entry(0)]

        response = client.get("/api/v1/workflow/control/audit")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert data["page"] == 1
        assert len(data["entries"]) == 1

    def test_get_audit_trail_pagination(self, app_and_client):
        client, _, mock_audit = app_and_client
        entries = [self._make_audit_entry(i) for i in range(5)]
        mock_audit.get_entries.return_value = entries

        # Page 2 with page_size=2 -> should return entries 2-3
        response = client.get("/api/v1/workflow/control/audit?page=2&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 5
        assert data["page"] == 2
        assert len(data["entries"]) == 2

    def test_get_audit_trail_filters_forwarded(self, app_and_client):
        client, _, mock_audit = app_and_client
        mock_audit.get_entries.return_value = []

        response = client.get(
            "/api/v1/workflow/control/audit?operation_type=plan&triggered_by=alice&result=success"
        )
        assert response.status_code == 200
        call_kwargs = mock_audit.get_entries.call_args[1]
        assert call_kwargs["operation_type"] == "plan"
        assert call_kwargs["triggered_by"] == "alice"
        assert call_kwargs["result"] == "success"

    def test_get_audit_trail_empty_result(self, app_and_client):
        """Empty audit trail should return 200 with zero entries."""
        client, _, mock_audit = app_and_client
        mock_audit.get_entries.return_value = []

        response = client.get("/api/v1/workflow/control/audit")
        assert response.status_code == 200
        assert response.json()["total_count"] == 0

    def test_get_audit_trail_500_on_exception(self, app_and_client):
        client, _, mock_audit = app_and_client
        mock_audit.get_entries.side_effect = RuntimeError("audit db down")

        response = client.get("/api/v1/workflow/control/audit")
        assert response.status_code == 500


# ===========================================================================
# 3. nodes.py
# ===========================================================================


class TestNodes:
    """Contract tests for /api/v1/nodes/* endpoints."""

    @pytest.fixture(autouse=True)
    def _reset_node_manager(self):
        """Reset node manager between tests."""
        from venom_core.api.routes import nodes as mod

        original = mod._node_manager
        yield
        mod._node_manager = original

    def _client_with_manager(self, manager):
        from venom_core.api.routes import nodes as mod

        mod.set_dependencies(manager)
        return _client(mod.router)

    def _client_no_manager(self):
        from venom_core.api.routes import nodes as mod

        mod._node_manager = None
        return _client(mod.router)

    # --- list_nodes ---

    def test_list_nodes_503_when_no_manager(self):
        client = self._client_no_manager()
        response = client.get("/api/v1/nodes")
        assert response.status_code == 503

    def test_list_nodes_success(self):
        node1 = MagicMock(is_online=True)
        node1.to_dict.return_value = {"id": "n1", "is_online": True}
        node2 = MagicMock(is_online=False)
        node2.to_dict.return_value = {"id": "n2", "is_online": False}

        manager = MagicMock()
        manager.list_nodes.return_value = [node1, node2]

        client = self._client_with_manager(manager)
        response = client.get("/api/v1/nodes")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["online_count"] == 1

    def test_list_nodes_online_only_query_param(self):
        manager = MagicMock()
        manager.list_nodes.return_value = []

        client = self._client_with_manager(manager)
        response = client.get("/api/v1/nodes?online_only=true")

        assert response.status_code == 200
        manager.list_nodes.assert_called_once_with(online_only=True)

    def test_list_nodes_500_on_exception(self):
        manager = MagicMock()
        manager.list_nodes.side_effect = RuntimeError("db error")

        client = self._client_with_manager(manager)
        response = client.get("/api/v1/nodes")

        assert response.status_code == 500

    # --- get_node_info ---

    def test_get_node_info_503_when_no_manager(self):
        client = self._client_no_manager()
        response = client.get("/api/v1/nodes/node-1")
        assert response.status_code == 503

    def test_get_node_info_404_when_not_found(self):
        manager = MagicMock()
        manager.get_node.return_value = None

        client = self._client_with_manager(manager)
        response = client.get("/api/v1/nodes/missing-node")

        assert response.status_code == 404

    def test_get_node_info_success(self):
        node = MagicMock()
        node.to_dict.return_value = {"id": "n1", "name": "Node 1"}

        manager = MagicMock()
        manager.get_node.return_value = node

        client = self._client_with_manager(manager)
        response = client.get("/api/v1/nodes/n1")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_node_info_500_on_exception(self):
        manager = MagicMock()
        manager.get_node.side_effect = RuntimeError("node error")

        client = self._client_with_manager(manager)
        response = client.get("/api/v1/nodes/n1")

        assert response.status_code == 500

    # --- execute_on_node ---

    def test_execute_on_node_503_when_no_manager(self):
        client = self._client_no_manager()
        response = client.post(
            "/api/v1/nodes/n1/execute",
            json={"skill_name": "my_skill", "method_name": "run"},
        )
        assert response.status_code == 503

    def test_execute_on_node_404_when_not_found(self):
        manager = MagicMock()
        manager.get_node.return_value = None

        client = self._client_with_manager(manager)
        response = client.post(
            "/api/v1/nodes/missing/execute",
            json={"skill_name": "my_skill", "method_name": "run"},
        )
        assert response.status_code == 404

    def test_execute_on_node_400_when_offline(self):
        node = MagicMock(is_online=False)
        manager = MagicMock()
        manager.get_node.return_value = node

        client = self._client_with_manager(manager)
        response = client.post(
            "/api/v1/nodes/n1/execute",
            json={"skill_name": "my_skill", "method_name": "run"},
        )
        assert response.status_code == 400

    def test_execute_on_node_success(self):
        node = MagicMock(is_online=True)
        manager = MagicMock()
        manager.get_node.return_value = node
        manager.execute_on_node = AsyncMock(return_value={"result": "ok"})

        from venom_core.api.routes import nodes as mod

        mod.set_dependencies(manager)

        client = _client(mod.router)
        response = client.post(
            "/api/v1/nodes/n1/execute",
            json={"skill_name": "my_skill", "method_name": "run", "parameters": {}},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_execute_on_node_504_on_timeout(self):
        node = MagicMock(is_online=True)
        manager = MagicMock()
        manager.get_node.return_value = node
        manager.execute_on_node = AsyncMock(side_effect=TimeoutError())

        from venom_core.api.routes import nodes as mod

        mod.set_dependencies(manager)

        client = _client(mod.router)
        response = client.post(
            "/api/v1/nodes/n1/execute",
            json={"skill_name": "my_skill", "method_name": "run"},
        )
        assert response.status_code == 504

    def test_execute_on_node_500_on_exception(self):
        node = MagicMock(is_online=True)
        manager = MagicMock()
        manager.get_node.return_value = node
        manager.execute_on_node = AsyncMock(side_effect=RuntimeError("exec error"))

        from venom_core.api.routes import nodes as mod

        mod.set_dependencies(manager)

        client = _client(mod.router)
        response = client.post(
            "/api/v1/nodes/n1/execute",
            json={"skill_name": "my_skill", "method_name": "run"},
        )
        assert response.status_code == 500


# ===========================================================================
# 4. queue.py
# ===========================================================================


class TestQueue:
    """Contract tests for /api/v1/queue/* endpoints."""

    @pytest.fixture(autouse=True)
    def _reset_queue(self):
        from venom_core.api.routes import queue as mod
        from venom_core.utils.ttl_cache import TTLCache

        original = mod._orchestrator
        mod._queue_cache = TTLCache(ttl_seconds=1.0)
        yield
        mod._orchestrator = original
        mod._queue_cache = TTLCache(ttl_seconds=1.0)

    def _client_with_orchestrator(self, orchestrator):
        from venom_core.api.routes import queue as mod

        mod.set_dependencies(orchestrator)
        return _client(mod.router)

    def _client_no_orchestrator(self):
        from venom_core.api.routes import queue as mod

        mod._orchestrator = None
        return _client(mod.router)

    # --- status ---

    def test_queue_status_503_when_no_orchestrator(self):
        client = self._client_no_orchestrator()
        response = client.get("/api/v1/queue/status")
        assert response.status_code == 503

    def test_queue_status_success(self):
        orchestrator = MagicMock()
        orchestrator.get_queue_status.return_value = {
            "paused": False,
            "pending": 3,
            "active": 1,
            "limit": 10,
        }

        client = self._client_with_orchestrator(orchestrator)
        response = client.get("/api/v1/queue/status")

        assert response.status_code == 200
        assert response.json()["pending"] == 3

    def test_queue_status_cached(self):
        """Second call should use TTL cache."""
        from venom_core.api.routes import queue as mod
        from venom_core.utils.ttl_cache import TTLCache

        mod._queue_cache = TTLCache(ttl_seconds=60.0)

        orchestrator = MagicMock()
        orchestrator.get_queue_status.return_value = {"paused": False, "pending": 0}
        mod.set_dependencies(orchestrator)

        client = _client(mod.router)
        client.get("/api/v1/queue/status")
        client.get("/api/v1/queue/status")

        # Should only call underlying once (second is cached)
        assert orchestrator.get_queue_status.call_count == 1

    def test_queue_status_500_on_exception(self):
        orchestrator = MagicMock()
        orchestrator.get_queue_status.side_effect = RuntimeError("db down")

        client = self._client_with_orchestrator(orchestrator)
        response = client.get("/api/v1/queue/status")

        assert response.status_code == 500

    # --- pause ---

    def test_pause_queue_503_when_no_orchestrator(self):
        client = self._client_no_orchestrator()
        response = client.post("/api/v1/queue/pause")
        assert response.status_code == 503

    def test_pause_queue_success(self):
        orchestrator = MagicMock()
        orchestrator.pause_queue = AsyncMock(return_value={"success": True})

        client = self._client_with_orchestrator(orchestrator)
        response = client.post("/api/v1/queue/pause")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_pause_queue_500_on_exception(self):
        orchestrator = MagicMock()
        orchestrator.pause_queue = AsyncMock(side_effect=RuntimeError("fail"))

        client = self._client_with_orchestrator(orchestrator)
        response = client.post("/api/v1/queue/pause")

        assert response.status_code == 500

    # --- resume ---

    def test_resume_queue_503_when_no_orchestrator(self):
        client = self._client_no_orchestrator()
        response = client.post("/api/v1/queue/resume")
        assert response.status_code == 503

    def test_resume_queue_success(self):
        orchestrator = MagicMock()
        orchestrator.resume_queue = AsyncMock(return_value={"success": True})

        client = self._client_with_orchestrator(orchestrator)
        response = client.post("/api/v1/queue/resume")

        assert response.status_code == 200

    def test_resume_queue_500_on_exception(self):
        orchestrator = MagicMock()
        orchestrator.resume_queue = AsyncMock(side_effect=RuntimeError("fail"))

        client = self._client_with_orchestrator(orchestrator)
        response = client.post("/api/v1/queue/resume")

        assert response.status_code == 500

    # --- purge ---

    def test_purge_queue_503_when_no_orchestrator(self):
        client = self._client_no_orchestrator()
        response = client.post("/api/v1/queue/purge")
        assert response.status_code == 503

    def test_purge_queue_success(self):
        orchestrator = MagicMock()
        orchestrator.purge_queue = AsyncMock(
            return_value={"success": True, "removed": 5}
        )

        client = self._client_with_orchestrator(orchestrator)
        response = client.post("/api/v1/queue/purge")

        assert response.status_code == 200

    def test_purge_queue_500_on_exception(self):
        orchestrator = MagicMock()
        orchestrator.purge_queue = AsyncMock(side_effect=RuntimeError("purge fail"))

        client = self._client_with_orchestrator(orchestrator)
        response = client.post("/api/v1/queue/purge")

        assert response.status_code == 500

    # --- emergency-stop ---

    def test_emergency_stop_503_when_no_orchestrator(self):
        client = self._client_no_orchestrator()
        response = client.post("/api/v1/queue/emergency-stop")
        assert response.status_code == 503

    def test_emergency_stop_success(self):
        orchestrator = MagicMock()
        orchestrator.emergency_stop = AsyncMock(
            return_value={"success": True, "cancelled": 3}
        )

        client = self._client_with_orchestrator(orchestrator)
        response = client.post("/api/v1/queue/emergency-stop")

        assert response.status_code == 200

    def test_emergency_stop_500_on_exception(self):
        orchestrator = MagicMock()
        orchestrator.emergency_stop = AsyncMock(side_effect=RuntimeError("stop fail"))

        client = self._client_with_orchestrator(orchestrator)
        response = client.post("/api/v1/queue/emergency-stop")

        assert response.status_code == 500

    # --- abort task ---

    def test_abort_task_503_when_no_orchestrator(self):
        client = self._client_no_orchestrator()
        response = client.post(f"/api/v1/queue/task/{uuid4()}/abort")
        assert response.status_code == 503

    def test_abort_task_success(self):
        task_id = uuid4()
        orchestrator = MagicMock()
        orchestrator.abort_task = AsyncMock(
            return_value={"success": True, "message": "aborted"}
        )

        client = self._client_with_orchestrator(orchestrator)
        response = client.post(f"/api/v1/queue/task/{task_id}/abort")

        assert response.status_code == 200

    def test_abort_task_404_when_not_found(self):
        task_id = uuid4()
        orchestrator = MagicMock()
        orchestrator.abort_task = AsyncMock(
            return_value={"success": False, "message": "task not active"}
        )

        client = self._client_with_orchestrator(orchestrator)
        response = client.post(f"/api/v1/queue/task/{task_id}/abort")

        assert response.status_code == 404

    def test_abort_task_500_on_exception(self):
        task_id = uuid4()
        orchestrator = MagicMock()
        orchestrator.abort_task = AsyncMock(side_effect=RuntimeError("abort fail"))

        client = self._client_with_orchestrator(orchestrator)
        response = client.post(f"/api/v1/queue/task/{task_id}/abort")

        assert response.status_code == 500


# ===========================================================================
# 5. agents.py
# ===========================================================================


class TestAgents:
    """Contract tests for agent status/control endpoints."""

    @pytest.fixture(autouse=True)
    def _reset_agents(self):
        from venom_core.api.routes import agents as mod

        originals = (
            mod._gardener_agent,
            mod._shadow_agent,
            mod._file_watcher,
            mod._documenter_agent,
            mod._orchestrator,
        )
        yield
        (
            mod._gardener_agent,
            mod._shadow_agent,
            mod._file_watcher,
            mod._documenter_agent,
            mod._orchestrator,
        ) = originals

    def _setup_all(
        self,
        gardener=None,
        shadow=None,
        watcher=None,
        documenter=None,
        orchestrator=None,
    ):
        from venom_core.api.routes import agents as mod

        mod.set_dependencies(gardener, shadow, watcher, documenter, orchestrator)
        return _client(mod.router)

    # --- gardener ---

    def test_gardener_status_503_when_unavailable(self):
        client = self._setup_all()
        response = client.get("/api/v1/gardener/status")
        assert response.status_code == 503

    def test_gardener_status_success(self):
        gardener = MagicMock()
        gardener.get_status.return_value = {"running": True}

        client = self._setup_all(gardener=gardener)
        response = client.get("/api/v1/gardener/status")

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_gardener_status_500_on_exception(self):
        gardener = MagicMock()
        gardener.get_status.side_effect = RuntimeError("gardener crash")

        client = self._setup_all(gardener=gardener)
        response = client.get("/api/v1/gardener/status")

        assert response.status_code == 500

    # --- watcher ---

    def test_watcher_status_503_when_unavailable(self):
        client = self._setup_all()
        response = client.get("/api/v1/watcher/status")
        assert response.status_code == 503

    def test_watcher_status_success(self):
        watcher = MagicMock()
        watcher.get_status.return_value = {"watching": ["/some/path"]}

        client = self._setup_all(watcher=watcher)
        response = client.get("/api/v1/watcher/status")

        assert response.status_code == 200

    def test_watcher_status_500_on_exception(self):
        watcher = MagicMock()
        watcher.get_status.side_effect = RuntimeError("watcher crash")

        client = self._setup_all(watcher=watcher)
        response = client.get("/api/v1/watcher/status")

        assert response.status_code == 500

    # --- documenter ---

    def test_documenter_status_503_when_unavailable(self):
        client = self._setup_all()
        response = client.get("/api/v1/documenter/status")
        assert response.status_code == 503

    def test_documenter_status_success(self):
        documenter = MagicMock()
        documenter.get_status.return_value = {"docs_generated": 42}

        client = self._setup_all(documenter=documenter)
        response = client.get("/api/v1/documenter/status")

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_documenter_status_500_on_exception(self):
        documenter = MagicMock()
        documenter.get_status.side_effect = RuntimeError("doc crash")

        client = self._setup_all(documenter=documenter)
        response = client.get("/api/v1/documenter/status")

        assert response.status_code == 500

    # --- shadow ---

    def test_shadow_status_disabled_when_no_agent(self):
        client = self._setup_all()
        response = client.get("/api/v1/shadow/status")

        assert response.status_code == 200
        assert response.json()["status"] == "disabled"

    def test_shadow_status_success(self):
        shadow = MagicMock()
        shadow.get_status.return_value = {"active": True}

        client = self._setup_all(shadow=shadow)
        response = client.get("/api/v1/shadow/status")

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_shadow_status_500_on_exception(self):
        shadow = MagicMock()
        shadow.get_status.side_effect = RuntimeError("shadow crash")

        client = self._setup_all(shadow=shadow)
        response = client.get("/api/v1/shadow/status")

        assert response.status_code == 500

    # --- shadow reject ---

    def test_reject_shadow_503_when_no_shadow_agent(self):
        client = self._setup_all(orchestrator=MagicMock())
        response = client.post(
            "/api/v1/shadow/reject", json={"content": "suggestion text"}
        )
        assert response.status_code == 503

    def test_reject_shadow_503_when_no_orchestrator(self):
        shadow = MagicMock()
        client = self._setup_all(shadow=shadow)
        response = client.post(
            "/api/v1/shadow/reject", json={"content": "suggestion text"}
        )
        assert response.status_code == 503

    def test_reject_shadow_success(self):
        shadow = MagicMock()
        orchestrator = MagicMock()

        client = self._setup_all(shadow=shadow, orchestrator=orchestrator)
        response = client.post(
            "/api/v1/shadow/reject", json={"content": "bad suggestion"}
        )

        assert response.status_code == 200
        shadow.reject_suggestion.assert_called_once_with("bad suggestion")

    def test_reject_shadow_500_on_exception(self):
        shadow = MagicMock()
        shadow.reject_suggestion.side_effect = RuntimeError("reject error")
        orchestrator = MagicMock()

        client = self._setup_all(shadow=shadow, orchestrator=orchestrator)
        response = client.post(
            "/api/v1/shadow/reject", json={"content": "bad suggestion"}
        )

        assert response.status_code == 500


# ===========================================================================
# 6. system_scheduler.py
# ===========================================================================


class TestSystemScheduler:
    """Contract tests for /api/v1/scheduler/* endpoints."""

    @pytest.fixture(autouse=True)
    def _patch_system_deps(self):
        from venom_core.api.routes import system_deps

        original = system_deps._background_scheduler
        yield
        system_deps._background_scheduler = original

    def _client_with_scheduler(self, scheduler):
        from venom_core.api.routes import system_deps
        from venom_core.api.routes import system_scheduler as mod

        system_deps._background_scheduler = scheduler
        return _client(mod.router)

    def _client_no_scheduler(self):
        from venom_core.api.routes import system_deps
        from venom_core.api.routes import system_scheduler as mod

        system_deps._background_scheduler = None
        return _client(mod.router)

    # --- status ---

    def test_scheduler_status_503_when_unavailable(self):
        client = self._client_no_scheduler()
        response = client.get("/api/v1/scheduler/status")
        assert response.status_code == 503

    def test_scheduler_status_success(self):
        scheduler = MagicMock()
        scheduler.get_status.return_value = {"running": True, "jobs": 2}

        client = self._client_with_scheduler(scheduler)
        response = client.get("/api/v1/scheduler/status")

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_scheduler_status_500_on_exception(self):
        scheduler = MagicMock()
        scheduler.get_status.side_effect = RuntimeError("sched error")

        client = self._client_with_scheduler(scheduler)
        response = client.get("/api/v1/scheduler/status")

        assert response.status_code == 500

    # --- jobs ---

    def test_scheduler_jobs_503_when_unavailable(self):
        client = self._client_no_scheduler()
        response = client.get("/api/v1/scheduler/jobs")
        assert response.status_code == 503

    def test_scheduler_jobs_success(self):
        scheduler = MagicMock()
        scheduler.get_jobs.return_value = [{"id": "j1"}, {"id": "j2"}]

        client = self._client_with_scheduler(scheduler)
        response = client.get("/api/v1/scheduler/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2

    def test_scheduler_jobs_500_on_exception(self):
        scheduler = MagicMock()
        scheduler.get_jobs.side_effect = RuntimeError("jobs error")

        client = self._client_with_scheduler(scheduler)
        response = client.get("/api/v1/scheduler/jobs")

        assert response.status_code == 500

    # --- pause scheduler ---

    def test_pause_scheduler_503_when_unavailable(self):
        client = self._client_no_scheduler()
        response = client.post("/api/v1/scheduler/pause")
        assert response.status_code == 503

    def test_pause_scheduler_success(self):
        scheduler = MagicMock()
        scheduler.pause_all_jobs = AsyncMock()

        client = self._client_with_scheduler(scheduler)
        response = client.post("/api/v1/scheduler/pause")

        assert response.status_code == 200
        assert "paused" in response.json()["message"].lower()

    def test_pause_scheduler_500_on_exception(self):
        scheduler = MagicMock()
        scheduler.pause_all_jobs = AsyncMock(side_effect=RuntimeError("pause fail"))

        client = self._client_with_scheduler(scheduler)
        response = client.post("/api/v1/scheduler/pause")

        assert response.status_code == 500

    # --- resume scheduler ---

    def test_resume_scheduler_503_when_unavailable(self):
        client = self._client_no_scheduler()
        response = client.post("/api/v1/scheduler/resume")
        assert response.status_code == 503

    def test_resume_scheduler_success(self):
        scheduler = MagicMock()
        scheduler.resume_all_jobs = AsyncMock()

        client = self._client_with_scheduler(scheduler)
        response = client.post("/api/v1/scheduler/resume")

        assert response.status_code == 200
        assert "resumed" in response.json()["message"].lower()

    def test_resume_scheduler_500_on_exception(self):
        scheduler = MagicMock()
        scheduler.resume_all_jobs = AsyncMock(side_effect=RuntimeError("resume fail"))

        client = self._client_with_scheduler(scheduler)
        response = client.post("/api/v1/scheduler/resume")

        assert response.status_code == 500


# ===========================================================================
# 7. system_governance.py
# ===========================================================================


class TestSystemGovernance:
    """Contract tests for /api/v1/system/cost-mode and /system/autonomy endpoints."""

    @pytest.fixture(autouse=True)
    def _patch_deps(self):
        from venom_core.api.routes import system_deps

        original_sm = system_deps._state_manager
        yield
        system_deps._state_manager = original_sm

    def _client_with_state_manager(self, sm):
        from venom_core.api.routes import system_deps
        from venom_core.api.routes import system_governance as mod

        system_deps._state_manager = sm
        return _client(mod.router)

    def _client_no_state_manager(self):
        from venom_core.api.routes import system_deps
        from venom_core.api.routes import system_governance as mod

        system_deps._state_manager = None
        return _client(mod.router)

    # --- cost mode get ---

    def test_get_cost_mode_503_when_no_state_manager(self):
        client = self._client_no_state_manager()
        response = client.get("/api/v1/system/cost-mode")
        assert response.status_code == 503

    def test_get_cost_mode_success(self):
        sm = MagicMock()
        sm.is_paid_mode_enabled.return_value = False

        client = self._client_with_state_manager(sm)
        response = client.get("/api/v1/system/cost-mode")

        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_get_cost_mode_500_on_exception(self):
        sm = MagicMock()
        sm.is_paid_mode_enabled.side_effect = RuntimeError("sm error")

        client = self._client_with_state_manager(sm)
        response = client.get("/api/v1/system/cost-mode")

        assert response.status_code == 500

    # --- cost mode set ---

    def test_set_cost_mode_503_when_no_state_manager(self):
        client = self._client_no_state_manager()
        response = client.post("/api/v1/system/cost-mode", json={"enable": True})
        assert response.status_code == 503

    def test_set_cost_mode_enable(self):
        sm = MagicMock()
        client = self._client_with_state_manager(sm)

        response = client.post("/api/v1/system/cost-mode", json={"enable": True})

        assert response.status_code == 200
        sm.enable_paid_mode.assert_called_once()
        assert response.json()["enabled"] is True

    def test_set_cost_mode_disable(self):
        sm = MagicMock()
        client = self._client_with_state_manager(sm)

        response = client.post("/api/v1/system/cost-mode", json={"enable": False})

        assert response.status_code == 200
        sm.disable_paid_mode.assert_called_once()
        assert response.json()["enabled"] is False

    def test_set_cost_mode_500_on_exception(self):
        sm = MagicMock()
        sm.enable_paid_mode.side_effect = RuntimeError("enable fail")

        client = self._client_with_state_manager(sm)
        response = client.post("/api/v1/system/cost-mode", json={"enable": True})

        assert response.status_code == 500

    # --- autonomy get ---

    def test_get_autonomy_level_success(self):
        from venom_core.api.routes import system_governance as mod

        level_info = SimpleNamespace(
            name="SUPERVISED",
            color="#FFA500",
            color_name="orange",
            description="Supervised mode",
            permissions={"read": True, "write": False},  # dict, not list
            risk_level="low",  # str, not int
        )

        with (
            patch.object(mod.permission_guard, "get_current_level", return_value=10),
            patch.object(
                mod.permission_guard, "get_level_info", return_value=level_info
            ),
        ):
            client = _client(mod.router)
            response = client.get("/api/v1/system/autonomy")

        assert response.status_code == 200
        data = response.json()
        assert data["current_level"] == 10
        assert data["current_level_name"] == "SUPERVISED"

    def test_get_autonomy_level_500_when_no_level_info(self):
        from venom_core.api.routes import system_governance as mod

        with (
            patch.object(mod.permission_guard, "get_current_level", return_value=99),
            patch.object(mod.permission_guard, "get_level_info", return_value=None),
        ):
            client = _client(mod.router)
            response = client.get("/api/v1/system/autonomy")

        assert response.status_code == 500

    def test_get_autonomy_level_500_on_exception(self):
        from venom_core.api.routes import system_governance as mod

        with patch.object(
            mod.permission_guard,
            "get_current_level",
            side_effect=RuntimeError("level error"),
        ):
            client = _client(mod.router)
            response = client.get("/api/v1/system/autonomy")

        assert response.status_code == 500

    # --- autonomy set ---

    def test_set_autonomy_level_success(self):
        from venom_core.api.routes import system_governance as mod

        level_info = SimpleNamespace(
            name="SUPERVISED",
            color="#FFA500",
            permissions={"read": True},  # dict, not list
        )

        with (
            patch.object(mod.permission_guard, "set_level", return_value=True),
            patch.object(
                mod.permission_guard, "get_level_info", return_value=level_info
            ),
        ):
            client = _client(mod.router)
            response = client.post("/api/v1/system/autonomy", json={"level": 10})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["level"] == 10

    def test_set_autonomy_level_400_on_invalid(self):
        from venom_core.api.routes import system_governance as mod

        with patch.object(mod.permission_guard, "set_level", return_value=False):
            client = _client(mod.router)
            response = client.post("/api/v1/system/autonomy", json={"level": 99})

        assert response.status_code == 400

    def test_set_autonomy_level_500_when_no_level_info_after_set(self):
        from venom_core.api.routes import system_governance as mod

        with (
            patch.object(mod.permission_guard, "set_level", return_value=True),
            patch.object(mod.permission_guard, "get_level_info", return_value=None),
        ):
            client = _client(mod.router)
            response = client.post("/api/v1/system/autonomy", json={"level": 10})

        assert response.status_code == 500

    def test_set_autonomy_level_500_on_exception(self):
        from venom_core.api.routes import system_governance as mod

        with patch.object(
            mod.permission_guard, "set_level", side_effect=RuntimeError("set fail")
        ):
            client = _client(mod.router)
            response = client.post("/api/v1/system/autonomy", json={"level": 10})

        assert response.status_code == 500

    def test_extract_actor_from_request_prefers_state_user_and_header_fallback(self):
        from venom_core.api.routes import system_governance as mod

        class _StateRequest:
            state = SimpleNamespace(user="state-actor")
            headers = {"X-Actor": "header-actor", "X-User-Id": "user-id"}

        class _HeaderRequest:
            state = SimpleNamespace(user=None)
            headers = {"X-User-Id": "user-id-only"}

        assert mod._extract_actor_from_request(_StateRequest()) == "state-actor"
        assert mod._extract_actor_from_request(_HeaderRequest()) == "user-id-only"

    def test_extract_actor_from_request_handles_exception(self):
        from venom_core.api.routes import system_governance as mod

        class _BrokenRequest:
            @property
            def state(self):
                raise RuntimeError("broken-state")

        assert mod._extract_actor_from_request(_BrokenRequest()) == "unknown"

    # --- autonomy levels list ---

    def test_get_all_autonomy_levels_success(self):
        from venom_core.api.routes import system_governance as mod

        level_obj = SimpleNamespace(
            id=0,
            name="ISOLATED",
            description="Isolated",
            color="#FF0000",
            color_name="red",
            permissions=[],
            risk_level=0,
            examples=[],
        )
        fake_levels = {0: level_obj}

        with patch.object(
            mod.permission_guard, "get_all_levels", return_value=fake_levels
        ):
            client = _client(mod.router)
            response = client.get("/api/v1/system/autonomy/levels")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["levels"][0]["name"] == "ISOLATED"

    def test_get_all_autonomy_levels_500_on_exception(self):
        from venom_core.api.routes import system_governance as mod

        with patch.object(
            mod.permission_guard,
            "get_all_levels",
            side_effect=RuntimeError("levels error"),
        ):
            client = _client(mod.router)
            response = client.get("/api/v1/system/autonomy/levels")

        assert response.status_code == 500


# ===========================================================================
# 8. system_config.py
# ===========================================================================


class TestSystemConfig:
    """Contract tests for /api/v1/config/* endpoints."""

    @pytest.fixture(autouse=True)
    def _patch_config_manager(self):
        """Patch config_manager to avoid real file I/O."""
        from venom_core.api.routes import system_config as mod

        self.mock_cm = MagicMock()
        self.mock_cm.get_effective_config_with_sources.return_value = (
            {"AI_MODE": "LOCAL"},
            {"AI_MODE": ".env"},
        )
        self.mock_cm.update_config.return_value = {
            "success": True,
            "message": "Updated",
            "changed_keys": ["AI_MODE"],
        }
        self.mock_cm.get_backup_list.return_value = [
            {"filename": "backup1.env", "date": "2024-01-01"}
        ]
        self.mock_cm.restore_backup.return_value = {
            "success": True,
            "message": "Restored",
        }

        with patch.object(mod, "config_manager", self.mock_cm):
            yield

    def _client_patched(self):
        """Create a TestClient with require_localhost_request patched out."""
        from venom_core.api.routes import system_config as mod

        # TestClient sends requests with host="testclient" which is NOT in the
        # localhost allowlist. We patch the guard to be a no-op for these tests.
        app = _make_app(mod.router)
        with patch.object(mod, "require_localhost_request", return_value=None):
            yield TestClient(app)

    # --- get runtime config ---

    def test_get_runtime_config_success(self):
        from venom_core.api.routes import system_config as mod

        with patch.object(mod, "config_manager", self.mock_cm):
            client = _client(mod.router)
            response = client.get("/api/v1/config/runtime")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "config" in data

    def test_get_runtime_config_500_on_exception(self):
        from venom_core.api.routes import system_config as mod

        mock_cm = MagicMock()
        mock_cm.get_effective_config_with_sources.side_effect = RuntimeError(
            "config error"
        )

        with patch.object(mod, "config_manager", mock_cm):
            client = _client(mod.router)
            response = client.get("/api/v1/config/runtime")

        assert response.status_code == 500

    # --- update runtime config ---

    def test_update_runtime_config_success(self):
        """Verify update config succeeds when localhost check is bypassed."""
        from venom_core.api.routes import system_config as mod

        with (
            patch.object(mod, "config_manager", self.mock_cm),
            patch.object(mod, "require_localhost_request", return_value=None),
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/config/runtime",
                json={"updates": {"AI_MODE": "HYBRID"}},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "AI_MODE" in data["updated_keys"]

    def test_update_runtime_config_403_for_remote_host(self):
        """Verify require_localhost_request raises 403 for non-local IPs."""
        from fastapi import HTTPException

        from venom_core.api.routes.system_config import require_localhost_request

        mock_req = MagicMock()
        mock_req.client = SimpleNamespace(host="192.168.1.100")
        with pytest.raises(HTTPException) as exc_info:
            require_localhost_request(mock_req)
        assert exc_info.value.status_code == 403

    def test_update_runtime_config_500_on_exception(self):
        from venom_core.api.routes import system_config as mod

        mock_cm = MagicMock()
        mock_cm.update_config.side_effect = RuntimeError("update error")

        with (
            patch.object(mod, "config_manager", mock_cm),
            patch.object(mod, "require_localhost_request", return_value=None),
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/config/runtime",
                json={"updates": {"AI_MODE": "HYBRID"}},
            )

        assert response.status_code == 500

    # --- get config backups ---

    def test_get_config_backups_success(self):
        from venom_core.api.routes import system_config as mod

        with (
            patch.object(mod, "config_manager", self.mock_cm),
            patch.object(mod, "require_localhost_request", return_value=None),
        ):
            client = _client(mod.router)
            response = client.get("/api/v1/config/backups")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["count"] == 1

    def test_get_config_backups_with_limit(self):
        from venom_core.api.routes import system_config as mod

        with (
            patch.object(mod, "config_manager", self.mock_cm),
            patch.object(mod, "require_localhost_request", return_value=None),
        ):
            client = _client(mod.router)
            response = client.get("/api/v1/config/backups?limit=5")

        assert response.status_code == 200
        self.mock_cm.get_backup_list.assert_called_once_with(limit=5)

    def test_get_config_backups_500_on_exception(self):
        from venom_core.api.routes import system_config as mod

        mock_cm = MagicMock()
        mock_cm.get_backup_list.side_effect = RuntimeError("backup list error")

        with (
            patch.object(mod, "config_manager", mock_cm),
            patch.object(mod, "require_localhost_request", return_value=None),
        ):
            client = _client(mod.router)
            response = client.get("/api/v1/config/backups")

        assert response.status_code == 500

    # --- restore config backup ---

    def test_restore_config_backup_success(self):
        from venom_core.api.routes import system_config as mod

        with (
            patch.object(mod, "config_manager", self.mock_cm),
            patch.object(mod, "require_localhost_request", return_value=None),
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/config/restore",
                json={"backup_filename": "backup1.env"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["restored_file"] == "backup1.env"

    def test_restore_config_backup_500_on_exception(self):
        from venom_core.api.routes import system_config as mod

        mock_cm = MagicMock()
        mock_cm.restore_backup.side_effect = RuntimeError("restore error")

        with (
            patch.object(mod, "config_manager", mock_cm),
            patch.object(mod, "require_localhost_request", return_value=None),
        ):
            client = _client(mod.router)
            response = client.post(
                "/api/v1/config/restore",
                json={"backup_filename": "backup1.env"},
            )

        assert response.status_code == 500

    def test_require_localhost_request_allows_127_0_0_1(self):
        """Test require_localhost_request passes for 127.0.0.1."""
        from venom_core.api.routes.system_config import require_localhost_request

        mock_req = MagicMock()
        mock_req.client = SimpleNamespace(host="127.0.0.1")
        # Should not raise — returns None on success
        result = require_localhost_request(mock_req)
        assert result is None

    def test_require_localhost_request_allows_ipv6_localhost(self):
        """Test require_localhost_request passes for ::1."""
        from venom_core.api.routes.system_config import require_localhost_request

        mock_req = MagicMock()
        mock_req.client = SimpleNamespace(host="::1")
        result = require_localhost_request(mock_req)
        assert result is None

    def test_require_localhost_request_allows_named_localhost(self):
        """Test require_localhost_request passes for 'localhost'."""
        from venom_core.api.routes.system_config import require_localhost_request

        mock_req = MagicMock()
        mock_req.client = SimpleNamespace(host="localhost")
        result = require_localhost_request(mock_req)
        assert result is None

    def test_require_localhost_request_denies_remote(self):
        """Test require_localhost_request raises 403 for remote IPs."""
        from fastapi import HTTPException

        from venom_core.api.routes.system_config import require_localhost_request

        mock_req = MagicMock()
        mock_req.client = SimpleNamespace(host="10.0.0.1")
        with pytest.raises(HTTPException) as exc_info:
            require_localhost_request(mock_req)
        assert exc_info.value.status_code == 403

    def test_require_localhost_request_denies_no_client(self):
        """Test require_localhost_request raises 403 when client is None."""
        from fastapi import HTTPException

        from venom_core.api.routes.system_config import require_localhost_request

        mock_req = MagicMock()
        mock_req.client = None
        with pytest.raises(HTTPException) as exc_info:
            require_localhost_request(mock_req)
        assert exc_info.value.status_code == 403
