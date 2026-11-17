"""Offline tests of qualified remote reviewing; HTTP is always a test double."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from venom_core.services.training_experiments import openrouter_semantic_judge as judge
from venom_core.services.training_experiments.profiles import digest, stable_hash


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


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))


@pytest.fixture
def full_audit(tmp_path, monkeypatch):
    """228 invented HTTP traces, never a real qualification or hidden material."""
    root = tmp_path / "audit"
    jobs, golds, decisions = {}, {}, {}
    for split, count in {**judge.PHASE1, "holdout": 24}.items():
        jobs[split], decisions[split] = {}, {}
        accepted, rejected, styles, semantics, gold_answers = [], {}, {}, {}, {}
        for i in range(count):
            ident = split + str(i)
            positive = i < 24 if split == "legacy" else i % 4 < 2
            case = {
                "id": split + "case" + str(i // 4),
                "messages": [],
                "criteria": [{"id": "fact", "description": "Fixture fact"}],
            }
            answer = {"id": ident, "text": "fixture-" + ident}
            body = judge._control_request(case, answer)
            raw = response(body, answer["text"], ident, positive)
            data = json.loads(raw["choices"][0]["message"]["content"])
            if split == "legacy" and 24 <= i < 30:
                data["polish_ok"] = False
            if split == "legacy" and 30 <= i < 36:
                data["natural_ok"] = False
            raw["choices"][0]["message"]["content"] = json.dumps(data)
            decision = judge.decode(raw, body, answer["text"])
            jobs[split][ident] = case, answer
            decisions[split][ident] = raw
            if positive:
                accepted.append(ident)
            else:
                rejected[ident] = {"critical": True, "failure": "fixture"}
            if split == "legacy" and (i < 12 or 24 <= i < 36):
                styles[ident] = {
                    "polish_ok": decision.polish_ok,
                    "natural_ok": decision.natural_ok,
                }
            if split == "legacy" and 24 <= i < 30:
                semantics[ident] = {"unsupported": "yes"}
            gold_answers[ident] = {
                "decision": {k: getattr(decision, k) for k in judge.DECISION_FIELDS}
            }
        golds[split] = (
            {
                "accepted": accepted,
                "rejected": rejected,
                "expected_style": styles,
                "expected_semantics": semantics,
            }
            if split == "legacy"
            else {"answers": gold_answers}
        )
    monkeypatch.setattr(
        judge, "_jobs", lambda _root, _manifest, split: (jobs[split], golds[split])
    )
    first = [
        {"split": split, "answer_id": ident, "repeat": 1}
        for split in judge.PHASE1
        for ident in jobs[split]
    ]
    order_path = root / "controls/phase1-order.json"
    _write(order_path, {"jobs": first})
    held = {}
    for name in ("panel.json", "gold.json"):
        path = root / "controls/holdout" / name
        _write(path, {"fixture": name})
        held[name] = digest(path)
    thresholds = {
        "legacy_positive": 24,
        "legacy_negative": 36,
        "legacy_style": 24,
        "legacy_semantics": 6,
        "development_full": 48,
        "extra_full": 32,
        "contrasts_full": 16,
        "holdout_full": 72,
        "holdout_stable_groups": 24,
    }
    manifest = {
        "control_version": "luna-controls-v3",
        "status": "frozen_before_any_inference",
        "thresholds": thresholds,
        "files": {"phase1-order.json": digest(order_path)},
        "holdout": {"files": held},
    }
    _write(root / "controls/frozen-manifest.json", manifest)
    manifest_sha = digest(root / "controls/frozen-manifest.json")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _write(
        root / "data-review.json",
        {
            "status": "passed",
            "reviewer": "invented CPU fixture",
            "controls_manifest_sha256": manifest_sha,
            "created_at": base.isoformat(),
        },
    )
    protocol = {
        "judge": judge.JUDGE,
        "request_contract": judge._contract(),
        "controls_manifest_sha256": manifest_sha,
        "implementation_sha256": judge.implementation_identity(),
        "data_review_sha256": digest(root / "data-review.json"),
        "initial_accounted_usd": "0.01",
        "initial_unknown_reserved_usd": "0.01",
        "budget_usd": "0.20",
        "max_seconds": 2000,
    }
    _write(root / "protocol.json", protocol)
    protocol_sha = digest(root / "protocol.json")
    order = first + [
        {"split": "holdout", "answer_id": ident, "repeat": repeat}
        for repeat in (1, 2, 3)
        for ident in jobs["holdout"]
    ]
    hashes = {}
    total = Decimal(0)
    for i, entry in enumerate(order, 1):
        case, answer = jobs[entry["split"]][entry["answer_id"]]
        body = judge._control_request(case, answer)
        raw = copy.deepcopy(decisions[entry["split"]][entry["answer_id"]])
        raw["id"] = "generation-" + str(i)
        row = {
            **entry,
            "index": i,
            "status": "completed",
            "call_id": "call-" + str(i),
            "protocol_sha256": protocol_sha,
            "request": body,
            "request_sha256": stable_hash(body),
            "response": raw,
            "response_sha256": stable_hash(raw),
            "decision": judge.decode(raw, body, answer["text"]).model_dump(),
            "cost_usd": judge.reported_cost(raw),
            "reserved_usd": str(judge.reserve(body)),
            "started_at": (base + timedelta(seconds=i * 2)).isoformat(),
            "finished_at": (base + timedelta(seconds=i * 2 + 1)).isoformat(),
        }
        path = root / "receipts" / f"{i:03d}.json"
        _write(path, row)
        hashes[path.name] = digest(path)
        total += Decimal(row["cost_usd"])
    _write(
        root / "phase1-result.json",
        {
            "status": "passed",
            "rows": 156,
            "metrics": {
                k: v for k, v in thresholds.items() if not k.startswith("holdout")
            },
            "receipt_hashes": {k: v for k, v in hashes.items() if int(k[:3]) <= 156},
            "finished_at": (base + timedelta(seconds=313)).isoformat(),
        },
    )
    result = {
        "status": "passed",
        "protocol_sha256": protocol_sha,
        "metrics": thresholds,
        "receipt_hashes": hashes,
        "phase1_result_sha256": digest(root / "phase1-result.json"),
        "actual_known_cost_usd": str(total),
        "unknown_reserved_usd": "0",
        "carried_unknown_reserved_usd": "0.01",
        "accounted_usd": str(total + Decimal("0.01")),
    }
    _write(root / "result.json", result)
    pin = judge.QualificationRemote(
        schema_version=1,
        judge=judge.JUDGE,
        audit_root=str(root),
        model=judge.MODEL,
        provider=judge.PROVIDER,
        endpoint=judge.ENDPOINT,
        protocol_sha256=protocol_sha,
        result_sha256=digest(root / "result.json"),
        controls_manifest_sha256=manifest_sha,
        prompt_sha256=judge._contract()["prompt_sha256"],
        request_contract_sha256=stable_hash(judge._contract()),
        implementation_sha256=judge.implementation_identity(),
    )
    return root, pin, result


def test_full_228_audit_replayed_offline(full_audit):
    _, pin, _ = full_audit
    calibration = {"judge": judge.JUDGE, "judge_qualification": pin.model_dump()}
    assert judge.qualification(calibration) == pin
    assert judge.scorer_protocol(calibration).startswith(judge.JUDGE + ":")


@pytest.mark.parametrize(
    "damage",
    ["status", "rows", "budget", "metrics", "raw", "generation", "time", "marker"],
)
def test_resealed_audit_cannot_hide_failure(full_audit, damage):
    root, pin, result = full_audit
    if damage == "status":
        result["status"] = "failed_qualification"
    elif damage == "rows":
        del result["receipt_hashes"]["001.json"]
    elif damage == "budget":
        result["accounted_usd"] = "0.3"
    elif damage == "metrics":
        result["metrics"] = {}
    elif damage == "marker":
        marker = json.loads((root / "phase1-result.json").read_text())
        marker["status"] = "failed"
        _write(root / "phase1-result.json", marker)
        result["phase1_result_sha256"] = digest(root / "phase1-result.json")
    else:
        row = json.loads((root / "receipts/002.json").read_text())
        if damage == "raw":
            row["response"]["provider"] = "Other"
        elif damage == "generation":
            row["response"]["id"] = "generation-1"
            row["response_sha256"] = stable_hash(row["response"])
        else:
            row["started_at"] = "2020-01-01T00:00:00+00:00"
        _write(root / "receipts/002.json", row)
        result["receipt_hashes"]["002.json"] = digest(root / "receipts/002.json")
    _write(root / "result.json", result)
    pin = pin.model_copy(update={"result_sha256": digest(root / "result.json")})
    with pytest.raises(ValueError):
        judge.verify_audit(pin)


def test_incomplete_phase1_never_reads_heldout(full_audit, monkeypatch):
    root, pin, result = full_audit
    (root / "receipts/001.json").unlink()
    original = type(root).open

    def guarded(path, *args, **kwargs):
        if "holdout" in path.parts:
            pytest.fail("held-out bytes opened before G1")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(type(root), "open", guarded)
    with pytest.raises((ValueError, FileNotFoundError)):
        judge.verify_audit(pin)


@pytest.fixture
def review_env(tmp_path, monkeypatch, packet):
    import httpx

    spec, case, answer = packet
    audit = tmp_path / "audit"
    _write(audit / "result.json", {"accounted_usd": "0.01"})
    pin = judge.QualificationRemote(
        schema_version=1,
        judge=judge.JUDGE,
        audit_root=str(audit),
        model=judge.MODEL,
        provider=judge.PROVIDER,
        endpoint=judge.ENDPOINT,
        protocol_sha256="0" * 64,
        result_sha256=digest(audit / "result.json"),
        controls_manifest_sha256="2" * 64,
        prompt_sha256="3" * 64,
        request_contract_sha256="4" * 64,
        implementation_sha256="5" * 64,
    )
    monkeypatch.setattr(judge, "qualification", lambda _cal: pin)
    monkeypatch.setattr(judge.runtime, "is_enabled", lambda: True)
    monkeypatch.setattr(judge.runtime, "cloud_allowed", lambda: True)
    monkeypatch.setattr(judge.runtime, "credential", lambda: "synthetic-test-key")
    monkeypatch.setattr(judge.SETTINGS, "OPENROUTER_DAILY_LIMIT_USD", 0.20)
    monkeypatch.setattr(judge.SETTINGS, "OPENROUTER_MESSAGE_LIMIT_USD", 0.01)
    calibration = {
        "judge": judge.JUDGE,
        "cases": {case["record_id"]: spec},
        "remote_review": {
            "ledger_root": str(tmp_path / "reviews"),
            "budget_usd": "0.20",
            "max_request_usd": "0.01",
        },
    }
    bundle = {"cases": [case], "answers": [{"case": case, "answers": {"A": answer}}]}
    state = {
        "calls": [],
        "status": 200,
        "nonjson": False,
        "raw_change": lambda value: value,
    }

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, json, timeout):
            assert url == judge.ENDPOINT and timeout > 0
            state["calls"].append(json)
            request = httpx.Request("POST", url)
            if state["nonjson"]:
                return httpx.Response(
                    state["status"], text="fixture HTML error", request=request
                )
            raw = response(json, ident="remote-" + str(len(state["calls"])))
            if state["status"] >= 400:
                raw = {"error": {"message": "synthetic failure"}}
            return httpx.Response(
                state["status"], json=state["raw_change"](raw), request=request
            )

    monkeypatch.setattr(judge.httpx, "Client", Client)
    return calibration, bundle, pin, state, tmp_path / "reviews"


def test_review_replay_and_exact_completed_reuse(review_env, packet):
    calibration, bundle, pin, state, root = review_env
    grades = judge.review_bundle(calibration, bundle, "run-1", 10)
    assert len(state["calls"]) == 1 and grades[0]["criteria"]["place"]
    assert "synthetic-test-key" not in (root / "ledger.json").read_text()
    judge.verify_review_receipt(pin, *packet, grades[0])
    assert judge.review_bundle(calibration, bundle, "run-1", 10) == grades
    assert len(state["calls"]) == 1
    damaged = copy.deepcopy(grades[0])
    damaged["criteria"]["place"] = False
    with pytest.raises(ValueError):
        judge.verify_review_receipt(pin, *packet, damaged)
    damaged = copy.deepcopy(grades[0])
    damaged["model_review_call"]["receipt_name"] = "../../outside.json"
    with pytest.raises(ValueError):
        judge.verify_review_receipt(pin, *packet, damaged)


@pytest.mark.parametrize("damage", ["accounted", "entry", "receipt", "orphan"])
def test_ledger_tampering_refuses_before_post(review_env, damage):
    calibration, bundle, _, state, root = review_env
    judge.review_bundle(calibration, bundle, "run-1", 10)
    ledger = json.loads((root / "ledger.json").read_text())
    if damage == "accounted":
        ledger["accounted_usd"] = "0"
    elif damage == "entry":
        ledger["receipts"] = {}
    elif damage == "receipt":
        name = next(iter(ledger["receipts"]))
        row = json.loads((root / "receipts" / name).read_text())
        row["cost_usd"] = "0"
        _write(root / "receipts" / name, row)
    else:
        _write(root / "receipts" / ("f" * 32 + ".json"), {})
    _write(root / "ledger.json", ledger)
    with pytest.raises(ValueError):
        judge.review_bundle(calibration, bundle, "run-2", 10)
    assert len(state["calls"]) == 1


@pytest.mark.parametrize(
    "status,nonjson",
    [(401, False), (403, False), (404, False), (404, True), (500, False)],
)
def test_failfast_preserves_failure_and_unknown_reservation(
    review_env, status, nonjson
):
    import httpx

    calibration, bundle, _, state, root = review_env
    state.update(status=status, nonjson=nonjson)
    with pytest.raises((ValueError, httpx.HTTPError)):
        judge.review_bundle(calibration, bundle, "run-1", 10)
    assert len(state["calls"]) == 1
    ledger = json.loads((root / "ledger.json").read_text())
    name = next(iter(ledger["receipts"]))
    row = json.loads((root / "receipts" / name).read_text())
    assert row["http_status"] == status and row["status"] == "failed"
    assert row["response"] and row["cost_usd"] is None
    assert Decimal(ledger["accounted_usd"]) == Decimal("0.01") + Decimal(
        row["reserved_usd"]
    )
    with pytest.raises(ValueError, match="attempt_already_started"):
        judge.review_bundle(calibration, bundle, "run-1", 10)
    assert len(state["calls"]) == 1


@pytest.mark.parametrize(
    "damage", ["length", "missing_cost", "wrong_provider", "duplicate_id", "overcharge"]
)
def test_partial_reply_or_overcharge_cannot_return_grades(review_env, damage):
    calibration, bundle, _, state, root = review_env
    if damage == "duplicate_id":
        judge.review_bundle(calibration, bundle, "run-0", 10)

    def change(raw):
        if damage == "length":
            raw["choices"][0]["finish_reason"] = "length"
        elif damage == "missing_cost":
            raw.pop("usage")
        elif damage == "wrong_provider":
            raw["provider"] = "Other"
        elif damage == "duplicate_id":
            raw["id"] = "remote-1"
        else:
            raw["usage"]["cost"] = 0.30
        return raw

    state["raw_change"] = change
    with pytest.raises(ValueError):
        judge.review_bundle(calibration, bundle, "run-1", 10)
    row = json.loads(next((root / "receipts").glob("*.json")).read_text())
    assert row["response"]


def test_budget_cancel_deadline_and_configuration(review_env):
    calibration, bundle, _, state, _ = review_env
    calibration["remote_review"]["budget_usd"] = "0.010001"
    with pytest.raises(ValueError, match="budget_exhausted"):
        judge.review_bundle(calibration, bundle, "budget", 10)
    assert not state["calls"]
    calibration["remote_review"]["budget_usd"] = "0.20"

    def cancel():
        raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        judge.review_bundle(calibration, bundle, "cancel", 10, check=cancel)
    assert not state["calls"]
    with pytest.raises(ValueError):
        judge.review_bundle(calibration, bundle, "nan", float("nan"))
    judge.preflight(calibration)
    state["status"] = 200


def test_current_qualification_rejects_changed_code(full_audit):
    _, pin, _ = full_audit
    with pytest.raises(ValueError):
        judge.verify_audit(pin.model_copy(update={"implementation_sha256": "0" * 64}))
