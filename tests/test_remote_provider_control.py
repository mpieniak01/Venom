"""External API administration never provisions hosts or generates model output."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from venom_core.api.routes import models_remote as routes
from venom_core.services import openrouter_runtime as ort
from venom_core.services import remote_provider_control as control
from venom_core.services import vast_chat_runtime as vrt


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "_STATE", tmp_path / "providers" / "control.json")
    monkeypatch.setattr(control, "_CHECKS", {})
    monkeypatch.setattr(
        ort, "status", lambda: {"configured": True, "active": False, "reason": None}
    )
    monkeypatch.setattr(ort, "credential", lambda: "fixture-secret")
    monkeypatch.setattr(ort, "cloud_allowed", lambda: True)
    monkeypatch.setattr(ort.SETTINGS, "OPENROUTER_ENABLED", True)
    monkeypatch.setattr(
        ort,
        "configured_catalog",
        lambda: ("fixture", [{"id": "fixture/model", "name": "fixture/model"}]),
    )
    state = {
        "available": False,
        "target_id": "fixture",
        "models": [],
        "error": "offline",
    }
    connection = SimpleNamespace(status=Mock(side_effect=lambda **kw: dict(state)))
    monkeypatch.setattr(vrt, "connection", lambda: connection)
    monkeypatch.setattr(vrt, "selection", lambda: None)
    return state, connection


def test_controls_persist_without_changing_selection_or_connecting(isolated):
    _, connection = isolated
    for provider in control.PROVIDERS:
        control.set_enabled(provider, False)
        assert not control.enabled(provider)
        control.set_enabled(provider, True)
        assert control.enabled(provider)
    connection.status.assert_not_called()
    assert "fixture-secret" not in control._STATE.read_text()


@pytest.mark.parametrize(
    "raw", ["[]", '{"openrouter":"true"}', '{"unknown":true}', "broken"]
)
def test_corrupt_controls_fail_closed(raw):
    control._STATE.parent.mkdir()
    control._STATE.write_text(raw)
    assert not control.enabled("openrouter")
    with pytest.raises(HTTPException):
        control.set_enabled("openrouter", True)


def test_unknown_provider_rejected():
    with pytest.raises(HTTPException) as failure:
        control.set_enabled("other", True)
    assert failure.value.status_code == 400


def test_status_does_not_claim_authentication_or_probe_vast(isolated):
    _, connection = isolated
    info = control.status("openrouter")
    assert info["available"] is None
    assert info["last_check"] is None
    control.status("vast_ollama")
    connection.status.assert_called_once_with(refresh=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [200, 401])
async def test_openrouter_check_is_metadata_only(monkeypatch, status_code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status_code, json={"data": {}})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        control.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    result = await control.check("openrouter")
    assert result["available"] is (status_code == 200)
    assert len(calls) == 1 and calls[0].method == "GET"
    assert str(calls[0].url) == "https://openrouter.ai/api/v1/key"
    assert "fixture-secret" not in str(result)


@pytest.mark.asyncio
async def test_openrouter_connection_error_is_sanitized(monkeypatch):
    def fail(request):
        raise httpx.ConnectError("fixture-secret")

    real = httpx.AsyncClient
    monkeypatch.setattr(
        control.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(fail), **kw),
    )
    info = await control.check("openrouter")
    assert info["available"] is False
    assert info["error"] == "openrouter_connection_unavailable"
    assert "fixture-secret" not in str(info)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["disabled", "credentials", "policy"])
async def test_unapproved_checks_never_contact_openrouter(monkeypatch, reason):
    client = Mock(side_effect=AssertionError("unexpected network"))
    monkeypatch.setattr(control.httpx, "AsyncClient", client)
    if reason == "disabled":
        control.set_enabled("openrouter", False)
    if reason == "credentials":
        monkeypatch.setattr(
            ort,
            "status",
            lambda: {"configured": False, "active": False, "reason": None},
        )
    if reason == "policy":
        monkeypatch.setattr(ort, "cloud_allowed", lambda: False)
    assert (await control.check("openrouter"))["available"] is False
    client.assert_not_called()


@pytest.mark.asyncio
async def test_vast_check_and_disabled_generation_preserve_selection(
    isolated, monkeypatch
):
    state, connection = isolated
    assert (await control.check("vast_ollama"))["available"] is False
    state.update(available=True, models=[{"name": "fixture/model"}])
    assert (await control.check("vast_ollama"))["available"] is True
    assert control.catalog("vast_ollama")[0]["id"] == "fixture/model"
    selected = {"model": "fixture/model", "target_id": "fixture", "digest": "digest"}
    monkeypatch.setattr(vrt, "selection", lambda: selected)
    control.set_enabled("vast_ollama", False)
    connection.status.reset_mock()
    with pytest.raises(HTTPException) as failure:
        await vrt.preflight()
    assert failure.value.detail == "vast_chat_disabled"
    connection.status.assert_not_called()
    assert vrt.selection() == selected
    assert control.catalog("vast_ollama") == []


def test_disabled_openrouter_blocks_runtime_without_erasing_identity(monkeypatch):
    control.set_enabled("openrouter", False)
    with pytest.raises(HTTPException) as failure:
        ort.require_ready()
    assert failure.value.detail == "openrouter_disabled"
    assert control.catalog("openrouter") == []
    control.set_enabled("openrouter", True)
    assert control.catalog("openrouter")[0]["id"] == "fixture/model"


@pytest.mark.asyncio
async def test_remote_routes_enable_check_and_catalog(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    monkeypatch.setattr(control, "check", AsyncMock(return_value={"available": True}))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
        base_url="http://localhost",
    ) as client:
        result = await client.post(
            "/api/v1/models/remote/providers/openrouter/enable", json={"enabled": False}
        )
        assert result.status_code == 200 and result.json()["enabled"] is False
        assert (
            await client.post("/api/v1/models/remote/providers/openrouter/check")
        ).json()["available"] is True
        assert (
            await client.get("/api/v1/models/remote/catalog?provider=openrouter")
        ).json()["models"] == []
        assert (
            await client.post(
                "/api/v1/models/remote/providers/unknown/enable", json={"enabled": True}
            )
        ).status_code == 400
        assert (
            await client.post(
                "/api/v1/models/remote/providers/openrouter/enable",
                json={"enabled": "false"},
            )
        ).status_code == 422


@pytest.mark.asyncio
async def test_provider_controls_reject_nonlocal_mutations():
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("203.0.113.8", 1234)),
        base_url="http://localhost",
    ) as client:
        assert (
            await client.post(
                "/api/v1/models/remote/providers/openrouter/enable",
                json={"enabled": True},
            )
        ).status_code == 403
        assert (
            await client.post("/api/v1/models/remote/providers/openrouter/check")
        ).status_code == 403


@pytest.mark.asyncio
async def test_malformed_success_is_not_authenticated(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(
        control.httpx,
        "AsyncClient",
        lambda **kw: real(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text="not JSON")
            ),
            **kw,
        ),
    )
    assert (await control.check("openrouter"))["available"] is False
