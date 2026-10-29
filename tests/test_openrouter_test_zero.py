"""Manual test-zero selection and live semantics are verified with fake HTTP only."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from scripts.cloud.openrouter import test_zero as smoke

MODEL = "vendor/small:free"
ROW = {
    "id": MODEL,
    "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
    "pricing": {"prompt": "0", "completion": "0"},
    "supported_parameters": ["max_tokens", "temperature"],
}


def core():
    def prices(raw):
        if not {"prompt", "completion", "request"} <= raw.keys():
            raise ValueError("unknown")
        return SimpleNamespace(
            estimate=lambda i, o: Decimal(raw["prompt"]) * i
            + Decimal(raw["completion"]) * o
            + Decimal(raw["request"])
        )

    return SimpleNamespace(
        strict_prices=prices,
        ModelSpec=lambda model, *a: SimpleNamespace(model_id=model),
        ChatRequest=lambda **kw: SimpleNamespace(**kw),
        build_chat_payload=lambda req: {
            "model": req.model.model_id,
            "messages": req.messages,
            "stream": True,
            "max_tokens": req.max_tokens,
        },
    )


def test_default_is_read_only_and_zero_budget():
    calls = []

    def endpoint(req):
        calls.append(req)
        if req.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {}})
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [ROW]})
        return httpx.Response(
            200,
            json={
                "data": {
                    "endpoints": [dict(ROW, model_id=MODEL, status=0, tag="fixed")]
                }
            },
        )

    def factory(**kw):
        return httpx.Client(transport=httpx.MockTransport(endpoint), **kw)

    report = smoke.run("fixture-key", core(), client_factory=factory)
    assert report["authenticated"]
    assert not report["response_confirmed"]
    assert report["generation_requests"] == 0
    assert report["selected_model"] == MODEL
    assert all(r.method == "GET" for r in calls)
    assert "fixture-key" not in str(report)


def test_missing_prices_and_aliases_cannot_win_selection():
    bad = dict(ROW, id="openrouter/auto")
    unknown = dict(ROW, id="vendor/missing", pricing={"prompt": "0"})
    paid = dict(
        ROW,
        id="vendor/paid",
        pricing={"prompt": "1", "completion": "1", "request": "0"},
    )
    assert smoke.ranked_models([bad, unknown, paid, ROW], core(), Decimal("0")) == [
        (Decimal("0"), MODEL)
    ]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_metadata_http_errors_are_sanitized(status):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(status, text="private-error")
        )
    ) as client:
        with pytest.raises(smoke.TestZeroError) as exc:
            smoke.get_json(client, "/key")
    assert str(exc.value) == "metadata_http_" + str(status)


def test_generation_failure_has_no_retry_and_preserves_preflight(monkeypatch):
    calls = []

    def endpoint(req):
        calls.append(req)
        if req.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {}})
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [ROW]})
        return httpx.Response(
            200,
            json={
                "data": {
                    "endpoints": [dict(ROW, model_id=MODEL, status=0, tag="fixed")]
                }
            },
        )

    def factory(**kw):
        return httpx.Client(transport=httpx.MockTransport(endpoint), **kw)

    attempts = []

    async def fail(*a):
        attempts.append(1)
        raise smoke.TestZeroError("generation_http_429")

    monkeypatch.setattr(smoke, "generate", fail)
    report = smoke.run("fixture", core(), live=True, client_factory=factory)
    assert report["authenticated"]
    assert report["models_visible"] == 1
    assert report["status"] == "failed"
    assert report["generation_requests"] == 1
    assert len(attempts) == 1


def test_answer_validation():
    state = {
        "text": "",
        "done": False,
        "usage": {},
        "generation_id": None,
        "confirmed_model": None,
        "confirmed_provider": None,
    }
    smoke.apply_event({"type": "text", "text": "OK"}, state)
    smoke.apply_event(
        {"type": "metadata", "model": MODEL, "generation_id": "gen"}, state
    )
    smoke.apply_event({"type": "done"}, state)
    assert state["done"]
    assert state["text"] == "OK"
    assert state["generation_id"] == "gen"
    with pytest.raises(smoke.TestZeroError):
        smoke.apply_event({"type": "error"}, state)


def test_invalid_local_payload_never_counts_as_generation(monkeypatch):
    api = core()
    monkeypatch.setattr(
        smoke, "generation_payload", Mock(side_effect=ValueError("invalid"))
    )

    def endpoint(req):
        if req.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {}})
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [ROW]})
        return httpx.Response(
            200,
            json={
                "data": {
                    "endpoints": [dict(ROW, model_id=MODEL, status=0, tag="fixed")]
                }
            },
        )

    def factory(**kw):
        return httpx.Client(transport=httpx.MockTransport(endpoint), **kw)

    report = smoke.run("fixture", api, live=True, client_factory=factory)
    assert report["generation_requests"] == 0
    assert report["reason"] == "local_request_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,reason",
    [
        ("success", None),
        ("marker", "answer_marker_missing"),
        ("model", "model_identity_mismatch"),
        ("cost", "reported_cost_exceeds_reservation"),
        ("incomplete", "no_completed_text_answer"),
        ("http", "generation_http_429"),
    ],
)
async def test_generate_validates_one_mocked_completion(case, reason):
    api = core()
    events = [
        {"type": "text", "text": "wrong" if case == "marker" else smoke.MARKER},
        {"type": "metadata", "model": "wrong/model" if case == "model" else MODEL},
    ]
    if case != "incomplete":
        events.append({"type": "done"})
    api.SSEDecoder = lambda: SimpleNamespace(feed=lambda raw: events, finish=lambda: [])
    api.usage_cost = lambda usage: Decimal("1" if case == "cost" else "0")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429 if case == "http" else 200, content=b"fixture")

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    candidate = {"model": MODEL, "provider": "fixed", "estimate": Decimal("0")}
    if reason is None:
        report = await smoke.generate(
            api, "fixture", candidate, factory, payload={"fixture": True}
        )
        assert report["answered"] is True
        assert report["accounting"] == "settled"
        assert report["reported_usd"] == "0"
    else:
        with pytest.raises(smoke.TestZeroError, match=reason):
            await smoke.generate(
                api, "fixture", candidate, factory, payload={"fixture": True}
            )
    assert len(calls) == 1
    assert calls[0].method == "POST"
