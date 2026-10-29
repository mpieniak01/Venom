"""Provider-boundary regressions run without a real provider or private package."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from venom_core.api.schemas.llm_simple import SimpleChatRequest
from venom_core.config import SETTINGS
from venom_core.services import openrouter_chat as chat
from venom_core.services import openrouter_runtime as rt


@pytest.fixture
def configured(tmp_path, monkeypatch):
    prices = SimpleNamespace(
        input_per_million=Decimal("0.3"),
        output_per_million=Decimal("1.5"),
        request=Decimal("0"),
        estimate=Mock(return_value=Decimal("0.001")),
    )
    ledger = Mock()

    class ExecutionBoundary:
        # Boundary stub only: lifecycle semantics are tested with the real wheel.
        def __init__(self, ledger, request_id, conversation_id, amount, **limits):
            self.reserve = lambda: ledger.reserve(
                request_id, conversation_id, amount, **limits
            )
            self.settle = lambda actual: ledger.settle(request_id, actual)
            self.pending = lambda: ledger.settle(request_id, None)

    core = SimpleNamespace(
        Execution=ExecutionBoundary,
        strict_prices=Mock(return_value=prices),
        decimal_amount=lambda v, *_: Decimal(v),
        BudgetLedger=Mock(return_value=ledger),
        ModelSpec=lambda model_id, *args: SimpleNamespace(model_id=model_id),
        ChatRequest=lambda **v: SimpleNamespace(**v),
        build_chat_payload=lambda r: {
            "model": r.model.model_id,
            "messages": r.messages,
            "max_tokens": r.max_tokens,
            "temperature": r.temperature,
            "stream": True,
        },
        SSEDecoder=Mock(),
        usage_cost=lambda u: Decimal(u["cost"]) if "cost" in u else None,
    )
    monkeypatch.setattr(rt, "library", lambda: core)
    monkeypatch.setattr(rt, "_STATE", tmp_path / "state")
    catalog = tmp_path / "catalog.json"
    row = {
        "id": "vendor/test",
        "provider_endpoint": "test-provider",
        "context_length": 8192,
        "max_output_tokens": 1024,
        "pricing": {"prompt": "0.0000003", "completion": "0.0000015", "request": "0"},
    }
    catalog.write_text(
        json.dumps(
            {"pricing_as_of": datetime.now(timezone.utc).isoformat(), "models": [row]}
        )
    )
    for k, v in {
        "OPENROUTER_ENABLED": True,
        "AI_MODE": "CLOUD",
        "SENSITIVE_DATA_LOCAL_ONLY": False,
        "OPENROUTER_API_KEY": "test-secret",
        "OPENROUTER_MODELS_FILE": str(catalog),
        "OPENROUTER_MESSAGE_LIMIT_USD": "0.01",
        "OPENROUTER_CONVERSATION_LIMIT_USD": "0.1",
        "OPENROUTER_DAILY_LIMIT_USD": "1",
    }.items():
        monkeypatch.setattr(SETTINGS, k, v)

    @asynccontextmanager
    async def admitted(**kwargs):
        yield None

    monkeypatch.setattr(chat, "runtime_request_guard", admitted)
    monkeypatch.setattr(chat, "_ACTIVE", asyncio.Lock())
    rt.select_model("vendor/test")
    return core, ledger, catalog


def request():
    runtime = rt.runtime_override()
    return SimpleChatRequest(
        content="Hello",
        model=runtime.model_name,
        session_id="session",
        expected_runtime_id=runtime.runtime_id,
        expected_config_hash=runtime.config_hash,
    )


def authorized_request():
    value = request()
    value.expected_quote_hash = chat.quote(value)["quote_hash"]
    return value


def test_quote_is_offline_unreserved_and_bound_to_content(configured):
    core, ledger, _ = configured
    value = authorized_request()
    quote = chat.quote(value)
    assert quote["estimated_usd"] == "0.001"
    assert quote["reserved_usd"] == "0"
    ledger.reserve.assert_not_called()
    value.content = "changed"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat.response(value))
    assert exc.value.status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("OPENROUTER_ENABLED", False),
        ("AI_MODE", "LOCAL"),
        ("SENSITIVE_DATA_LOCAL_ONLY", True),
        ("OPENROUTER_API_KEY", ""),
        ("OPENROUTER_DAILY_LIMIT_USD", "0"),
    ],
)
def test_policy_denies_before_reservation(configured, monkeypatch, field, value):
    _, ledger, _ = configured
    item = request()
    monkeypatch.setattr(SETTINGS, field, value)
    with pytest.raises(HTTPException):
        chat.prepare(item)
    ledger.reserve.assert_not_called()


def test_status_never_claims_authentication_or_returns_key(configured):
    value = rt.status()
    assert value["authenticated"] is None
    assert value["available"] is True
    assert "test-secret" not in json.dumps(value)


def test_config_change_invalidates_captured_identity(configured, monkeypatch):
    item = request()
    monkeypatch.setattr(SETTINGS, "OPENROUTER_MESSAGE_LIMIT_USD", "0.02")
    with pytest.raises(HTTPException) as exc:
        chat.prepare(item)
    assert exc.value.status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"model": "not-approved"},
        {"expected_runtime_id": None},
        {"expected_config_hash": None},
        {"session_id": None},
        {"tools": []},
        {"max_tokens": 2000},
        {"content": "x" * 9000},
    ],
)
def test_invalid_request_fails_before_reservation(configured, change):
    _, ledger, _ = configured
    item = request().model_copy(update=change)
    with pytest.raises(HTTPException):
        chat.prepare(item)
    ledger.reserve.assert_not_called()


def test_stale_and_duplicate_catalog_rejected(configured):
    _, _, path = configured
    data = json.loads(path.read_text())
    data["pricing_as_of"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(data))
    with pytest.raises(HTTPException):
        rt.configured_catalog()
    data["pricing_as_of"] = datetime.now(timezone.utc).isoformat()
    data["models"] *= 2
    path.write_text(json.dumps(data))
    with pytest.raises(HTTPException):
        rt.configured_catalog()


class Decoder:
    def __init__(self, kind):
        self.kind = kind

    def feed(self, data):
        if self.kind == "error":
            return [{"type": "error", "code": "hidden"}]
        values = [
            {
                "type": "metadata",
                "model": "vendor/test",
                "generation_id": "gen-1",
                "provider": "test-provider",
            },
            {"type": "text", "text": "Hello"},
        ]
        if self.kind == "settled":
            values.append(
                {
                    "type": "usage",
                    "usage": {
                        "prompt_tokens": 2,
                        "completion_tokens": 1,
                        "cost": "0.0001",
                    },
                }
            )
        if self.kind != "incomplete":
            values.append({"type": "done"})
        return values

    def finish(self):
        return []


def consume(value):
    async def run():
        response = await chat.response(value)
        return "".join([chunk async for chunk in response.body_iterator])

    return asyncio.run(run())


@pytest.mark.parametrize(
    "kind", ["settled", "pending", "error", "incomplete", "http_error"]
)
def test_single_post_and_settlement_semantics(configured, monkeypatch, kind):
    core, ledger, _ = configured
    core.SSEDecoder = lambda: Decoder(kind)
    calls = []

    def endpoint(req):
        calls.append(req)
        return httpx.Response(429 if kind == "http_error" else 200, content=b"fixture")

    monkeypatch.setattr(
        chat,
        "client_factory",
        lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(endpoint), **kw),
    )
    value = authorized_request()
    body = consume(value)
    assert len(calls) == 1
    assert calls[0].url == rt.ENDPOINT
    assert calls[0].headers["Authorization"] == "Bearer test-secret"
    payload = json.loads(calls[0].content)
    assert payload["provider"]["allow_fallbacks"] is False
    ledger.reserve.assert_called_once()
    if kind == "settled":
        ledger.settle.assert_called_once_with(
            ledger.reserve.call_args.args[0], Decimal("0.0001")
        )
        assert "event: done" in body and '"reported_usd": "0.0001"' in body
    else:
        ledger.settle.assert_called_once_with(ledger.reserve.call_args.args[0], None)
        assert '"state": "pending"' in body
    if kind in {"error", "incomplete", "http_error"}:
        assert "event: done" not in body
    assert "test-secret" not in body


def test_busy_request_has_no_reservation(configured):
    _, ledger, _ = configured

    async def run():
        async with chat._ACTIVE:
            with pytest.raises(HTTPException):
                await chat.response(request())

    asyncio.run(run())
    ledger.reserve.assert_not_called()


def test_never_started_generator_does_not_reserve(configured):
    _, ledger, _ = configured
    asyncio.run(chat.response(authorized_request()))
    ledger.reserve.assert_not_called()


def test_ledger_rejection_prevents_post(configured, monkeypatch):
    _, ledger, _ = configured
    ledger.reserve.side_effect = ValueError("budget_exceeded")
    client = Mock()
    monkeypatch.setattr(chat, "client_factory", client)
    body = consume(authorized_request())
    assert "openrouter_budget_exceeded" in body
    client.assert_not_called()
    ledger.settle.assert_not_called()


def test_selection_corruption_cannot_fall_back_local(configured):
    (rt._STATE / "selection.json").write_text("invalid")
    assert rt.runtime_override().provider == "openrouter"
    with pytest.raises(HTTPException):
        chat.prepare(request())


def test_missing_library_is_actionable(monkeypatch):
    def missing(name):
        raise ImportError("hidden")

    monkeypatch.setattr(rt.importlib, "import_module", missing)
    # Use original implementation captured before fixture patching.
    with pytest.raises(HTTPException) as exc:
        rt.library()
    assert exc.value.detail == "openrouter_library_unavailable"


def test_direct_only_guard(configured):
    from venom_core.services.runtime_switch_gate import assert_runtime_request_allowed

    with pytest.raises(HTTPException) as exc:
        assert_runtime_request_allowed(request_kind="normal")
    assert exc.value.detail == "openrouter_direct_only"


def test_quote_route(configured):
    from venom_core.api.routes.openrouter import router
    from venom_core.api.routes.system_config import require_localhost_request

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[require_localhost_request] = lambda: None
    with TestClient(app) as client:
        assert client.get("/api/v1/openrouter/status").status_code == 200
        assert (
            client.post(
                "/api/v1/openrouter/quote", json=request().model_dump()
            ).status_code
            == 200
        )


def test_zero_price_is_not_proof_of_reported_zero_cost(configured, monkeypatch):
    core, ledger, _ = configured
    core.strict_prices.return_value.estimate.return_value = Decimal("0")
    core.SSEDecoder = lambda: Decoder("pending")
    monkeypatch.setattr(
        chat,
        "client_factory",
        lambda **kw: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, content=b"fixture")
            ),
            **kw,
        ),
    )
    body = consume(authorized_request())
    assert '"reported_usd": null' in body
    assert '"state": "pending"' in body
    ledger.settle.assert_called_once_with(ledger.reserve.call_args.args[0], None)


def test_credential_bridge_private_atomic_and_no_escape(tmp_path):
    from scripts.openrouter_credential_bridge import store_credential

    root = tmp_path / "repo"
    destination = root / ".venom_runtime/openrouter/credential"
    secret = "sk-or-v1-" + ("a" * 32)
    store_credential(root, destination, secret)
    assert destination.read_text() == secret
    assert destination.stat().st_mode & 0o777 == 0o600
    assert destination.parent.stat().st_mode & 0o777 == 0o700
    with pytest.raises(ValueError):
        store_credential(root, tmp_path / "outside", secret)
    with pytest.raises(ValueError):
        store_credential(root, destination, "bad\nsecret")
    assert destination.read_text() == secret


def test_credential_file_permissions_and_missing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(SETTINGS, "OPENROUTER_API_KEY", "")
    file = tmp_path / "credential"
    monkeypatch.setattr(SETTINGS, "OPENROUTER_CREDENTIAL_FILE", str(file))
    assert rt.credential() == ""
    file.write_text("test")
    file.chmod(0o644)
    assert rt.credential() == ""
    file.chmod(0o600)
    assert rt.credential() == "test"


def test_release_gate_rejects_different_artifact_and_peer(tmp_path):
    import hashlib

    from scripts.qualify_openrouter_local import verify_artifact

    wheel = tmp_path / "agent_execution_core-0.2.0-py3-none-any.whl"
    wheel.write_bytes(b"fixture")
    receipt = {
        "package": "agent-execution-core",
        "version": "0.2.0",
        "wheel": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "source_commit": "a" * 40,
    }
    peer = {
        "receipt": receipt,
        "environment": "windows-host",
        "consumer_head": "b" * 40,
        "groups": [
            {"group": "library", "returncode": 0},
            {"group": "orchestration", "returncode": 0},
        ],
    }
    verify_artifact(wheel, receipt, peer)
    with pytest.raises(ValueError):
        verify_artifact(wheel, {**receipt, "version": "9"}, peer)
    with pytest.raises(ValueError):
        verify_artifact(
            wheel,
            {**receipt, "source_commit": "bad"},
            dict(peer, receipt={**receipt, "source_commit": "bad"}),
        )
    with pytest.raises(ValueError):
        verify_artifact(wheel, receipt, dict(peer, groups=[]))
    with pytest.raises(ValueError):
        verify_artifact(
            wheel, receipt, dict(peer, groups=[{"returncode": 1}, {"returncode": 0}])
        )
    wheel.write_bytes(b"changed")
    with pytest.raises(ValueError):
        verify_artifact(wheel, receipt, peer)


def test_cancelled_turn_retains_provider_identity_without_text(configured, monkeypatch):
    core, _, _ = configured
    core.SSEDecoder = lambda: Decoder("pending")
    monkeypatch.setattr(
        chat,
        "client_factory",
        lambda **kw: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, content=b"fixture")
            ),
            **kw,
        ),
    )

    async def run():
        response = await chat.response(authorized_request())
        iterator = response.body_iterator
        await anext(iterator)
        await anext(iterator)
        await anext(iterator)
        await iterator.aclose()

    asyncio.run(run())
    receipt = json.loads(next((rt._STATE / "requests").glob("*.json")).read_text())
    assert receipt["generation_id"] == "gen-1"
    assert receipt["requested_model"] == "vendor/test" and receipt["state"] == "pending"
    assert "test-secret" not in json.dumps(receipt) and "Hello" not in json.dumps(
        receipt
    )


def test_explicit_free_variant_retains_requested_identity(configured, monkeypatch):
    core, _, path = configured
    raw = json.loads(path.read_text())
    raw["models"][0]["id"] = "vendor/test:free"
    path.write_text(json.dumps(raw))
    rt.select_model("vendor/test:free")
    core.SSEDecoder = lambda: Decoder("pending")
    monkeypatch.setattr(
        chat,
        "client_factory",
        lambda **kw: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, content=b"fixture")
            ),
            **kw,
        ),
    )
    body = consume(authorized_request())
    assert "event: done" in body
    assert '"requested_model": "vendor/test:free"' in body
    assert '"confirmed_model": "vendor/test"' in body


def test_free_variant_conversation_namespace_cannot_collide(configured):
    _, _, path = configured
    first = request()
    first.session_id = "free:session"
    one = chat.prepare(first)["conversation"]
    raw = json.loads(path.read_text())
    raw["models"][0]["id"] = "vendor/test:free"
    path.write_text(json.dumps(raw))
    rt.select_model("vendor/test:free")
    second = request()
    second.session_id = "session"
    turn = chat.prepare(second)
    assert one != turn["conversation"]
    assert turn["payload"]["provider"]["max_price"] == {
        "prompt": 0,
        "completion": 0,
        "request": 0,
    }
