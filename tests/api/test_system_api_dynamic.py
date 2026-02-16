import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from venom_core.api.routes.system import (
    _generate_external_map,
    _generate_internal_map,
    _get_method_signatures,
    _update_runtime_statuses,
    router,
)
from venom_core.api.schemas.system import (
    ApiConnection,
    ConnectionProtocol,
    ConnectionStatus,
)


# Setup a dummy app for testing route discovery
@pytest.fixture
def mock_app():
    app = FastAPI()

    # Define some dummy routes matching our prefixes
    router_sys = APIRouter()

    @router_sys.get("/api/v1/system/status")
    def status():
        pass

    @router_sys.post("/api/v1/system/services/{name}/restart")
    def restart(name: str):
        pass

    @router_sys.post("/api/v1/chat")
    def chat():
        pass

    app.include_router(router_sys)
    return app


def test_get_method_signatures(mock_app):
    # Test discovery for system status
    methods = _get_method_signatures(mock_app, "/api/v1/system/status")
    assert "GET /api/v1/system/status" in methods

    # Test discovery for services (parameterized)
    methods = _get_method_signatures(mock_app, "/api/v1/system/services")
    assert "POST /api/v1/system/services/{name}/restart" in methods

    # Test unknown prefix
    methods = _get_method_signatures(mock_app, "/api/v1/unknown")
    assert len(methods) == 0


def test_generate_internal_map(mock_app):
    # Mock request.app
    mock_request = MagicMock()
    mock_request.app = mock_app

    internal = _generate_internal_map(mock_request)

    # Check if we found System Status API
    system_status = next(
        (c for c in internal if c.target_component == "System Status API"), None
    )
    assert system_status is not None
    assert "GET /api/v1/system/status" in system_status.methods

    # Check if we found Frontend (Next.js) which maps to /api/v1/chat
    frontend = next(
        (c for c in internal if c.target_component == "Frontend (Next.js)"), None
    )
    assert frontend is not None
    assert "POST /api/v1/chat" in frontend.methods
    # Verify WS/SSE are present (hardcoded in logic)
    assert "WS /ws/events" in frontend.methods


def test_generate_external_map():
    # Helper to test config-driven map
    with (
        patch("venom_core.config.SETTINGS.LLM_SERVICE_TYPE", "local"),
        patch(
            "venom_core.config.SETTINGS.LLM_LOCAL_ENDPOINT", "http://localhost:11434"
        ),
    ):
        external = _generate_external_map()
        local_llm = next(
            (c for c in external if "Local LLM" in c.target_component), None
        )
        assert local_llm is not None
        assert local_llm.source_type == "local"

    with (
        patch("venom_core.config.SETTINGS.AI_MODE", "CLOUD"),
        patch("venom_core.config.SETTINGS.HYBRID_CLOUD_PROVIDER", "openai"),
    ):
        external = _generate_external_map()
        cloud_llm = next(
            (c for c in external if "Cloud LLM" in c.target_component), None
        )
        assert cloud_llm is not None
        assert cloud_llm.source_type == "cloud"


def test_update_runtime_statuses():
    # Create some dummy connections
    connections = [
        ApiConnection(
            source_component="System Monitor",
            target_component="OpenAI API",  # Should map to offline
            protocol=ConnectionProtocol.HTTP,
            status=ConnectionStatus.UNKNOWN,
            direction="bidirectional",
            auth_type="none",
            source_type="local",
            description="test",
            is_critical=False,
            methods=[],
        ),
        ApiConnection(
            source_component="System Monitor",
            target_component="Redis",  # Should be online
            protocol=ConnectionProtocol.HTTP,
            status=ConnectionStatus.UNKNOWN,
            direction="bidirectional",
            auth_type="none",
            source_type="local",
            description="test",
            is_critical=False,
            methods=[],
        ),
        ApiConnection(
            source_component="System Monitor",
            target_component="Agents API",  # Unknown service
            protocol=ConnectionProtocol.HTTP,
            status=ConnectionStatus.UNKNOWN,
            direction="bidirectional",
            auth_type="none",
            source_type="local",
            description="test",
            is_critical=False,
            methods=[],
        ),
    ]

    # Mock ServiceMonitor
    mock_monitor = MagicMock()

    # Define mock services
    class MockService:
        def __init__(self, name, status_val):
            self.name = name
            self.status = MagicMock()
            self.status.value = status_val
            self.error_message = None

    mock_monitor.get_all_services.return_value = [
        MockService("OpenAI API", "offline"),
        MockService("Redis", "online"),
    ]

    _update_runtime_statuses(connections, mock_monitor)

    assert connections[0].status == ConnectionStatus.DOWN
    assert connections[1].status == ConnectionStatus.OK
    assert (
        connections[2].status == ConnectionStatus.UNKNOWN
    )  # Not in service map/monitor


def test_caching_logic():
    # Test that caching works

    # Use TestClient to trigger the endpoint
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # We patch where it's DEFINED, not where it is imported inside the function
    # Because sys.modules has it.
    with (
        patch("venom_core.api.routes.system._generate_internal_map") as mock_gen,
        patch("venom_core.api.routes.system._update_runtime_statuses"),
        patch("venom_core.api.routes.system_deps.get_service_monitor"),
    ):
        mock_gen.return_value = []  # Return empty list

        # Reset cache in case other tests messed with it (though unrelated here, good practice)
        from venom_core.api.routes import system

        previous_cache = getattr(system, "_API_MAP_CACHE", None)
        previous_time = getattr(system, "_LAST_CACHE_TIME", 0)

        try:
            system._API_MAP_CACHE = None
            system._LAST_CACHE_TIME = 0

            # First call: should generate
            client.get("/api/v1/system/api-map")
            assert mock_gen.call_count == 1

            # Second call: should use cache
            client.get("/api/v1/system/api-map")
            assert mock_gen.call_count == 1

            # Mock time moving forward past TTL
            with patch("time.time", return_value=time.time() + system._CACHE_TTL + 1):
                client.get("/api/v1/system/api-map")
                assert mock_gen.call_count == 2
        finally:
            system._API_MAP_CACHE = previous_cache
            system._LAST_CACHE_TIME = previous_time
