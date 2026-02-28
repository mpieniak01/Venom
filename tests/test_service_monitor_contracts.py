from __future__ import annotations

from types import SimpleNamespace

import pytest

from venom_core.core.service_monitor import (
    ServiceHealthMonitor,
    ServiceInfo,
    ServiceStatus,
)


@pytest.mark.asyncio
async def test_service_monitor_http_and_summary_branches(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict[str, object]] = []

    class _Response:
        def __init__(self, status_code: int):
            self.status_code = status_code

    class _Client:
        def __init__(self, *, provider: str, timeout: float):
            calls.append({"provider": provider, "timeout": timeout})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def aget(self, _url: str, headers=None, raise_for_status=False):
            assert raise_for_status is False
            calls.append({"headers": headers or {}})
            return _Response(503)

    monitor = ServiceHealthMonitor(
        registry=SimpleNamespace(
            get_all_services=lambda: [],
            get_critical_services=lambda: [],
        )
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.TrafficControlledHttpClient", _Client
    )
    monkeypatch.setattr(
        "venom_core.core.service_monitor.SETTINGS",
        SimpleNamespace(
            GITHUB_TOKEN=SimpleNamespace(get_secret_value=lambda: "gh-token"),
            OPENAI_API_KEY="",
        ),
    )

    service = ServiceInfo(
        name="GitHub API",
        service_type="api",
        endpoint="https://example",
    )
    await monitor._check_http_service(service)
    assert service.status == ServiceStatus.OFFLINE
    assert service.error_message == "HTTP 503"
    assert calls[0]["provider"] == "github"
    assert calls[1]["headers"]["Authorization"] == "Bearer gh-token"

    summary = monitor.get_summary()
    assert summary["total_services"] == 0
