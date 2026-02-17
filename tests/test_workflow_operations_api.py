"""Integration tests for Workflow Operations API endpoints."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from venom_core.api.model_schemas.workflow_control import (
    WorkflowOperation,
    WorkflowStatus,
)
from venom_core.main import app


@pytest.fixture
def client():
    """Fixture for FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture
def workflow_id():
    """Generate a workflow ID."""
    return str(uuid4())


class TestPauseEndpoint:
    """Test /api/v1/workflow/operations/pause endpoint."""

    def test_pause_running_workflow(self, client, workflow_id):
        """Test pausing a running workflow via API."""
        # First, manually set workflow to RUNNING state
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Now pause via API
        request = {"workflow_id": workflow_id, "operation": "pause", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/pause", json=request)

        assert response.status_code == 200
        data = response.json()

        assert data["workflow_id"] == workflow_id
        assert data["operation"] == WorkflowOperation.PAUSE.value
        assert data["status"] == WorkflowStatus.PAUSED.value
        assert "successfully" in data["message"].lower()

    def test_pause_idle_workflow_returns_error(self, client, workflow_id):
        """Test that pausing IDLE workflow returns proper error response."""
        request = {"workflow_id": workflow_id, "operation": "pause", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/pause", json=request)

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == WorkflowStatus.IDLE.value
        assert data["reason_code"] == "forbidden_transition"


class TestResumeEndpoint:
    """Test /api/v1/workflow/operations/resume endpoint."""

    def test_resume_paused_workflow(self, client, workflow_id):
        """Test resuming a paused workflow via API."""
        # Set workflow to PAUSED state
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.PAUSED.value

        # Resume via API
        request = {"workflow_id": workflow_id, "operation": "resume", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/resume", json=request)

        assert response.status_code == 200
        data = response.json()

        assert data["workflow_id"] == workflow_id
        assert data["operation"] == WorkflowOperation.RESUME.value
        assert data["status"] == WorkflowStatus.RUNNING.value

    def test_resume_running_workflow_returns_error(self, client, workflow_id):
        """Test that resuming RUNNING workflow returns error."""
        # Set workflow to RUNNING state
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        request = {"workflow_id": workflow_id, "operation": "resume", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/resume", json=request)

        assert response.status_code == 200
        data = response.json()
        assert data["reason_code"] == "forbidden_transition"


class TestCancelEndpoint:
    """Test /api/v1/workflow/operations/cancel endpoint."""

    def test_cancel_running_workflow(self, client, workflow_id):
        """Test cancelling a running workflow via API."""
        # Set workflow to RUNNING state
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Cancel via API
        request = {"workflow_id": workflow_id, "operation": "cancel", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/cancel", json=request)

        assert response.status_code == 200
        data = response.json()

        assert data["workflow_id"] == workflow_id
        assert data["operation"] == WorkflowOperation.CANCEL.value
        assert data["status"] == WorkflowStatus.CANCELLED.value

    def test_cancel_paused_workflow(self, client, workflow_id):
        """Test cancelling a paused workflow."""
        # Set workflow to PAUSED state
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.PAUSED.value

        request = {"workflow_id": workflow_id, "operation": "cancel", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/cancel", json=request)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == WorkflowStatus.CANCELLED.value


class TestRetryEndpoint:
    """Test /api/v1/workflow/operations/retry endpoint."""

    def test_retry_failed_workflow(self, client, workflow_id):
        """Test retrying a failed workflow via API."""
        # Set workflow to FAILED state
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.FAILED.value

        # Retry via API
        request = {"workflow_id": workflow_id, "operation": "retry", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/retry", json=request)

        assert response.status_code == 200
        data = response.json()

        assert data["workflow_id"] == workflow_id
        assert data["operation"] == WorkflowOperation.RETRY.value
        assert data["status"] == WorkflowStatus.RUNNING.value

    def test_retry_from_specific_step(self, client, workflow_id):
        """Test retrying from a specific step."""
        # Set workflow to FAILED state
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.FAILED.value

        # Retry from specific step
        request = {
            "workflow_id": workflow_id,
            "operation": "retry",
            "step_id": "step_5",
            "metadata": {},
        }

        response = client.post("/api/v1/workflow/operations/retry", json=request)

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == WorkflowStatus.RUNNING.value
        assert data["metadata"]["step_id"] == "step_5"

    def test_retry_cancelled_workflow(self, client, workflow_id):
        """Test retrying a cancelled workflow."""
        # Set workflow to CANCELLED state
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.CANCELLED.value

        request = {"workflow_id": workflow_id, "operation": "retry", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/retry", json=request)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == WorkflowStatus.RUNNING.value


class TestDryRunEndpoint:
    """Test /api/v1/workflow/operations/dry-run endpoint."""

    def test_dry_run_execution(self, client, workflow_id):
        """Test dry-run execution via API."""
        request = {"workflow_id": workflow_id, "operation": "dry_run", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/dry-run", json=request)

        assert response.status_code == 200
        data = response.json()

        assert data["workflow_id"] == workflow_id
        assert data["operation"] == WorkflowOperation.DRY_RUN.value
        assert data["metadata"]["dry_run"] is True
        assert "no changes" in data["message"].lower()

    def test_dry_run_does_not_change_state(self, client, workflow_id):
        """Test that dry-run doesn't change workflow state."""
        # Set workflow to RUNNING state
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Perform dry-run
        request = {"workflow_id": workflow_id, "operation": "dry_run", "metadata": {}}

        response = client.post("/api/v1/workflow/operations/dry-run", json=request)

        assert response.status_code == 200
        data = response.json()

        # State should still be RUNNING
        assert data["status"] == WorkflowStatus.RUNNING.value
        assert service.get_workflow_status(workflow_id) == WorkflowStatus.RUNNING


class TestWorkflowOperationsIntegration:
    """Test integrated workflow operation scenarios."""

    def test_full_pause_resume_workflow(self, client, workflow_id):
        """Test full pause/resume cycle via API."""
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()

        # Start workflow
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Pause
        pause_request = {
            "workflow_id": workflow_id,
            "operation": "pause",
            "metadata": {},
        }
        pause_response = client.post(
            "/api/v1/workflow/operations/pause", json=pause_request
        )
        assert pause_response.status_code == 200
        assert pause_response.json()["status"] == WorkflowStatus.PAUSED.value

        # Resume
        resume_request = {
            "workflow_id": workflow_id,
            "operation": "resume",
            "metadata": {},
        }
        resume_response = client.post(
            "/api/v1/workflow/operations/resume", json=resume_request
        )
        assert resume_response.status_code == 200
        assert resume_response.json()["status"] == WorkflowStatus.RUNNING.value

    def test_workflow_with_metadata(self, client, workflow_id):
        """Test workflow operations with metadata tracking."""
        from venom_core.services.workflow_operations import (
            get_workflow_operation_service,
        )

        service = get_workflow_operation_service()
        workflow = service._get_or_create_workflow(workflow_id)
        workflow["status"] = WorkflowStatus.RUNNING.value

        # Pause with metadata
        request = {
            "workflow_id": workflow_id,
            "operation": "pause",
            "metadata": {"reason": "maintenance", "scheduled_by": "admin"},
        }

        response = client.post("/api/v1/workflow/operations/pause", json=request)

        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["reason"] == "maintenance"
        assert data["metadata"]["scheduled_by"] == "admin"
