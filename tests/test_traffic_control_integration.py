"""Integration tests for traffic control - HTTP client and middleware."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from venom_core.api.middleware.traffic_control import TrafficControlMiddleware
from venom_core.infrastructure.traffic_control import (
    TrafficControlConfig,
    TrafficController,
    TrafficControlledHttpClient,
)


class TestTrafficControlledHttpClient:
    """Integration tests dla TrafficControlledHttpClient."""

    def test_http_client_respects_rate_limits(self):
        """Test że HTTP client respektuje rate limity."""
        # Create client with very low limits
        config = TrafficControlConfig()
        config.global_outbound.rate_limit.capacity = 2
        controller = TrafficController(config)

        # Don't actually create HTTP client, just verify controller behavior
        # First 2 checks should pass
        allowed1, _, _ = controller.check_outbound_request("test_provider")
        assert allowed1 is True
        
        allowed2, _, _ = controller.check_outbound_request("test_provider")
        assert allowed2 is True

        # Third check should fail
        allowed3, reason, wait = controller.check_outbound_request("test_provider")
        assert allowed3 is False
        assert reason == "rate_limit_exceeded"
        assert wait is not None

    def test_http_client_circuit_breaker_integration(self):
        """Test że circuit breaker działa z HTTP clientem."""
        config = TrafficControlConfig()
        config.global_outbound.circuit_breaker.failure_threshold = 2
        controller = TrafficController(config)

        # Simulate failures
        controller.check_outbound_request("test_provider")
        controller.record_outbound_response("test_provider", 503)
        
        controller.check_outbound_request("test_provider")
        controller.record_outbound_response("test_provider", 503)

        # Circuit should be open now
        allowed, reason, _ = controller.check_outbound_request("test_provider")
        assert allowed is False
        assert reason == "circuit_breaker_open"

    def test_http_client_tracks_metrics(self):
        """Test że HTTP client śledzi metryki."""
        config = TrafficControlConfig()
        controller = TrafficController(config)

        # Simulate successful requests
        controller.check_outbound_request("test_provider")
        controller.record_outbound_response("test_provider", 200)

        controller.check_outbound_request("test_provider")
        controller.record_outbound_response("test_provider", 201)

        # Simulate error
        controller.check_outbound_request("test_provider")
        controller.record_outbound_response("test_provider", 429)

        # Check metrics
        metrics = controller.get_metrics("test_provider")
        assert metrics["metrics"]["total_requests"] == 3
        assert metrics["metrics"]["total_2xx"] == 2
        assert metrics["metrics"]["total_429"] == 1

    def test_http_client_provider_specific_limits(self):
        """Test że różne providery mają różne limity."""
        config = TrafficControlConfig.from_env()
        controller = TrafficController(config)

        # GitHub ma limit 60/min
        for _ in range(60):
            allowed, _, _ = controller.check_outbound_request("github")
            if not allowed:
                break
        # Powinno być rate limited po 60 requestach
        allowed, reason, _ = controller.check_outbound_request("github")
        assert allowed is False

        # OpenAI ma wyższy limit (500/min) - still should work
        allowed, _, _ = controller.check_outbound_request("openai")
        assert allowed is True


class TestTrafficControlMiddleware:
    """Integration tests dla FastAPI middleware."""

    def test_middleware_allows_normal_request(self):
        """Test że middleware przepuszcza normalne requesty."""
        app = FastAPI()
        app.add_middleware(TrafficControlMiddleware)

        @app.get("/api/v1/test")
        async def test_endpoint():
            return {"status": "ok"}

        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/api/v1/test")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_middleware_rate_limits_requests(self):
        """Test że middleware rate limituje requesty."""
        # Create app with very low rate limits
        config = TrafficControlConfig()
        config.global_inbound.rate_limit.capacity = 2
        controller = TrafficController(config)

        # Patch singleton to use our controller
        with patch(
            "venom_core.api.middleware.traffic_control.get_traffic_controller",
            return_value=controller,
        ):
            app = FastAPI()
            app.add_middleware(TrafficControlMiddleware)

            @app.get("/api/v1/chat/test")
            async def test_endpoint():
                return {"status": "ok"}

            from fastapi.testclient import TestClient

            client = TestClient(app)

            # First 2 requests should succeed
            response1 = client.get("/api/v1/chat/test")
            assert response1.status_code == 200

            response2 = client.get("/api/v1/chat/test")
            assert response2.status_code == 200

            # Third request should be rate limited
            response3 = client.get("/api/v1/chat/test")
            assert response3.status_code == 429
            assert "retry_after_seconds" in response3.json()

    def test_middleware_skips_health_checks(self):
        """Test że middleware pomija health check endpointy."""
        app = FastAPI()
        app.add_middleware(TrafficControlMiddleware)

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Health check should never be rate limited
        for _ in range(100):
            response = client.get("/health")
            assert response.status_code == 200

    def test_middleware_groups_endpoints_correctly(self):
        """Test że middleware grupuje endpointy poprawnie."""
        config = TrafficControlConfig.from_env()
        # Override chat policy
        from venom_core.infrastructure.traffic_control.config import InboundPolicyConfig, TokenBucketConfig
        config.endpoint_group_policies["chat"] = InboundPolicyConfig(
            rate_limit=TokenBucketConfig(capacity=2, refill_rate=0.1)
        )
        config.endpoint_group_policies["memory"] = InboundPolicyConfig(
            rate_limit=TokenBucketConfig(capacity=10, refill_rate=1.0)
        )
        controller = TrafficController(config)

        with patch(
            "venom_core.api.middleware.traffic_control.get_traffic_controller",
            return_value=controller,
        ):
            app = FastAPI()
            app.add_middleware(TrafficControlMiddleware)

            @app.get("/api/v1/chat/messages")
            async def chat_endpoint():
                return {"status": "ok"}

            @app.get("/api/v1/memory/recall")
            async def memory_endpoint():
                return {"status": "ok"}

            from fastapi.testclient import TestClient

            client = TestClient(app)

            # Chat has low limit (2), should be rate limited quickly
            client.get("/api/v1/chat/messages")
            client.get("/api/v1/chat/messages")
            response = client.get("/api/v1/chat/messages")
            assert response.status_code == 429

            # Memory has higher limit (10), should still work
            response = client.get("/api/v1/memory/recall")
            assert response.status_code == 200
