"""Tests for traffic control API routes."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from venom_core.api.routes.traffic_control import router, get_traffic_control_status, get_scope_metrics
from venom_core.infrastructure.traffic_control import TrafficController, TrafficControlConfig


@pytest.fixture
def mock_controller():
    """Mock traffic controller for testing."""
    controller = MagicMock(spec=TrafficController)
    controller.get_metrics.return_value = {
        "outbound_scopes": ["openai", "github"],
        "inbound_scopes": ["chat", "memory"],
        "global": {
            "total_requests": 100,
            "total_2xx": 90,
            "total_4xx": 5,
            "total_5xx": 5,
        },
    }
    return controller


class TestTrafficControlStatusEndpoint:
    """Tests for /status endpoint."""

    def test_get_traffic_control_status_success(self, mock_controller):
        """Test successful status retrieval."""
        with patch(
            "venom_core.api.routes.traffic_control.get_traffic_controller",
            return_value=mock_controller,
        ):
            result = get_traffic_control_status()

            assert result["status"] == "success"
            assert "global" in result
            assert "scopes" in result
            mock_controller.get_metrics.assert_called()

    def test_get_traffic_control_status_with_scopes(self, mock_controller):
        """Test status retrieval includes all scopes."""
        # Configure mock to return scope-specific metrics
        def get_metrics_side_effect(scope=None):
            if scope is None:
                return {
                    "outbound_scopes": ["openai", "github"],
                    "inbound_scopes": ["chat"],
                    "global": {"total_requests": 100},
                }
            else:
                return {
                    "rate_limit": {"capacity": 100, "available": 50},
                    "circuit_breaker": {"state": "closed"},
                }

        mock_controller.get_metrics.side_effect = get_metrics_side_effect

        with patch(
            "venom_core.api.routes.traffic_control.get_traffic_controller",
            return_value=mock_controller,
        ):
            result = get_traffic_control_status()

            assert result["status"] == "success"
            assert "scopes" in result
            # Should have called get_metrics for global + 2 outbound + 1 inbound
            assert mock_controller.get_metrics.call_count >= 4

    def test_get_traffic_control_status_error_handling(self):
        """Test error handling in status endpoint."""
        with patch(
            "venom_core.api.routes.traffic_control.get_traffic_controller",
            side_effect=Exception("Test error"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_traffic_control_status()

            assert exc_info.value.status_code == 500
            assert "Internal server error" in str(exc_info.value.detail)


class TestScopeMetricsEndpoint:
    """Tests for /metrics/{scope} endpoint."""

    def test_get_scope_metrics_success(self, mock_controller):
        """Test successful scope metrics retrieval."""
        mock_controller.get_metrics.return_value = {
            "rate_limit": {"capacity": 100, "available": 80},
            "circuit_breaker": {"state": "closed", "failure_count": 0},
            "metrics": {"total_requests": 50, "total_2xx": 48},
        }

        with patch(
            "venom_core.api.routes.traffic_control.get_traffic_controller",
            return_value=mock_controller,
        ):
            result = get_scope_metrics("openai")

            assert result["status"] == "success"
            assert result["scope"] == "openai"
            assert "metrics" in result
            mock_controller.get_metrics.assert_called_once_with("openai")

    def test_get_scope_metrics_not_found(self, mock_controller):
        """Test scope not found error."""
        mock_controller.get_metrics.return_value = {
            "error": "Scope not found: unknown_provider"
        }

        with patch(
            "venom_core.api.routes.traffic_control.get_traffic_controller",
            return_value=mock_controller,
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_scope_metrics("unknown_provider")

            assert exc_info.value.status_code == 404

    def test_get_scope_metrics_error_handling(self):
        """Test error handling in scope metrics endpoint."""
        with patch(
            "venom_core.api.routes.traffic_control.get_traffic_controller",
            side_effect=Exception("Test error"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_scope_metrics("openai")

            assert exc_info.value.status_code == 500
            assert "Internal server error" in str(exc_info.value.detail)


class TestTrafficControlRouterIntegration:
    """Integration tests for traffic control router."""

    def test_router_is_configured(self):
        """Test that router is properly configured."""
        assert router.prefix == "/api/v1/traffic-control"
        assert "traffic-control" in router.tags

    def test_router_has_required_routes(self):
        """Test that router has all required routes."""
        route_paths = [route.path for route in router.routes]
        assert "/api/v1/traffic-control/status" in route_paths
        assert "/api/v1/traffic-control/metrics/{scope}" in route_paths
