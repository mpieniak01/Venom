import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tests.helpers.url_fixtures import http_url
from venom_core.core.service_monitor import (
    ServiceHealthMonitor,
    ServiceInfo,
    ServiceRegistry,
    ServiceStatus,
)


@pytest.mark.asyncio
async def test_service_status_broadcast():
    # Mock registry and services
    registry = ServiceRegistry()
    # Use an API service type to trigger _check_http_service
    service = ServiceInfo(
        name="test_api",
        service_type="api",
        endpoint=http_url("fake.api", path="/health"),
        status=ServiceStatus.UNKNOWN,
    )
    registry.services["test_api"] = service

    # Mock event broadcaster
    mock_broadcaster = AsyncMock()

    # Initialize monitor
    monitor = ServiceHealthMonitor(registry, event_broadcaster=mock_broadcaster)

    # Mock _check_http_service instead of _check_service_health
    with patch.object(
        monitor, "_check_http_service", new_callable=AsyncMock
    ) as mock_http_check:

        async def side_effect(s):
            if s.name == "test_api":
                s.status = ServiceStatus.ONLINE
                s.error_message = "All good"
            else:
                s.status = ServiceStatus.OFFLINE

        mock_http_check.side_effect = side_effect

        # Run health check
        await monitor.check_health()

        # Give a moment for the background tasks (asyncio.create_task in monitor)
        await asyncio.sleep(0.5)

        # Verify broadcast_event was called
        assert mock_broadcaster.broadcast_event.called, (
            "broadcast_event should have been called"
        )

        # Check call arguments
        found = False
        for call in mock_broadcaster.broadcast_event.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("event_type") == "SERVICE_STATUS_UPDATE":
                if kwargs["data"]["name"] == "test_api":
                    assert kwargs["data"]["status"] == "online"
                    found = True
                    break

        assert found, (
            f"SERVICE_STATUS_UPDATE event for 'test_api' was not broadcasted. Calls: {mock_broadcaster.broadcast_event.call_args_list}"
        )
