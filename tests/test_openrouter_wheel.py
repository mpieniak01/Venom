"""Installed artifact qualification; explicitly enabled by the local release gate."""

import asyncio
import importlib
import json
import os
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from tests import test_openrouter_runtime as boundary
from tests.test_openrouter_runtime import authorized_request, consume
from venom_core.services import openrouter_chat as chat
from venom_core.services import openrouter_runtime as rt

configured = boundary.configured

pytestmark = pytest.mark.skipif(
    os.environ.get("EXECUTION_CORE_WHEEL_TEST") != "1",
    reason="Local wheel qualification required; private artifact not distributed to GitHub runners",
)


@pytest.fixture
def installed(configured, monkeypatch):
    core = importlib.import_module("agent_execution_core")
    expected = Path(os.environ["EXECUTION_CORE_INSTALLED_ROOT"]).resolve()
    assert Path(core.__file__).resolve().is_relative_to(expected)
    monkeypatch.setattr(rt, "library", lambda: core)
    rt.select_model("vendor/test")
    return core


def test_real_wheel_quote_and_completion(installed, monkeypatch):
    def endpoint(req):
        assert req.url == rt.ENDPOINT
        assert json.loads(req.content)["model"] == "vendor/test"
        packets = [
            {
                "id": "gen-test",
                "model": "vendor/test",
                "provider": "fixture",
                "choices": [{"delta": {"content": "Answer"}}],
            },
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 3,
                    "total_tokens": 23,
                    "cost": 0.0001,
                },
            },
        ]
        body = (
            ": keepalive\n\n"
            + "".join("data: " + json.dumps(x) + "\n\n" for x in packets)
            + "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body.encode())

    monkeypatch.setattr(
        chat,
        "client_factory",
        lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(endpoint), **kw),
    )
    item = authorized_request()
    quote = chat.quote(item)
    assert quote["input_token_upper_bound"] > len(item.content)
    assert not (rt._STATE / "budget.sqlite").exists(), (
        "Quote must not create the ledger"
    )
    body = consume(item)
    assert "event: done" in body and "Answer" in body and "gen-test" in body
    row = installed.BudgetLedger(rt._STATE / "budget.sqlite").snapshot()[
        "reservations"
    ][0]
    assert row["status"] == "settled" and row["cost"] == "0.0001"


def test_real_wheel_unknown_cost_survives_reopen(installed, monkeypatch):
    monkeypatch.setattr(
        chat,
        "client_factory",
        lambda **kw: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    content=b'data: {"choices":[{"delta":{"content":"A"}}]}\n\ndata: [DONE]\n\n',
                )
            ),
            **kw,
        ),
    )
    body = consume(authorized_request())
    assert '"state": "pending"' in body
    row = installed.BudgetLedger(rt._STATE / "budget.sqlite").snapshot()[
        "reservations"
    ][0]
    assert row["status"] == "pending" and row["cost"] is None


def test_real_wheel_stop_keeps_reservation(installed, monkeypatch):
    class Waiting(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"id":"gen-stop","model":"vendor/test","choices":[{"delta":{"content":"A"}}]}\n\n'
            await asyncio.Event().wait()

    def endpoint(req):
        return httpx.Response(200, stream=Waiting())

    monkeypatch.setattr(
        chat,
        "client_factory",
        lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(endpoint), **kw),
    )

    async def run():
        response = await chat.response(authorized_request())
        iterator = response.body_iterator
        assert "event: cost" in await anext(iterator)
        assert "event: start" in await anext(iterator)
        assert "event: content" in await anext(iterator)
        await iterator.aclose()

    asyncio.run(run())
    row = installed.BudgetLedger(rt._STATE / "budget.sqlite").snapshot()[
        "reservations"
    ][0]
    assert row["status"] == "pending"
    receipt = json.loads(next((rt._STATE / "requests").glob("*.json")).read_text())
    assert receipt["state"] == "pending"
    assert "test-secret" not in json.dumps(receipt)


def test_real_wheel_invalid_price_prevents_execution(installed, configured):
    _, _, path = configured
    raw = json.loads(path.read_text())
    del raw["models"][0]["pricing"]["completion"]
    path.write_text(json.dumps(raw))
    with pytest.raises(HTTPException):
        rt.require_ready()


def test_public_direct_route_with_actual_installed_wheel(installed, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from venom_core.api.routes import llm_simple, openrouter
    from venom_core.api.routes.system_config import require_localhost_request
    from venom_core.services import llm_simple_service

    monkeypatch.setattr(
        llm_simple_service, "assert_runtime_request_allowed", lambda **kw: None
    )
    data = b'data: {"model":"vendor/test","choices":[{"delta":{"content":"HTTP answer"}}]}\n\ndata: [DONE]\n\n'
    monkeypatch.setattr(
        chat,
        "client_factory",
        lambda **kw: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, content=data)
            ),
            **kw,
        ),
    )
    app = FastAPI()
    app.include_router(llm_simple.router)
    app.include_router(openrouter.router, prefix="/api/v1")
    app.dependency_overrides[require_localhost_request] = lambda: None
    item = authorized_request()
    with TestClient(app) as client:
        quote = client.post("/api/v1/openrouter/quote", json=item.model_dump())
        assert quote.status_code == 200
        item.expected_quote_hash = quote.json()["quote_hash"]
        result = client.post("/api/v1/llm/simple/stream", json=item.model_dump())
        assert result.status_code == 200
        assert "HTTP answer" in result.text and "event: done" in result.text
