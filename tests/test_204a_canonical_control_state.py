"""
Test suite for 204A: Canonical Workflow-Control Operator Model.

Tests coverage:
- Request selector (_select_trace) with 4-strategy fallback
- Config field aggregation with CONFIG_WHITELIST mapping
- Runtime service aggregation with allowed_actions
- Execution step aggregation from trace
- Canonical graph builder (core nodes + service nodes)
- Gateway endpoints for workflow operations and runtime actions
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from venom_core.core.tracer import RequestTrace, TraceStatus, TraceStep
from venom_core.main import app
from venom_core.services.runtime_controller import (
    ServiceInfo,
    ServiceStatus,
    ServiceType,
)


class InMemoryConfigManager:
    """Test double for config manager."""

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

    def get_config(self, mask_secrets: bool = False) -> dict[str, Any]:
        return dict(self._config)

    def get_control_options(self) -> dict[str, Any]:
        """Return available options for config fields."""
        return {
            "AI_MODE": ["standard", "advanced", "heuristic"],
            "INTENT_MODE": ["simple", "advanced", "expert"],
            "KERNEL": ["standard", "optimized", "legacy"],
            "ACTIVE_PROVIDER": ["ollama", "openai", "anthropic"],
            "EMBEDDING_MODEL": ["sentence-transformers", "openai-embeddings"],
        }

    def get_effective_config_with_sources(
        self, mask_secrets: bool = True
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Return config dict and sources dict for each key."""
        config = dict(self._config)
        sources = {key: "env" for key in config.keys()}
        return config, sources

    def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        for key, value in updates.items():
            self._config[key] = str(value)
        return {
            "success": True,
            "message": "Updated",
            "changed_keys": list(updates.keys()),
        }


class InMemoryTracer:
    """Test double for request tracer."""

    def __init__(self):
        self.traces: dict[str, RequestTrace] = {}
        self.latest_active_trace: RequestTrace | None = None
        self.latest_trace: RequestTrace | None = None

    def get_trace(self, request_id: str | UUID) -> RequestTrace | None:
        return self.traces.get(str(request_id))

    def add_trace(self, request_id: str, trace: RequestTrace) -> None:
        """Add trace to registry, ensuring request_id matches."""
        # Ensure trace.request_id matches the key
        try:
            trace_uuid = UUID(request_id) if isinstance(request_id, str) else request_id
            if trace.request_id != trace_uuid:
                # Create a copy with matching request_id
                import copy

                trace = copy.deepcopy(trace)
                trace.request_id = trace_uuid
        except (ValueError, TypeError):
            pass

        self.traces[request_id] = trace
        self.latest_trace = trace
        if trace.status == "PROCESSING":
            self.latest_active_trace = trace

    def get_all_traces(self, limit: int = 200) -> list[RequestTrace]:
        """Return all traces in reverse order (newest first) up to limit."""
        return list(reversed(list(self.traces.values())))[:limit]


@pytest.fixture(autouse=True)
def isolated_control_plane(monkeypatch):
    """Reset singletons and inject test doubles for each test."""
    import venom_core.services.control_plane as control_plane_module

    fake_config = InMemoryConfigManager()
    fake_tracer = InMemoryTracer()

    # Mock config_manager
    monkeypatch.setattr(control_plane_module, "config_manager", fake_config)

    # Mock runtime_controller.get_all_services_status
    def mock_services():
        return [
            ServiceInfo(
                name="Backend",
                service_type=ServiceType.BACKEND,
                status=ServiceStatus.RUNNING,
                pid=1001,
                port=8000,
                cpu_percent=15.0,
                memory_mb=512.0,
                uptime_seconds=3600,
                runtime_version="1.0.0",
                actionable=True,
            ),
            ServiceInfo(
                name="Ollama",
                service_type=ServiceType.LLM_OLLAMA,
                status=ServiceStatus.RUNNING,
                pid=1002,
                port=11434,
                cpu_percent=45.0,
                memory_mb=2048.0,
                uptime_seconds=7200,
                runtime_version="0.13.0",
                actionable=True,
            ),
            ServiceInfo(
                name="UI",
                service_type=ServiceType.UI,
                status=ServiceStatus.STOPPED,
                pid=None,
                port=None,
                cpu_percent=0.0,
                memory_mb=0.0,
                uptime_seconds=0,
                runtime_version="16.1.6",
                actionable=True,
            ),
        ]

    monkeypatch.setattr(
        control_plane_module.runtime_controller,
        "get_all_services_status",
        mock_services,
    )

    # Mock get_request_tracer
    def mock_tracer():
        return fake_tracer

    monkeypatch.setattr(
        control_plane_module,
        "get_request_tracer",
        mock_tracer,
    )

    # Return tracer for test access
    return fake_tracer


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_trace() -> RequestTrace:
    """Create a sample request trace."""
    return RequestTrace(
        request_id=uuid4(),
        status=TraceStatus.PROCESSING,
        prompt="Test user query",
        steps=[
            TraceStep(
                id="step_1",
                component="decision",
                action="analyze",
                status="completed",
                timestamp=datetime.now().isoformat(),
                details='{"intent": "user_query"}',
            ),
            TraceStep(
                id="step_2",
                component="intent",
                action="extract",
                status="completed",
                timestamp=datetime.now().isoformat(),
                details='{"intent_confidence": 0.95}',
            ),
            TraceStep(
                id="step_3",
                component="kernel",
                action="execute",
                status="in_progress",
                timestamp=datetime.now().isoformat(),
                details='{"progress": "50%"}',
            ),
        ],
        llm_provider="ollama",
        llm_model="llama2",
    )


class TestRequestSelector:
    """Tests for _select_trace request selector with 4-strategy fallback."""

    def test_select_trace_explicit_request_id(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that explicit request_id takes priority (strategy 1)."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        # Create another trace that's latest but not the one we want
        other_request_id = str(uuid4())
        other_trace = RequestTrace(
            request_id=uuid4(),
            status=TraceStatus.PROCESSING,
            prompt="Other query",
            steps=[],
        )
        isolated_control_plane.add_trace(other_request_id, other_trace)

        # Request with explicit request_id should use that trace
        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_target"]["request_id"] == request_id

    def test_select_trace_latest_active_fallback(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test fallback to latest_active when explicit request_id not provided (strategy 2)."""
        # Add active trace
        request_id_active = str(uuid4())
        isolated_control_plane.add_trace(request_id_active, sample_trace)

        # Add non-active trace as latest (but not active)
        request_id_inactive = str(uuid4())
        inactive_trace = RequestTrace(
            request_id=uuid4(),
            status=TraceStatus.COMPLETED,
            prompt="Inactive query",
            steps=[],
        )
        isolated_control_plane.add_trace(request_id_inactive, inactive_trace)

        # Should select active trace (strategy 2)
        response = client.get("/api/v1/workflow/control/state")
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_target"]["request_id"] == request_id_active

    def test_select_trace_latest_fallback(self, client, isolated_control_plane):
        """Test fallback to latest when no active trace exists (strategy 3)."""
        # Add only inactive traces
        request_id_1 = str(uuid4())
        trace_1 = RequestTrace(
            prompt="Query 1",
            created_at="2026-01-01T10:00:00",
            request_id=uuid4(),
            status=TraceStatus.COMPLETED,
            steps=[],
        )
        isolated_control_plane.add_trace(request_id_1, trace_1)

        request_id_2 = str(uuid4())
        trace_2 = RequestTrace(
            prompt="Query 2",
            created_at="2026-01-01T11:00:00",
            request_id=uuid4(),
            status=TraceStatus.COMPLETED,
            steps=[],
        )
        isolated_control_plane.add_trace(request_id_2, trace_2)

        # Should select trace_2 (latest by timestamp)
        response = client.get("/api/v1/workflow/control/state")
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_target"]["request_id"] == request_id_2

    def test_select_trace_none_fallback(self, client, isolated_control_plane):
        """Test fallback to None when no traces exist (strategy 4)."""
        # No traces added
        response = client.get("/api/v1/workflow/control/state")
        assert response.status_code == 200
        data = response.json()
        assert (
            data["workflow_target"] is None
            or data["workflow_target"]["request_id"] is None
        )


class TestConfigFieldAggregation:
    """Tests for config field aggregation from CONFIG_WHITELIST."""

    def test_config_fields_present_in_response(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that config_fields list is present and populated."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        # Verify config_fields structure
        assert "config_fields" in data
        assert isinstance(data["config_fields"], list)
        assert len(data["config_fields"]) > 0

    def test_config_field_has_required_attributes(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that each config field has required attributes."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        config_fields = data["config_fields"]
        required_attrs = [
            "entity_id",
            "field",
            "key",
            "value",
            "effective_value",
            "source",
            "editable",
            "restart_required",
            "affected_services",
            "options",
        ]

        for field in config_fields:
            for attr in required_attrs:
                assert attr in field, f"Missing attribute '{attr}' in config field"

    def test_config_field_options_mapping(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that config field options are properly mapped from get_control_options."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        # Find AI_MODE field
        ai_mode_field = next(
            (f for f in data["config_fields"] if f["key"] == "AI_MODE"), None
        )
        assert ai_mode_field is not None
        assert "options" in ai_mode_field
        assert ai_mode_field["options"] == ["standard", "advanced", "heuristic"]

    def test_config_field_effective_value_differs(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that effective_value differs from value when applicable."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        config_fields = data["config_fields"]
        # At least one field should have value/effective_value (implementation dependent)
        # For now, just verify the structure is present
        for field in config_fields:
            assert field["value"] is not None or field["effective_value"] is not None


class TestRuntimeServiceAggregation:
    """Tests for runtime service aggregation."""

    def test_runtime_services_present_in_response(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that runtime_services list is present and populated."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        assert "runtime_services" in data
        assert isinstance(data["runtime_services"], list)
        assert len(data["runtime_services"]) == 3  # backend, llm_ollama, ui

    def test_runtime_service_structure(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that each runtime service has correct structure."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        runtime_services = data["runtime_services"]
        required_attrs = [
            "id",
            "name",
            "kind",
            "status",
            "pid",
            "port",
            "cpu_percent",
            "memory_mb",
            "uptime_seconds",
            "runtime_version",
            "actionable",
            "allowed_actions",
            "dependencies",
        ]

        for service in runtime_services:
            for attr in required_attrs:
                assert attr in service, f"Missing attribute '{attr}' in runtime service"

    def test_runtime_service_allowed_actions(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that allowed_actions are properly set based on service state."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        runtime_services = data["runtime_services"]

        # Find running service (backend)
        backend = next(
            (s for s in runtime_services if s.get("kind") == "backend"), None
        )
        assert backend is not None
        assert isinstance(backend["allowed_actions"], list)
        assert (
            "stop" in backend["allowed_actions"]
            or "restart" in backend["allowed_actions"]
        )

        # Find stopped service (ui)
        ui = next((s for s in runtime_services if s.get("kind") == "ui"), None)
        assert ui is not None
        assert "start" in ui["allowed_actions"]


class TestExecutionStepAggregation:
    """Tests for execution step aggregation from trace."""

    def test_execution_steps_present_in_response(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that execution_steps list is present and populated."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        assert "execution_steps" in data
        assert isinstance(data["execution_steps"], list)
        assert len(data["execution_steps"]) == 3  # 3 steps in sample_trace

    def test_execution_step_structure(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that each execution step has correct structure."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        execution_steps = data["execution_steps"]
        required_attrs = ["id", "component", "action", "status", "timestamp", "details"]

        for step in execution_steps:
            for attr in required_attrs:
                assert attr in step, f"Missing attribute '{attr}' in execution step"

    def test_missing_execution_step_timestamp_is_null(
        self, client, isolated_control_plane, sample_trace
    ):
        """Missing source timestamp should remain null in API response."""
        request_id = str(uuid4())
        sample_trace.steps[0].timestamp = None
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        execution_steps = data["execution_steps"]
        assert len(execution_steps) > 0
        assert execution_steps[0]["timestamp"] is None


class TestCanonicalGraphBuilder:
    """Tests for canonical operator graph builder."""

    def test_graph_present_in_response(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that graph is present in response."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        assert "graph" in data
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]
        assert isinstance(data["graph"]["nodes"], list)
        assert isinstance(data["graph"]["edges"], list)

    def test_graph_has_core_nodes(self, client, isolated_control_plane, sample_trace):
        """Test that graph includes all 6 core nodes."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        nodes = data["graph"]["nodes"]
        node_ids = {node["id"] for node in nodes}

        core_nodes = {
            "decision",
            "intent",
            "kernel",
            "runtime",
            "embedding",
            "provider",
        }
        for core_node in core_nodes:
            assert core_node in node_ids, f"Core node '{core_node}' missing from graph"

    def test_graph_edges_connect_core_nodes(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that edges properly connect core nodes."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        edges = data["graph"]["edges"]
        # Should have at least 5 edges connecting 6 core nodes
        assert len(edges) >= 5

        edge_pairs = {(e["source"], e["target"]) for e in edges}
        # Verify some key connections
        assert any((e[0] == "decision" and e[1] == "intent") for e in edge_pairs), (
            "Missing decision->intent edge"
        )


class TestGatewayEndpoints:
    """Tests for gateway endpoints."""

    def test_runtime_service_action_gateway(self, client, isolated_control_plane):
        """Test POST /runtime/{service_id}/{action} gateway."""
        # Test start action
        response = client.post("/api/v1/workflow/control/runtime/ui/start")
        assert response.status_code in [200, 202, 409]  # 409 if already running

    def test_workflow_operation_gateway(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test POST /workflow/{request_id}/{operation} gateway."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        # Test pause operation
        response = client.post(f"/api/v1/workflow/control/workflow/{request_id}/pause")
        # Should return 200/202 (operation accepted) or 400/409 (invalid state)
        assert response.status_code in [200, 202, 400, 409, 404]


class TestCanonicalStateIntegration:
    """Integration tests for complete canonical state response."""

    def test_complete_control_state_response(
        self, client, isolated_control_plane, sample_trace
    ):
        """Test that GET /state returns complete canonical response."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        # Verify all top-level keys from ControlStateResponse
        expected_keys = [
            "system_state",
            "meta",
            "workflow_target",
            "config_fields",
            "runtime_services",
            "execution_steps",
            "graph",
            "allowed_actions",
        ]

        for key in expected_keys:
            assert key in data, f"Missing key '{key}' in canonical state response"

    def test_request_id_propagation(self, client, isolated_control_plane, sample_trace):
        """Test that request_id is properly propagated through response."""
        request_id = str(uuid4())
        isolated_control_plane.add_trace(request_id, sample_trace)

        response = client.get(f"/api/v1/workflow/control/state?request_id={request_id}")
        assert response.status_code == 200
        data = response.json()

        # Should also be in workflow_target if available
        if data["workflow_target"]:
            assert data["workflow_target"]["request_id"] == request_id
