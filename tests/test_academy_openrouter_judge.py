"""Offline tests of qualified remote reviewing; HTTP is always a test double."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from venom_core.services.training_experiments import openrouter_semantic_judge as judge
from venom_core.services.training_experiments import semantic_openrouter_audit as audit
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
    assert body["messages"][0]["content"] == judge.PROMPT
    assert judge._contract()["prompt_sha256"] == (
        "03670ddc9bcb365dfc9e73c359dc8335d0d53261072e253c3f6517eacc70ad4d"
    )
    assert body["provider"]["only"] == ["azure"]
    assert "zdr" not in body["provider"]
    assert "temperature" not in body
    assert "max_tokens" not in body
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
        "rate_limit": audit._RATE_LIMIT_POLICY,
        "automatic_retry": "http_429_only",
        "request_timeout_seconds": audit._REQUEST_TIMEOUT_SECONDS,
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
            "started_at": (base + timedelta(seconds=i * 3)).isoformat(),
            "finished_at": (base + timedelta(seconds=i * 3 + 1)).isoformat(),
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
            "finished_at": (base + timedelta(seconds=469)).isoformat(),
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
            assert kwargs["trust_env"] is False
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, json, timeout):
            assert url == judge.ENDPOINT
            assert timeout > 0
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
    assert len(state["calls"]) == 1
    assert grades[0]["criteria"]["place"]
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
    assert row["http_status"] == status
    assert row["status"] == "failed"
    assert row["response"]
    assert row["cost_usd"] is None
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
    damaged = pin.model_copy(update={"implementation_sha256": "0" * 64})
    with pytest.raises(ValueError):
        judge.verify_audit(damaged)


@pytest.mark.parametrize(
    "damage", ["choice-none", "choice-list", "message-none", "message-list"]
)
def test_malformed_provider_objects_fail_without_poisoning_ledger(review_env, damage):
    calibration, bundle, _, state, root = review_env

    def malformed(raw):
        if damage.startswith("choice"):
            raw["choices"] = [None if damage.endswith("none") else []]
        else:
            raw["choices"][0]["message"] = None if damage.endswith("none") else []
        return raw

    state["raw_change"] = malformed
    with pytest.raises(ValueError):
        judge.review_bundle(calibration, bundle, "invalid-reply", 10)
    row = json.loads(next((root / "receipts").glob("*.json")).read_text())
    assert row["status"] == "failed"
    assert row["cost_usd"] is not None
    state["raw_change"] = lambda raw: raw
    assert judge.review_bundle(calibration, bundle, "fresh-plan", 10)[0]["criteria"][
        "place"
    ]
    assert len(state["calls"]) == 2


def test_failed_duplicate_keeps_cost_and_allows_fresh_generation(review_env):
    calibration, bundle, _, state, root = review_env
    judge.review_bundle(calibration, bundle, "first", 10)

    def duplicate(raw):
        raw["id"] = "remote-1"
        return raw

    state["raw_change"] = duplicate
    with pytest.raises(ValueError):
        judge.review_bundle(calibration, bundle, "duplicate", 10)
    state["raw_change"] = lambda raw: raw
    grades = judge.review_bundle(calibration, bundle, "fresh", 10)
    assert grades[0]["criteria"]["place"]
    assert len(state["calls"]) == 3
    ledger = json.loads((root / "ledger.json").read_text())
    assert Decimal(ledger["accounted_usd"]) == Decimal("0.01003")
    assert len(ledger["receipts"]) == 3
    state["raw_change"] = duplicate
    with pytest.raises(ValueError):
        judge.review_bundle(calibration, bundle, "duplicate-again", 10)
    assert len(state["calls"]) == 4


@pytest.mark.parametrize("when", ["initial-ledger", "final-ledger", "final-cleanup"])
def test_transaction_recovers_interrupted_pair_without_repeating_post(
    review_env, monkeypatch, when
):
    calibration, bundle, pin, state, root = review_env
    original = judge.atomic_json
    ledger_writes = 0
    target = 1 if when == "initial-ledger" else 2
    failed = False

    def interrupted(path, value):
        nonlocal ledger_writes, failed
        if path == root / "ledger.json":
            ledger_writes += 1
            if when != "final-cleanup" and ledger_writes == target:
                failed = True
                raise OSError("simulated crash between receipt and ledger")
        return original(path, value)

    if when != "final-cleanup":
        monkeypatch.setattr(judge, "atomic_json", interrupted)
    else:
        unlink = type(root).unlink
        cleanup_calls = 0

        def cleanup(path, *args, **kwargs):
            nonlocal cleanup_calls, failed
            if path == root / ".pending-transaction.json":
                cleanup_calls += 1
                if cleanup_calls == 2:
                    failed = True
                    raise OSError("simulated crash after ledger commit")
            return unlink(path, *args, **kwargs)

        monkeypatch.setattr(type(root), "unlink", cleanup)
    with pytest.raises(OSError, match="simulated crash"):
        judge.review_bundle(calibration, bundle, "crashed-plan", 10)
    assert failed
    sent = 0 if when == "initial-ledger" else 1
    assert len(state["calls"]) == sent
    assert (root / ".pending-transaction.json").exists()
    monkeypatch.setattr(judge, "atomic_json", original)
    recovered, _ = judge._ledger_snapshot(root, pin)
    assert len(recovered["receipts"]) == 1
    row = json.loads(next((root / "receipts").glob("*.json")).read_text())
    charge = row["reserved_usd"] if sent == 0 else row["cost_usd"]
    assert Decimal(recovered["accounted_usd"]) == Decimal("0.01") + Decimal(charge)
    assert not (root / ".pending-transaction.json").exists()
    with pytest.raises(ValueError, match="attempt_already_started"):
        judge.review_bundle(calibration, bundle, "crashed-plan", 10)
    assert len(state["calls"]) == sent
    assert judge.review_bundle(calibration, bundle, "independent-plan", 10)[0][
        "criteria"
    ]["place"]
    assert len(state["calls"]) == sent + 1


@pytest.mark.parametrize(
    "relation, observed, extra_content, valid",
    [
        ("supported", "Opiekunka: Daria", "", False),
        ("contradicted", "Opiekunka: Daria", "", False),
        ("omitted", "Opiekunka: Daria", "", False),
        ("supported", "brak w odpowiedzi", "", False),
        ("omitted", "brak w odpowiedzi", "", True),
        ("omitted", "„brak w odpowiedzi”", "", False),
        ("omitted", '"brak w odpowiedzi"', "", False),
        ("omitted", " brak w odpowiedzi ", "", False),
        ("omitted", "„brak w odpowiedzi”", "Notatka: brak w odpowiedzi.", True),
        ("supported", "brak w odpowiedzi", "Notatka: brak w odpowiedzi.", True),
        ("contradicted", "„brak w odpowiedzi”", "Notatka: brak w odpowiedzi.", True),
        ("supported", "„Pawilon: F”", "", True),
        ("omitted", "„Pawilon: F”", "", True),
        ("supported", '"', 'Symbol: "', True),
        ("supported", '""', 'Symbole: ""', True),
        ("supported", '""', 'Symbol: "', False),
        ("supported", '" "', "", False),
    ],
)
def test_observed_requires_candidate_text_or_omission(
    packet, relation, observed, extra_content, valid
):
    spec, case, answer = packet
    candidate = "Pawilon: F\nPoczątek: 8:35"
    if extra_content:
        candidate += f"\n{extra_content}"
    case["messages"][0]["content"] = "Opiekunka: Daria. Pawilon: F. Początek: 8:35."
    case["criteria"][0]["description"] = "Opiekunka to Daria."
    answer["text"] = candidate
    body = judge.request_payload(spec, case, answer)
    raw = response(body, candidate=candidate)
    message = raw["choices"][0]["message"]
    data = json.loads(message["content"])
    data["checks"]["place"].update(observed=observed, relation=relation)
    message["content"] = json.dumps(data)
    if valid:
        assert judge.decode(raw, body, candidate).atoms == {"place": relation}
    else:
        with pytest.raises(ValueError, match=judge.ERROR):
            judge.decode(raw, body, candidate)


def _audit_with_first_429(
    full_audit,
    *,
    index=1,
    attempts=((8, "7"),),
    raw=None,
    limit=20_000,
    policy=None,
    budget="0.20",
    phase1_marker_delay=0.5,
    request_timeout=audit._REQUEST_TIMEOUT_SECONDS,
):
    root, pin, result = full_audit
    protocol_path = root / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    protocol["max_seconds"] = limit
    protocol["budget_usd"] = budget
    protocol["request_timeout_seconds"] = request_timeout
    if policy is not None:
        protocol["rate_limit"] = policy
    _write(protocol_path, protocol)
    protocol_sha = digest(protocol_path)
    result["protocol_sha256"] = protocol_sha
    for name in result["receipt_hashes"]:
        path = root / "receipts" / name
        row = json.loads(path.read_text())
        row["protocol_sha256"] = protocol_sha
        offset = timedelta(seconds=77 * row["index"])
        for field in ("started_at", "finished_at"):
            row[field] = (judge._time(row[field]) + offset).isoformat()
        if row["index"] == index:
            retries = []
            for retry_index, (start_before, header) in enumerate(attempts):
                started = judge._time(row["started_at"]) - timedelta(
                    seconds=start_before
                )
                retries.append(
                    {
                        **row,
                        "status": "failed",
                        "http_status": 429,
                        "call_id": f"initial-429-{retry_index}",
                        "retry_after": header,
                        "response": raw,
                        "response_sha256": stable_hash(raw),
                        "cost_usd": None,
                        "started_at": started.isoformat(),
                        "finished_at": (
                            started + timedelta(milliseconds=100)
                        ).isoformat(),
                    }
                )
            row["rate_limit_attempts"] = retries
            reserved = Decimal(row["reserved_usd"]) * len(retries)
            result["unknown_reserved_usd"] = str(reserved)
            result["accounted_usd"] = str(Decimal(result["accounted_usd"]) + reserved)
        _write(path, row)
        result["receipt_hashes"][name] = digest(path)
    marker_path = root / "phase1-result.json"
    marker = json.loads(marker_path.read_text())
    marker["receipt_hashes"] = {
        name: sha
        for name, sha in result["receipt_hashes"].items()
        if int(name[:3]) <= 156
    }
    # Distinguish the phase boundary from the previous completed request.
    marker["finished_at"] = (
        judge._time(marker["finished_at"])
        + timedelta(seconds=156 * 77 + phase1_marker_delay)
    ).isoformat()
    _write(marker_path, marker)
    result["phase1_result_sha256"] = digest(marker_path)
    result_path = root / "result.json"
    _write(result_path, result)
    return pin.model_copy(
        update={
            "protocol_sha256": protocol_sha,
            "result_sha256": digest(result_path),
        }
    )


@pytest.mark.parametrize("raw", [["rate limited"], "too many requests", None])
def test_full_audit_replays_non_object_429_without_reported_cost(full_audit, raw):
    judge.verify_audit(_audit_with_first_429(full_audit, raw=raw))


@pytest.mark.parametrize(
    "attempt",
    [
        {"limit": 18165},
        {"attempts": ((81, "7"),)},
        {"index": 157, "attempts": ((75, "7"),), "phase1_marker_delay": 10},
    ],
    ids=["elapsed-before-success", "before-data-review", "before-phase1-marker"],
)
def test_full_audit_rejects_429_outside_time_guards(full_audit, attempt):
    pin = _audit_with_first_429(full_audit, raw={"error": "retry"}, **attempt)
    with pytest.raises(ValueError, match=judge.ERROR):
        judge.verify_audit(pin)


def test_completed_call_still_requires_response_object(packet):
    body = judge.request_payload(*packet)
    raw = ["unexpected body"]
    row = {
        "status": "completed",
        "protocol_sha256": "protocol",
        "request": body,
        "request_sha256": stable_hash(body),
        "response": raw,
        "response_sha256": stable_hash(raw),
    }
    with pytest.raises(ValueError, match=judge.ERROR):
        judge._verify_call(row, body, "Hala A", "protocol")


@pytest.mark.parametrize(
    "attempts, valid",
    [
        (((8, "7"),), True),
        (((7, "7"),), False),
        (((6, "invalid"),), True),
        (((5, ""),), False),
        (((19, "7"), (11, "")), True),
        (((17, "7"), (11, "")), False),
        (((19, "7"), (10, "")), False),
        (((62, "61"),), False),
        (((8, "Thu, 01 Jan 2026 00:01:19 GMT"),), True),
        (((8, "Thu, 01 Jan 2026 00:01:21 GMT"),), False),
    ],
    ids=[
        "retry-after-wait",
        "retry-after-too-soon",
        "malformed-header-fallback",
        "default-backoff-too-soon",
        "both-waits",
        "earlier-429-too-soon",
        "successful-attempt-too-soon",
        "retry-after-exceeds-cap",
        "http-date-wait",
        "http-date-too-soon",
    ],
)
def test_full_audit_enforces_frozen_retry_waits(full_audit, attempts, valid):
    pin = _audit_with_first_429(full_audit, attempts=attempts)
    if valid:
        judge.verify_audit(pin)
    else:
        with pytest.raises(ValueError, match=judge.ERROR):
            judge.verify_audit(pin)


def test_full_audit_rejects_policy_with_third_retry(full_audit):
    policy = {**audit._RATE_LIMIT_POLICY, "backoff_seconds": [5, 10, 15]}
    pin = _audit_with_first_429(
        full_audit, attempts=((33, ""), (27, ""), (16, "")), policy=policy
    )
    with pytest.raises(ValueError, match=judge.ERROR):
        judge.verify_audit(pin)


def _reseal_receipt(root, pin, result, index, change):
    name = f"{index:03d}.json"
    path = root / "receipts" / name
    row = json.loads(path.read_text())
    change(row)
    _write(path, row)
    result["receipt_hashes"][name] = digest(path)
    if index <= 156:
        marker_path = root / "phase1-result.json"
        marker = json.loads(marker_path.read_text())
        marker["receipt_hashes"][name] = digest(path)
        _write(marker_path, marker)
        result["phase1_result_sha256"] = digest(marker_path)
    _write(root / "result.json", result)
    return pin.model_copy(update={"result_sha256": digest(root / "result.json")})


@pytest.mark.parametrize("damage", ["status", "request", "cost", "budget"])
def test_bad_phase1_retry_never_opens_holdout(full_audit, monkeypatch, damage):
    root, _, result = full_audit
    budget = "0.01156" if damage == "budget" else "0.20"
    pin = _audit_with_first_429(full_audit, budget=budget)

    def change(row):
        attempt = row["rate_limit_attempts"][0]
        if damage == "status":
            attempt["http_status"] = 503
        elif damage == "request":
            attempt["request"]["provider"]["allow_fallbacks"] = 0
        else:
            attempt["cost_usd"] = "0.00001"

    if damage != "budget":
        pin = _reseal_receipt(root, pin, result, 1, change)

    original = type(root).open

    def guarded(path, *args, **kwargs):
        if "holdout" in path.parts:
            pytest.fail("held-out bytes opened after invalid phase 1 retry")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(type(root), "open", guarded)
    with pytest.raises(ValueError, match=judge.ERROR):
        judge.verify_audit(pin)


def test_completed_request_uses_canonical_body_hash(full_audit):
    root, pin, result = full_audit

    def change(row):
        row["request"]["provider"]["allow_fallbacks"] = 0

    pin = _reseal_receipt(root, pin, result, 1, change)
    with pytest.raises(ValueError, match=judge.ERROR):
        judge.verify_audit(pin)


@pytest.mark.parametrize("index", [2, 157])
def test_audit_rejects_case_started_below_minimum_interval(full_audit, index):
    root, pin, result = full_audit
    previous = json.loads((root / "receipts" / f"{index - 1:03d}.json").read_text())

    def change(row):
        early = judge._time(previous["finished_at"]) + timedelta(seconds=1)
        row["started_at"] = early.isoformat()

    pin = _reseal_receipt(root, pin, result, index, change)
    with pytest.raises(ValueError, match=judge.ERROR):
        judge.verify_audit(pin)


@pytest.mark.parametrize("index", [2, 157])
def test_audit_rejects_first_429_below_minimum_interval(full_audit, index):
    pin = _audit_with_first_429(full_audit, index=index, attempts=((78, "7"),))
    with pytest.raises(ValueError, match=judge.ERROR):
        judge.verify_audit(pin)


def test_phase1_marker_does_not_restart_request_interval(full_audit):
    root, pin, result = full_audit
    marker_path = root / "phase1-result.json"
    marker = json.loads(marker_path.read_text())
    marker["finished_at"] = (
        judge._time(marker["finished_at"]) + timedelta(seconds=1.5)
    ).isoformat()
    _write(marker_path, marker)
    result["phase1_result_sha256"] = digest(marker_path)
    _write(root / "result.json", result)
    pin = pin.model_copy(update={"result_sha256": digest(root / "result.json")})
    judge.verify_audit(pin)


def test_full_audit_rejects_changed_request_timeout(full_audit):
    pin = _audit_with_first_429(full_audit, request_timeout=120)
    with pytest.raises(ValueError, match=judge.ERROR):
        judge.verify_audit(pin)
