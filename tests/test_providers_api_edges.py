"""Edge-case tests for provider management API internals."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from venom_core.api.routes import providers as providers_route


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _DummyAsyncClient:
    def __init__(
        self,
        response: _DummyResponse | None = None,
        exc: Exception | None = None,
        responses_by_url: dict[str, _DummyResponse] | None = None,
    ):
        self._response = response
        self._exc = exc
        self._responses_by_url = responses_by_url or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        if self._exc:
            raise self._exc
        if url in self._responses_by_url:
            return self._responses_by_url[url]
        return self._response


def test_get_provider_type_unknown() -> None:
    assert providers_route._get_provider_type("unknown") == "unknown"


def test_get_provider_capabilities_local_and_unknown() -> None:
    local_caps = providers_route._get_provider_capabilities("local")
    assert local_caps.activate is True
    assert local_caps.install is False
    assert local_caps.search is False

    unknown_caps = providers_route._get_provider_capabilities("not-real")
    assert unknown_caps.install is False
    assert unknown_caps.search is False
    assert unknown_caps.activate is False
    assert unknown_caps.inference is False
    assert unknown_caps.trainable is False


def test_get_provider_endpoint_vllm_and_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        providers_route.SETTINGS, "VLLM_ENDPOINT", "http://vllm:8000", raising=False
    )
    assert providers_route._get_provider_endpoint("vllm") == "http://vllm:8000"
    assert providers_route._get_provider_endpoint("unknown") is None


def test_check_openai_status_key_missing_and_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(providers_route.SETTINGS, "OPENAI_API_KEY", "", raising=False)
    missing = providers_route._check_openai_status()
    assert missing.status == "offline"
    assert missing.reason_code == "missing_api_key"

    monkeypatch.setattr(
        providers_route.SETTINGS, "OPENAI_API_KEY", "sk-test", raising=False
    )
    present = providers_route._check_openai_status()
    assert present.status == "connected"


def test_check_google_status_key_missing_and_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(providers_route.SETTINGS, "GOOGLE_API_KEY", "", raising=False)
    missing = providers_route._check_google_status()
    assert missing.status == "offline"
    assert missing.reason_code == "missing_api_key"

    monkeypatch.setattr(
        providers_route.SETTINGS, "GOOGLE_API_KEY", "g-test", raising=False
    )
    present = providers_route._check_google_status()
    assert present.status == "connected"


@pytest.mark.asyncio
async def test_check_provider_connection_unknown_provider() -> None:
    status = await providers_route._check_provider_connection("not-supported")
    assert status.status == "unknown"
    assert status.reason_code == "unsupported_provider"


@pytest.mark.asyncio
async def test_check_ollama_status_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers_route.httpx,
        "AsyncClient",
        lambda timeout=5.0: _DummyAsyncClient(response=_DummyResponse(503)),
    )
    status = await providers_route._check_ollama_status()
    assert status.status == "degraded"
    assert status.reason_code == "http_error"


@pytest.mark.asyncio
async def test_check_ollama_status_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        providers_route.httpx,
        "AsyncClient",
        lambda timeout=5.0: _DummyAsyncClient(exc=RuntimeError("boom")),
    )
    status = await providers_route._check_ollama_status()
    assert status.status == "offline"
    assert status.reason_code == "connection_failed"


@pytest.mark.asyncio
async def test_check_ollama_status_connected_includes_runtime_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        providers_route.httpx,
        "AsyncClient",
        lambda timeout=5.0: _DummyAsyncClient(
            responses_by_url={
                "http://localhost:11434/api/tags": _DummyResponse(200),
                "http://localhost:11434/api/version": _DummyResponse(
                    200, {"version": "0.16.1"}
                ),
            }
        ),
    )

    status = await providers_route._check_ollama_status()
    assert status.status == "connected"
    assert status.runtime_version == "0.16.1"


@pytest.mark.asyncio
async def test_check_vllm_status_no_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers_route.SETTINGS, "VLLM_ENDPOINT", "", raising=False)
    status = await providers_route._check_vllm_status()
    assert status.status == "offline"
    assert status.reason_code == "no_endpoint"


@pytest.mark.asyncio
async def test_check_vllm_status_degraded_and_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        providers_route.SETTINGS, "VLLM_ENDPOINT", "http://vllm:8000", raising=False
    )
    monkeypatch.setattr(
        providers_route.httpx,
        "AsyncClient",
        lambda timeout=5.0: _DummyAsyncClient(response=_DummyResponse(502)),
    )
    degraded = await providers_route._check_vllm_status()
    assert degraded.status == "degraded"
    assert degraded.reason_code == "http_error"

    monkeypatch.setattr(
        providers_route.httpx,
        "AsyncClient",
        lambda timeout=5.0: _DummyAsyncClient(exc=RuntimeError("fail")),
    )
    offline = await providers_route._check_vllm_status()
    assert offline.status == "offline"
    assert offline.reason_code == "connection_failed"


@pytest.mark.asyncio
async def test_activate_provider_offline_raises_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _offline(_provider: str):
        return providers_route.ProviderStatus(status="offline", message="down")

    monkeypatch.setattr(providers_route, "_check_provider_connection", _offline)

    with pytest.raises(HTTPException) as exc:
        await providers_route.activate_provider("openai", None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_activate_provider_openai_success_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _connected(_provider: str):
        return providers_route.ProviderStatus(status="connected")

    update_mock = MagicMock()
    monkeypatch.setattr(providers_route, "_check_provider_connection", _connected)
    monkeypatch.setattr(providers_route.config_manager, "update_config", update_mock)
    monkeypatch.setattr(
        providers_route.SETTINGS, "OPENAI_GPT4O_MODEL", "gpt-4o-default", raising=False
    )

    result = await providers_route.activate_provider("openai", None)
    assert result["status"] == "success"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4o-default"
    update_mock.assert_called_once()


@pytest.mark.asyncio
async def test_activate_provider_google_success_with_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _connected(_provider: str):
        return providers_route.ProviderStatus(status="connected")

    update_mock = MagicMock()
    monkeypatch.setattr(providers_route, "_check_provider_connection", _connected)
    monkeypatch.setattr(providers_route.config_manager, "update_config", update_mock)
    request = providers_route.ProviderActivateRequest(model="gemini-2.0-pro")

    result = await providers_route.activate_provider("google", request)
    assert result["status"] == "success"
    assert result["provider"] == "google"
    assert result["model"] == "gemini-2.0-pro"
    update_mock.assert_called_once()


@pytest.mark.asyncio
async def test_activate_provider_openai_update_failure_raises_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _connected(_provider: str):
        return providers_route.ProviderStatus(status="connected")

    def _raise(_payload: dict[str, str]):
        raise RuntimeError("cannot-save")

    monkeypatch.setattr(providers_route, "_check_provider_connection", _connected)
    monkeypatch.setattr(providers_route.config_manager, "update_config", _raise)
    monkeypatch.setattr(
        providers_route.SETTINGS, "OPENAI_GPT4O_MODEL", "gpt-4o-default", raising=False
    )

    with pytest.raises(HTTPException) as exc:
        await providers_route.activate_provider("openai", None)
    assert exc.value.status_code == 500
    assert "Failed to activate provider" in exc.value.detail


def _make_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {"type": "http", "method": "GET", "path": "/", "headers": raw_headers}
    )


def test_extract_user_prefers_request_state_user() -> None:
    request = _make_request({"x-user": "header-user"})
    request.state.user = "state-user"
    assert providers_route._extract_user_from_request(request) == "state-user"


def test_extract_user_falls_back_to_headers() -> None:
    request = _make_request({"x-authenticated-user": "header-user"})
    assert providers_route._extract_user_from_request(request) == "header-user"


def test_extract_user_returns_unknown_on_exception() -> None:
    class BrokenRequest:
        state = object()

        @property
        def headers(self):
            raise RuntimeError("headers unavailable")

    assert providers_route._extract_user_from_request(BrokenRequest()) == "unknown"


@pytest.mark.asyncio
async def test_get_provider_metrics_returns_empty_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_collector = SimpleNamespace(get_provider_metrics=lambda _provider: {})
    monkeypatch.setattr(
        "venom_core.core.metrics.get_metrics_collector", lambda: metrics_collector
    )

    result = await providers_route.get_provider_metrics("openai")
    assert result["status"] == "success"
    assert result["metrics"]["latency"]["samples"] == 0
    assert result["metrics"]["cost"]["total_usd"] == 0.0


@pytest.mark.asyncio
async def test_get_provider_health_serializes_slo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slo = SimpleNamespace(
        health_status=SimpleNamespace(value="healthy"),
        health_score=99.0,
        availability=0.999,
        latency_p99_ms=120.0,
        error_rate=0.001,
        cost_usage_usd=1.2,
        slo_target=SimpleNamespace(
            availability_target=0.99,
            latency_p99_ms=300.0,
            error_rate_target=0.02,
            cost_budget_usd=10.0,
        ),
        breaches=[],
    )
    observability = SimpleNamespace(
        calculate_slo_status=lambda _provider, _metrics: slo
    )
    metrics_collector = SimpleNamespace(
        get_provider_metrics=lambda _provider: {"requests": 1}
    )
    monkeypatch.setattr(
        "venom_core.core.provider_observability.get_provider_observability",
        lambda: observability,
    )
    monkeypatch.setattr(
        "venom_core.core.metrics.get_metrics_collector", lambda: metrics_collector
    )

    result = await providers_route.get_provider_health("openai")
    assert result["health"]["health_status"] == "healthy"
    assert result["health"]["slo_target"]["cost_budget_usd"] == 10.0


@pytest.mark.asyncio
async def test_get_alerts_filters_invalid_and_valid_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alert = SimpleNamespace(
        id="a1",
        severity=SimpleNamespace(value="critical"),
        alert_type=SimpleNamespace(value="latency"),
        provider="openai",
        message="high latency",
        technical_details={"p99_ms": 800},
        timestamp=datetime.now(timezone.utc),
        expires_at=None,
        metadata={},
    )
    observability = SimpleNamespace(
        get_active_alerts=lambda _provider=None: [alert],
        get_alert_summary=lambda: {"critical": 1},
    )
    monkeypatch.setattr(
        "venom_core.core.provider_observability.get_provider_observability",
        lambda: observability,
    )

    ok_result = await providers_route.get_alerts(provider="openai", severity="critical")
    assert ok_result["count"] == 1
    assert ok_result["alerts"][0]["severity"] == "critical"

    with pytest.raises(HTTPException) as exc:
        await providers_route.get_alerts(severity="invalid")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_test_provider_connection_success_and_error_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = providers_route.ProviderStatus(
        status="offline",
        reason_code="missing_api_key",
        message="missing key",
        latency_ms=5.0,
    )
    audit = MagicMock()
    monkeypatch.setattr(
        providers_route, "_check_provider_connection", AsyncMock(return_value=status)
    )
    monkeypatch.setattr("venom_core.core.admin_audit.get_audit_trail", lambda: audit)

    request = _make_request({"x-user": "qa-user"})
    result = await providers_route.test_provider_connection("openai", request)
    assert result["status"] == "failure"
    assert result["error_info"]["reason_code"] == "missing_api_key"
    audit.log_action.assert_called_once()


@pytest.mark.asyncio
async def test_provider_preflight_check_not_ready_and_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = providers_route.ProviderStatus(
        status="offline",
        reason_code="connection_failed",
        message="down",
    )
    audit = MagicMock()
    monkeypatch.setattr(
        providers_route, "_check_provider_connection", AsyncMock(return_value=status)
    )
    monkeypatch.setattr("venom_core.core.admin_audit.get_audit_trail", lambda: audit)
    monkeypatch.setattr(providers_route.SETTINGS, "OPENAI_API_KEY", "", raising=False)

    request = _make_request({"x-admin-user": "ops"})
    result = await providers_route.provider_preflight_check("openai", request)
    assert result["overall_status"] == "not_ready"
    assert result["checks"]["credentials"]["passed"] is False

    monkeypatch.setattr(
        providers_route,
        "_check_provider_connection",
        AsyncMock(side_effect=RuntimeError("preflight-fail")),
    )
    with pytest.raises(HTTPException) as exc:
        await providers_route.provider_preflight_check("openai", request)
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_admin_audit_log_caps_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = SimpleNamespace(
        timestamp=datetime.now(timezone.utc),
        action="test_connection",
        user="admin",
        provider="openai",
        details={},
        result="success",
        error_message=None,
    )
    audit = SimpleNamespace(get_entries=lambda **_kwargs: [entry])
    monkeypatch.setattr("venom_core.core.admin_audit.get_audit_trail", lambda: audit)

    result = await providers_route.get_admin_audit_log(limit=999)
    assert result["status"] == "success"
    assert result["count"] == 1
