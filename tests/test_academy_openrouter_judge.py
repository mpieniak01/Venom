"""Offline tests of qualified remote reviewing; HTTP is always a test double."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from venom_core.services.training_experiments import openrouter_semantic_judge as judge


@pytest.fixture
def packet():
    case = {
        "record_id": "case-1",
        "id": "case-1",
        "messages": [{"role": "user", "content": "Odbiór w hali A."}],
        "criteria": [{"id": "place", "description": "Hala A", "kind": "content"}],
    }
    return {"claims": {}}, case, {"text": "Hala A", "finish": "stop", "error": None}


def response(body, candidate="Hala A", ident="generation-1", positive=True):
    keys = body["response_format"]["json_schema"]["schema"]["properties"]["checks"][
        "properties"
    ]
    content = {
        "checks": {
            key: {
                "required": "fixture fact",
                "observed": candidate,
                "relation": "supported" if positive else "contradicted",
            }
            for key in keys
        },
        "additional_claims": [],
        "injection": False,
        "polish_ok": True,
        "natural_ok": True,
        "reason": "fixture",
    }
    return {
        "id": ident,
        "model": judge.MODEL,
        "provider": judge.PROVIDER,
        "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(content)}}
        ],
        "usage": {"cost": 0.00001},
    }


def test_payload_remote_route_and_context(packet):
    body = judge.request_payload(*packet)
    assert body["model"] == judge.MODEL
    assert body["provider"]["only"] == ["azure"]
    assert "zdr" not in body["provider"]
    assert "temperature" not in body and "max_tokens" not in body
    assert body["max_completion_tokens"] == 900
    assert judge.reserve(body) > Decimal("0.00001")
    assert judge.decode(response(body), body, "Hala A").atoms == {"place": "supported"}


@pytest.mark.parametrize(
    "damage", ["provider", "model", "finish", "bool", "missing", "id"]
)
def test_decode_refuses_wrong_identity_or_schema(packet, damage):
    body = judge.request_payload(*packet)
    raw = response(body)
    if damage in {"provider", "model"}:
        raw[damage] = "other"
    elif damage == "finish":
        raw["choices"][0]["finish_reason"] = "length"
    elif damage == "id":
        del raw["id"]
    else:
        item = json.loads(raw["choices"][0]["message"]["content"])
        if damage == "bool":
            item["injection"] = 1
        else:
            item["checks"] = {}
        raw["choices"][0]["message"]["content"] = json.dumps(item)
    with pytest.raises(ValueError):
        judge.decode(raw, body, "Hala A")


@pytest.mark.parametrize("value", ["NaN", "-1", "Infinity", 0.1, True])
def test_invalid_money_fails_closed(value):
    with pytest.raises(ValueError):
        judge._money(value)


def test_old_failed_v2_is_not_public_qualification():
    with pytest.raises(ValueError):
        judge.qualification({"judge": "semantic-openrouter-luna-field-v2"})


def test_unqualified_bundle_cannot_construct_http(monkeypatch, packet):
    monkeypatch.setattr(
        judge.httpx, "Client", lambda **_: pytest.fail("HTTP before qualification")
    )
    with pytest.raises(ValueError):
        judge.review_bundle(
            {"judge": "semantic-openrouter-luna-field-v2"}, {}, "run", 1
        )
