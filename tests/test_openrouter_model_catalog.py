"""Model discovery and durable multi-model connections, using metadata fixtures."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from venom_core.api.routes import openrouter as routes
from venom_core.services import openrouter_model_catalog as catalog
from venom_core.services import openrouter_runtime as rt

_REAL_GET = catalog._get


def row(name="vendor/a", *, tools=True):
    return {
        "id": name,
        "name": name,
        "context_length": 8192,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "supported_parameters": ["tools"] if tools else [],
        "pricing": {"prompt": "0.000001", "completion": "0.000002", "request": "0"},
    }


def endpoint():
    return {
        "endpoints": [
            {
                "status": 0,
                "tag": "fixed-provider",
                "context_length": 8192,
                "max_completion_tokens": 1024,
                "supported_parameters": ["temperature", "max_tokens"],
                "pricing": {
                    "prompt": "0.000001",
                    "completion": "0.000002",
                    "request": "0",
                },
            }
        ]
    }


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_STATE", tmp_path / "state")
    monkeypatch.setattr(
        rt.SETTINGS, "OPENROUTER_MODELS_FILE", str(tmp_path / "legacy.json")
    )
    monkeypatch.setattr(rt, "is_enabled", lambda: True)
    monkeypatch.setattr(rt, "cloud_allowed", lambda: True)
    monkeypatch.setattr(rt, "credential", lambda: "fixture-only-secret")
    monkeypatch.setattr(catalog, "_CACHE", {})
    monkeypatch.setattr(catalog, "_CACHE_LOCK", asyncio.Lock())

    def prices(raw):
        for key in ["prompt", "completion", "request"]:
            if raw.get(key) is None:
                raise ValueError("pricing_unknown")
            if Decimal(raw[key]) < 0:
                raise ValueError("negative")
        a, b, c = (
            Decimal(raw["prompt"]) * 1000000,
            Decimal(raw["completion"]) * 1000000,
            Decimal(raw["request"]),
        )
        return SimpleNamespace(
            input_per_million=a,
            output_per_million=b,
            request=c,
            estimate=lambda i, o: (a * i + b * o) / 1000000 + c,
        )

    monkeypatch.setattr(
        rt,
        "library",
        lambda: SimpleNamespace(
            strict_prices=prices, decimal_amount=lambda v, *args: Decimal(str(v))
        ),
    )
    for key in [
        "OPENROUTER_MESSAGE_LIMIT_USD",
        "OPENROUTER_CONVERSATION_LIMIT_USD",
        "OPENROUTER_DAILY_LIMIT_USD",
    ]:
        monkeypatch.setattr(rt.SETTINGS, key, "1")

    async def metadata(path, params=None):
        return (
            [row("vendor/a"), row("vendor/b"), row("vendor/c", tools=False)]
            if path == "/models"
            else endpoint()
        )

    mock = AsyncMock(side_effect=metadata)
    monkeypatch.setattr(catalog, "_get", mock)
    return mock


@pytest.mark.asyncio
async def test_multiple_connections_survive_reopen_and_keep_selected_hash(state):
    await catalog.connect("vendor/a")
    rt.select_model("vendor/a")
    identity = rt.selection()
    digest = rt.config_hash("vendor/a")
    await catalog.connect("vendor/b")
    assert catalog.connected()["count"] == 2
    assert rt.config_hash("vendor/a") == digest
    assert rt.selection() == identity
    assert {x["id"] for x in rt.target_payload()["models"]} == {"vendor/a", "vendor/b"}
    assert len(json.loads(catalog._path().read_text())["models"]) == 2
    catalog.disconnect("vendor/b")
    assert rt.config_hash("vendor/a") == digest
    catalog.disconnect("vendor/a")
    assert catalog.connected()["count"] == 0
    assert rt.selection() == identity
    assert rt.configured_catalog()[1] == []
    with pytest.raises(HTTPException):
        rt.assert_identity(
            SimpleNamespace(
                expected_runtime_id="openrouter@vendor/a",
                expected_config_hash=digest,
                model="vendor/a",
            )
        )


@pytest.mark.asyncio
async def test_migrates_legacy_once_and_last_disconnect_cannot_revive_it(state):
    legacy = {**row(), "provider_endpoint": "fixed-provider", "max_output_tokens": 256}
    path = rt.SETTINGS.OPENROUTER_MODELS_FILE
    from pathlib import Path

    Path(path).write_text(
        json.dumps(
            {
                "pricing_as_of": datetime.now(timezone.utc).isoformat(),
                "models": [legacy],
            }
        )
    )
    assert catalog.connected()["count"] == 1
    catalog.disconnect("vendor/a")
    assert catalog.connected()["models"] == []
    await catalog.connect("vendor/b")
    assert [x["id"] for x in catalog.connected()["models"]] == ["vendor/b"]


@pytest.mark.asyncio
async def test_stale_model_is_visible_but_cannot_become_fresh_by_adding_another(state):
    await catalog.connect("vendor/a")
    data = json.loads(catalog._path().read_text())
    data["models"][0]["pricing_as_of"] = (
        datetime.now(timezone.utc) - timedelta(days=2)
    ).isoformat()
    catalog._path().write_text(json.dumps(data))
    await catalog.connect("vendor/b")
    connected = {x["id"]: x for x in catalog.connected()["models"]}
    assert not connected["vendor/a"]["available"]
    assert connected["vendor/b"]["available"]
    assert [x["id"] for x in rt.configured_catalog()[1]] == ["vendor/b"]
    await catalog.connect("vendor/a")
    assert all(x["available"] for x in catalog.connected()["models"])


@pytest.mark.asyncio
async def test_search_profiles_query_pagination_and_category_only_upstream(state):
    first = await catalog.search(limit=1)
    assert first["total"] == 3 and first["next_offset"] == 1
    assert (await catalog.search(purpose="tasks"))["count"] == 2
    assert (await catalog.search(q="B"))["models"][0]["id"] == "vendor/b"
    assert (await catalog.search(offset=10))["models"] == []
    await catalog.search(purpose="programming")
    state.assert_called_with("/models", {"category": "programming"})


@pytest.mark.parametrize(
    "model",
    [
        "openrouter/auto",
        "openrouter/free",
        "vendor/latest",
        "vendor/a-latest",
        "vendor/a:unknown",
        "vendor/a bad",
        "",
    ],
)
@pytest.mark.asyncio
async def test_dynamic_or_invalid_identity_rejected_before_metadata(state, model):
    with pytest.raises(HTTPException):
        await catalog.connect(model)
    state.assert_not_called()


@pytest.mark.asyncio
async def test_missing_model_and_unknown_tariff_are_not_connectable(state):
    with pytest.raises(HTTPException) as failure:
        await catalog.connect("vendor/absent")
    assert failure.value.status_code == 404
    data = endpoint()
    del data["endpoints"][0]["pricing"]["request"]
    state.side_effect = lambda path, params=None: [row()] if path == "/models" else data
    with pytest.raises(HTTPException) as failure:
        await catalog.connect("vendor/a")
    assert failure.value.detail == "openrouter_model_endpoint_unavailable"
    assert not catalog._path().exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"purpose": "other"},
        {"category": "other"},
        {"limit": 101},
        {"offset": -1},
        {"q": "x" * 121},
    ],
)
@pytest.mark.asyncio
async def test_invalid_search_inputs_do_not_contact_provider(state, kwargs):
    with pytest.raises(HTTPException):
        await catalog.search(**kwargs)
    state.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_policy_and_key_reject_metadata(state, monkeypatch):
    monkeypatch.setattr(rt, "is_enabled", lambda: False)
    with pytest.raises(HTTPException) as failure:
        await catalog.search()
    assert failure.value.detail == "openrouter_disabled"
    monkeypatch.setattr(rt, "is_enabled", lambda: True)
    monkeypatch.setattr(rt, "cloud_allowed", lambda: False)
    with pytest.raises(HTTPException) as failure:
        await catalog.search()
    assert failure.value.status_code == 403
    monkeypatch.setattr(rt, "cloud_allowed", lambda: True)
    monkeypatch.setattr(rt, "credential", lambda: "")
    with pytest.raises(HTTPException) as failure:
        await catalog.search()
    assert failure.value.detail == "openrouter_missing_credentials"
    state.assert_not_called()


@pytest.mark.asyncio
async def test_cache_is_reused_but_failures_do_not_become_cached_success(state):
    await catalog.search()
    await catalog.search()
    assert state.await_count == 1
    catalog._CACHE.clear()
    state.side_effect = HTTPException(502, "provider unavailable")
    with pytest.raises(HTTPException):
        await catalog.search()
    assert not catalog._CACHE


@pytest.mark.asyncio
async def test_routes_and_local_admin_guard(state):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 5)),
        base_url="http://localhost",
    ) as client:
        assert (await client.get("/api/v1/openrouter/models/search?limit=1")).json()[
            "count"
        ] == 1
        assert (
            await client.post(
                "/api/v1/openrouter/models/connect", json={"model_id": "vendor/a"}
            )
        ).json()["count"] == 1
        assert (await client.get("/api/v1/openrouter/models/connected")).json()[
            "count"
        ] == 1
        assert (
            await client.post(
                "/api/v1/openrouter/models/disconnect", json={"model_id": "vendor/a"}
            )
        ).json()["count"] == 0
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("203.0.113.4", 5)),
        base_url="http://localhost",
    ) as client:
        assert (
            await client.post(
                "/api/v1/openrouter/models/connect", json={"model_id": "vendor/a"}
            )
        ).status_code == 403


def test_corrupt_registry_never_falls_back_to_legacy(state):
    catalog._path().parent.mkdir(parents=True)
    catalog._path().write_text("broken")
    with pytest.raises(HTTPException):
        catalog.connected()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["success", "http", "invalid", "network"])
async def test_metadata_transport_sanitizes_errors(state, monkeypatch, kind):
    calls = []

    def handler(request):
        calls.append(request)
        if kind == "network":
            raise httpx.ConnectError("fixture-only-secret")
        if kind == "http":
            return httpx.Response(401, json={"error": "fixture-only-secret"})
        return httpx.Response(200, json={"data": []} if kind == "success" else [])

    client = httpx.AsyncClient
    monkeypatch.setattr(
        catalog.httpx,
        "AsyncClient",
        lambda **kw: client(transport=httpx.MockTransport(handler), **kw),
    )
    if kind == "success":
        assert await _REAL_GET("/models") == []
    else:
        with pytest.raises(HTTPException) as failure:
            await _REAL_GET("/models")
        assert "fixture-only-secret" not in str(failure.value.detail)
    assert len(calls) == 1 and calls[0].method == "GET"
    assert calls[0].url.host == "openrouter.ai"


@pytest.mark.asyncio
async def test_free_endpoint_and_connection_capacity(state, monkeypatch):
    model = row("vendor/a:free")
    data = endpoint()
    data["endpoints"][0]["pricing"] = {"prompt": "0", "completion": "0"}
    state.side_effect = (
        lambda path, params=None: [model, row("vendor/b")]
        if path == "/models"
        else (data if "a:free" in path else endpoint())
    )
    monkeypatch.setattr(catalog, "MAX_CONNECTED", 1)
    await catalog.connect("vendor/a:free")
    assert catalog.connected()["models"][0]["input_price_per_million"] == "0"
    with pytest.raises(HTTPException) as failure:
        await catalog.connect("vendor/b")
    assert failure.value.detail == "openrouter_connected_limit"


@pytest.mark.asyncio
async def test_malformed_optional_metadata_is_safe(state):
    malformed = {
        **row(),
        "pricing": None,
        "supported_parameters": None,
        "context_length": float("inf"),
    }
    state.return_value = [malformed]
    state.side_effect = None
    result = await catalog.search()
    assert result["models"][0]["input_price_per_million"] is None
    assert result["models"][0]["context_length"] is None
    assert not result["models"][0]["supports_tools"]
    assert (await catalog.search(purpose="tasks"))["models"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad", [None, [], {"input_modalities": None, "output_modalities": ["text"]}]
)
async def test_malformed_architecture_is_skipped(state, bad):
    malformed = {**row(), "architecture": bad}
    state.return_value = [malformed]
    state.side_effect = None
    assert (await catalog.search())["models"] == []
    with pytest.raises(HTTPException) as failure:
        await catalog.connect("vendor/a")
    assert failure.value.detail == "openrouter_text_chat_only"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        None,
        {"status": 0, "supported_parameters": None},
        {**endpoint()["endpoints"][0], "context_length": float("inf")},
    ],
)
async def test_malformed_endpoint_rejected(state, bad):
    state.side_effect = (
        lambda path, params=None: [row()] if path == "/models" else {"endpoints": [bad]}
    )
    with pytest.raises(HTTPException) as failure:
        await catalog.connect("vendor/a")
    assert failure.value.detail == "openrouter_model_endpoint_unavailable"
    assert not catalog._path().exists()
