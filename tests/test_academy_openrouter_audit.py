"""The operator auditor is exercised only with invented fixtures and fake HTTP."""

from __future__ import annotations

import copy
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from tests.test_academy_openrouter_judge import full_audit as audit_fixture
from venom_core.services.training_experiments import openrouter_semantic_judge as judge
from venom_core.services.training_experiments import semantic_openrouter_audit as audit
from venom_core.services.training_experiments.profiles import digest, stable_hash

full_audit = audit_fixture


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))


@pytest.fixture
def ready(full_audit, tmp_path, monkeypatch):
    source_root, _, _ = full_audit
    source = source_root / "controls"
    manifest = json.loads((source / "frozen-manifest.json").read_text())
    for name in audit.CONTROL_FILES - {"phase1-order.json"}:
        write(source / name, {"invented_cpu_fixture": name})
        manifest["files"][name] = digest(source / name)
    manifest["holdout"]["source_directory"] = str(source / "holdout")
    write(source / "frozen-manifest.json", manifest)
    review = json.loads((source_root / "data-review.json").read_text())
    review["controls_manifest_sha256"] = digest(source / "frozen-manifest.json")
    write(source_root / "data-review.json", review)
    root = tmp_path / "operator-attempt"
    audit.prepare(
        source,
        source_root / "data-review.json",
        root,
        holdout_max_request_usd="0.002",
        controls_sha256=digest(source / "frozen-manifest.json"),
        data_review_sha256=digest(source_root / "data-review.json"),
        budget_usd="0.80",
        max_seconds=7200,
        initial_accounted_usd="0.01",
        initial_unknown_reserved_usd="0.01",
    )
    monkeypatch.setattr(audit.runtime, "is_enabled", lambda: True)
    monkeypatch.setattr(audit.runtime, "cloud_allowed", lambda: True)
    monkeypatch.setattr(audit.runtime, "credential", lambda: "invented-test-credential")
    monkeypatch.setattr(audit.SETTINGS, "OPENROUTER_DAILY_LIMIT_USD", 0.80)
    origin = judge._time(audit._utc())
    elapsed = 0.0

    def sleep(seconds):
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr(audit, "sleep", sleep)
    monkeypatch.setattr(
        audit,
        "time",
        SimpleNamespace(
            monotonic=lambda: elapsed, time=lambda: origin.timestamp() + elapsed
        ),
    )
    monkeypatch.setattr(
        audit, "_utc", lambda: (origin + timedelta(seconds=elapsed)).isoformat()
    )
    monkeypatch.setattr(audit.SETTINGS, "OPENROUTER_MESSAGE_LIMIT_USD", 0.01)
    responses = {}
    for path in (source_root / "receipts").glob("*.json"):
        row = json.loads(path.read_text())
        responses[row["request_sha256"]] = row["response"]

    class FakeClient:
        calls = 0
        factory_calls = 0
        mode = "pass"
        fail_at = 1

        def __init__(self, **kwargs):
            type(self).factory_calls += 1
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, url, *, json: dict, **_kwargs):
            type(self).calls += 1
            ledger = __import__("json").loads((root / "ledger.json").read_text())
            assert ledger["pending_call_id"]
            assert audit.judge._money(ledger["accounted_usd"]) >= judge.reserve(json)
            assert url == judge.ENDPOINT
            body = copy.deepcopy(responses[stable_hash(json)])
            body["id"] = "new-fake-generation-" + str(self.calls)
            at = self.calls == self.fail_at
            if self.mode == "duplicate-generation":
                body["id"] = "repeated-generation"
            if at and self.mode == "non-object":
                return httpx.Response(200, json=[], request=httpx.Request("POST", url))
            if at and self.mode == "404-text":
                return httpx.Response(
                    404, text="fixture not found", request=httpx.Request("POST", url)
                )
            if at and self.mode == "bad-qualification":
                data = __import__("json").loads(
                    body["choices"][0]["message"]["content"]
                )
                data["checks"] = {
                    key: {**value, "relation": "contradicted"}
                    for key, value in data["checks"].items()
                }
                body["choices"][0]["message"]["content"] = __import__("json").dumps(
                    data
                )
            if at and self.mode == "missing-cost":
                body.pop("usage")
            if at and self.mode == "wrong-provider":
                body["provider"] = "other"
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    return root, source_root, FakeClient


def test_prepare_never_opens_holdout_and_full_fake_audit_replays(ready):
    root, _, client = ready
    assert not (root / "controls/holdout").exists()
    assert not (root / "qualification.json").exists()
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "passed"
    assert client.calls == 228
    assert Decimal(result["accounted_usd"]) == Decimal("0.01228")
    assert result["carried_unknown_reserved_usd"] == "0.01"
    pin = judge.QualificationRemote.model_validate(
        json.loads((root / "qualification.json").read_text())
    )
    judge.verify_audit(pin)
    assert len(result["receipt_hashes"]) == 228
    assert result["deviations"] == {
        "planned": 228,
        "attempted": 228,
        "by_case": [],
        "not_run_reason": None,
        "not_run": [],
        "holdout_unscheduled": 0,
    }
    assert "invented-test-credential" not in "".join(
        p.read_text() for p in root.rglob("*.json")
    )


def test_g1_failure_cannot_open_missing_holdout(ready):
    root, source, client = ready
    client.mode = "bad-qualification"
    for p in (source / "controls/holdout").glob("*"):
        p.unlink()
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "failed_qualification"
    assert client.calls == 156
    assert not (root / "controls/holdout").exists()
    assert not (root / "qualification.json").exists()


def test_phase1_collects_rejections_through_156_and_never_opens_holdout(
    ready, monkeypatch
):
    root, _, client = ready
    monkeypatch.setattr(
        audit,
        "_stage_holdout",
        lambda *_: pytest.fail("rejected phase 1 opened holdout"),
    )

    class RejectingClient(client):
        def post(self, url, **kwargs):
            response = super().post(url, **kwargs)
            index = type(self).calls
            if index not in (98, 134, 156):
                return response
            body = response.json()
            message = body["choices"][0]["message"]
            if index == 98:
                message["content"] = "invalid decision"
            elif index == 156:
                decision = json.loads(message["content"])
                decision.update(polish_ok=False, natural_ok=False)
                message["content"] = json.dumps(decision)
            else:
                decision = json.loads(message["content"])
                candidate = json.loads(kwargs["json"]["messages"][1]["content"])[
                    "candidate"
                ]
                decision["checks"] = {
                    key: {"relation": "unclear", "observed": candidate}
                    for key in decision["checks"]
                }
                decision["additional_claims"] = []
                message["content"] = json.dumps(decision)
            return httpx.Response(200, json=body, request=response.request)

    result = audit.run(root, execute=True, client_factory=RejectingClient)

    assert result["status"] == "failed_qualification"
    assert result["rows"] == RejectingClient.calls == 156
    assert result["rate_limit_retries"] == 0
    assert Decimal(result["actual_known_cost_usd"]) == Decimal("0.00156")
    assert Decimal(result["unknown_reserved_usd"]) == 0
    assert result["holdout_opened"] is False
    assert not (root / "controls/holdout").exists()
    assert not (root / "qualification.json").exists()
    phase1 = json.loads((root / "phase1-result.json").read_text())
    assert phase1["status"] == "failed_qualification"
    assert result["phase1_rejections"] == phase1["rejected_decisions"]
    assert [
        (row["index"], row["error_type"]) for row in phase1["rejected_decisions"]
    ] == [(98, "decoder_invalid"), (134, "uncertain_decision")]
    assert result["metrics"]["development_full"] == 47
    assert result["metrics"]["extra_full"] == 31
    assert json.loads((root / "receipts/156.json").read_text())["status"] == "completed"
    deviations = result["deviations"]
    assert deviations["planned"] == deviations["attempted"] == 156
    assert deviations["holdout_unscheduled"] == 72
    assert deviations["not_run"] == []
    assert deviations["not_run_reason"] is None
    early, mid, last = deviations["by_case"]
    assert [early["index"], mid["index"], last["index"]] == [98, 134, 156]
    assert early["issues"][0]["error_type"] == "decoder_invalid"
    assert mid["issues"][0]["error_type"] == "uncertain_decision"
    assert {item["field"] for item in mid["issues"]} >= {"status", "atoms.fact"}
    assert last["issues"] == [
        {"field": "polish_ok", "expected": True, "actual": False},
        {"field": "natural_ok", "expected": True, "actual": False},
    ]
    assert json.loads((root / "result.json").read_text())["deviations"] == deviations


def test_open_holdout_collects_quality_deviations_through_228(ready):
    root, _, client = ready

    class HoldoutClient(client):
        def post(self, url, **kwargs):
            response = super().post(url, **kwargs)
            index = type(self).calls
            if index not in {157, 228}:
                return response
            body = response.json()
            message = body["choices"][0]["message"]
            if index == 157:
                message["content"] = "invalid holdout decision"
            else:
                decision = json.loads(message["content"])
                decision["checks"]["fact"]["relation"] = "supported"
                message["content"] = json.dumps(decision)
            return httpx.Response(200, json=body, request=response.request)

    result = audit.run(root, execute=True, client_factory=HoldoutClient)
    assert result["status"] == "failed_qualification"
    assert result["holdout_opened"]
    assert result["rows"] == HoldoutClient.calls == 228
    assert result["rate_limit_retries"] == 0
    assert result["metrics"]["holdout_full"] == 70
    assert result["metrics"]["holdout_stable_groups"] == 22
    assert not (root / "qualification.json").exists()
    deviations = result["deviations"]
    assert deviations["not_run"] == []
    assert deviations["holdout_unscheduled"] == 0
    first, last = deviations["by_case"]
    assert (first["index"], first["repeat"]) == (157, 1)
    assert first["issues"][0]["error_type"] == "decoder_invalid"
    assert (last["index"], last["repeat"]) == (228, 3)
    assert {
        item["field"]: (item["expected"], item["actual"]) for item in last["issues"]
    } == {
        "atoms.fact": ("contradicted", "supported"),
        "unsupported": ("yes", "no"),
    }


def test_missing_legacy_decision_never_counts_as_correct_negative(ready):
    root, _, client = ready
    protocol, manifest, _ = audit._static(root)
    _, gold = judge._jobs(root, manifest, "legacy")
    rejected = set(gold["rejected"])
    order = judge._audit_order(root, manifest, phase1=True)
    target = next(
        i
        for i, row in enumerate(order, 1)
        if row["split"] == "legacy" and row["answer_id"] in rejected
    )
    assert protocol["phase1_decision_errors"] == "collect_and_block_holdout"

    class DroppingClient(client):
        def post(self, url, **kwargs):
            response = super().post(url, **kwargs)
            if type(self).calls != target:
                return response
            body = response.json()
            body["choices"][0]["message"]["content"] = "invalid decision"
            return httpx.Response(200, json=body, request=response.request)

    result = audit.run(root, execute=True, client_factory=DroppingClient)
    assert result["status"] == "failed_qualification"
    assert result["rows"] == 156
    assert result["metrics"]["legacy_negative"] == 35
    assert result["phase1_rejections"][0]["index"] == target
    assert not result["holdout_opened"]


@pytest.mark.parametrize("fail_at", [1, 2])
def test_system_error_stops_without_retry_and_retains_unknown_cost(ready, fail_at):
    root, _, client = ready
    client.mode, client.fail_at = "404-text", fail_at
    result = audit.run(root, execute=True, client_factory=client)
    assert client.calls == fail_at
    assert result["status"] == "transport_incomplete"
    assert audit.judge._money(result["unknown_reserved_usd"]) > 0
    assert result["metrics"] is None
    deviations = result["deviations"]
    assert deviations["by_case"][0]["index"] == fail_at
    assert deviations["by_case"][0]["issues"][0]["http_status"] == 404
    assert deviations["not_run_reason"] == "transport_incomplete"
    assert [entry["index"] for entry in deviations["not_run"]] == list(
        range(fail_at + 1, 157)
    )
    assert not (root / "controls/holdout").exists()
    with pytest.raises(ValueError, match="single_attempt"):
        audit.run(root, execute=True, client_factory=client)


@pytest.mark.parametrize("mode", ["missing-cost", "wrong-provider"])
def test_incomplete_or_wrong_remote_identity_stops(ready, mode):
    root, _, client = ready
    client.mode = mode
    result = audit.run(root, execute=True, client_factory=client)
    assert client.calls == 1
    assert result["status"] == "transport_incomplete"
    assert not (root / "qualification.json").exists()


def test_execute_gate_precedes_provider_and_mutation(ready):
    root, _, client = ready
    with pytest.raises(ValueError, match="operator_execute"):
        audit.run(root, client_factory=client)
    assert client.factory_calls == 0
    assert not (root / "started.json").exists()


def test_disabled_provider_and_changed_frozen_contract_precede_http(ready, monkeypatch):
    root, _, client = ready
    monkeypatch.setattr(audit.runtime, "is_enabled", lambda: False)
    with pytest.raises(ValueError, match="provider_unavailable"):
        audit.run(root, execute=True, client_factory=client)
    assert client.factory_calls == 0
    monkeypatch.setattr(audit.runtime, "is_enabled", lambda: True)
    write(root / "protocol.json", {"tampered": True})
    with pytest.raises((ValueError, KeyError)):
        audit.run(root, execute=True, client_factory=client)
    assert client.factory_calls == 0


def test_budget_stop_cannot_construct_http(ready, monkeypatch):
    root, _, client = ready
    monkeypatch.setattr(audit.SETTINGS, "OPENROUTER_DAILY_LIMIT_USD", 0.01005)
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "budget_exhausted"
    assert client.factory_calls == 0
    assert result["rows"] == 0
    assert result["accounted_usd"] == "0.01"


def test_deadline_stop_cannot_construct_http(ready, monkeypatch):
    root, _, client = ready
    ticks = iter([0, 9000, 9001])
    monkeypatch.setattr(audit.time, "monotonic", lambda: next(ticks, 9001))
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "deadline_exceeded"
    assert client.factory_calls == 0
    assert not (root / "controls/holdout").exists()


def test_preparation_refuses_unreviewed_or_changed_data(ready, tmp_path):
    _, source, _ = ready
    review = source / "data-review.json"
    value = json.loads(review.read_text())
    value["status"] = "not-reviewed"
    write(review, value)
    with pytest.raises(ValueError, match="data_review_required"):
        audit.prepare(
            source / "controls",
            review,
            tmp_path / "bad-review",
            holdout_max_request_usd="0.002",
            controls_sha256=digest(source / "controls/frozen-manifest.json"),
            data_review_sha256=digest(review),
            budget_usd="0.10",
            max_seconds=7200,
        )
    assert not (tmp_path / "bad-review").exists()


@pytest.mark.parametrize(
    "budget,initial,unknown,seconds",
    [
        ("NaN", "0", "0", 2000),
        ("0", "0", "0", 2000),
        ("0.10", "0.20", "0", 2000),
        ("0.10", "0", "0.01", 2000),
        ("0.10", "0", "0", float("inf")),
    ],
)
def test_invalid_budget_or_deadline_cannot_prepare(
    ready, tmp_path, budget, initial, unknown, seconds
):
    _, source, _ = ready
    with pytest.raises(ValueError):
        audit.prepare(
            source / "controls",
            source / "data-review.json",
            tmp_path / "bad-budget",
            holdout_max_request_usd="0.002",
            controls_sha256=digest(source / "controls/frozen-manifest.json"),
            data_review_sha256=digest(source / "data-review.json"),
            budget_usd=budget,
            initial_accounted_usd=initial,
            initial_unknown_reserved_usd=unknown,
            max_seconds=seconds,
        )


def test_cli_help_and_missing_execute_are_offline(ready, monkeypatch):
    from scripts.academy import qualify_openrouter_judge as cli

    root, _, _ = ready
    monkeypatch.setattr("sys.argv", ["qualify", "--help"])
    with pytest.raises(SystemExit) as caught:
        cli.main()
    assert caught.value.code == 0
    monkeypatch.setattr("sys.argv", ["qualify", "run", "--audit-root", str(root)])
    with pytest.raises(ValueError, match="operator_execute"):
        cli.main()
    assert not (root / "started.json").exists()


def test_duplicate_generation_fails_before_third_request(ready):
    root, _, client = ready
    client.mode = "duplicate-generation"
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "transport_incomplete"
    assert client.calls == 2
    assert not (root / "qualification.json").exists()


def test_non_object_response_fails_closed(ready):
    root, _, client = ready
    client.mode = "non-object"
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "transport_incomplete"
    assert client.calls == 1
    assert audit.judge._money(result["unknown_reserved_usd"]) > 0


@pytest.mark.parametrize(
    "http_status, value, status",
    [
        (200, "NaN", "transport_incomplete"),
        (200, "Infinity", "transport_incomplete"),
        (429, "-Infinity", "provider_rate_limited"),
        (429, "1e999", "provider_rate_limited"),
    ],
)
def test_nonfinite_response_keeps_receipt_and_reservation(
    ready, http_status, value, status
):
    root, _, client = ready
    payload = '{"diagnostic":' + value + "}"

    class NonfiniteResponse(client):
        def post(self, url, **_kwargs):
            return httpx.Response(
                http_status,
                headers={"Retry-After": "300"},
                content=payload,
                request=httpx.Request("POST", url),
            )

    result = audit.run(root, execute=True, client_factory=NonfiniteResponse)

    receipt = json.loads((root / "receipts/001.json").read_text())
    ledger = json.loads((root / "ledger.json").read_text())
    assert result["status"] == status
    assert result["rows"] == 1
    assert receipt["response"] == {"non_json_body": payload}
    assert receipt["response_sha256"] == stable_hash(receipt["response"])
    assert Decimal(result["unknown_reserved_usd"]) == Decimal(receipt["reserved_usd"])
    assert ledger["pending_call_id"] is None


def test_cli_prepare_is_offline_and_binds_explicit_hashes(ready, tmp_path, monkeypatch):
    from scripts.academy import qualify_openrouter_judge as cli

    root, source, _ = ready
    target = tmp_path / "cli-prepared"
    monkeypatch.setattr(
        audit.runtime, "credential", lambda: pytest.fail("provider during prepare")
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "qualify",
            "prepare",
            "--controls",
            str(source / "controls"),
            "--data-review",
            str(source / "data-review.json"),
            "--output",
            str(target),
            "--controls-manifest-sha256",
            digest(source / "controls/frozen-manifest.json"),
            "--data-review-sha256",
            digest(source / "data-review.json"),
            "--budget-usd",
            "0.10",
            "--max-seconds",
            "2000",
            "--holdout-max-request-usd",
            "0.002",
        ],
    )
    cli.main()
    assert (target / "frozen.json").is_file()
    assert not (target / "started.json").exists()
    assert not (target / "controls/holdout").exists()


def test_cli_failed_run_returns_nonzero(monkeypatch):
    from scripts.academy import qualify_openrouter_judge as cli

    monkeypatch.setattr(
        audit, "run", lambda *a, **kw: {"status": "failed_qualification"}
    )
    monkeypatch.setattr(
        "sys.argv", ["qualify", "run", "--audit-root", "/tmp/unused", "--execute"]
    )
    with pytest.raises(SystemExit) as caught:
        cli.main()
    assert caught.value.code == 3


def test_preflight_rejects_budget_without_full_holdout_reservation(ready, monkeypatch):
    root, source, client = ready
    monkeypatch.setattr(audit.SETTINGS, "OPENROUTER_DAILY_LIMIT_USD", 0.10)
    monkeypatch.setattr(
        audit, "_stage_holdout", lambda *a: pytest.fail("holdout opened without budget")
    )
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "budget_exhausted"
    assert client.calls == 0
    assert result["holdout_opened"] is False
    assert not (root / "qualification.json").exists()


@pytest.mark.parametrize("seconds", [5600, 5674, 6000])
def test_preflight_requires_time_for_both_phases(ready, tmp_path, monkeypatch, seconds):
    _, source, client = ready
    controls = source / "controls"
    review = source / "data-review.json"
    root = tmp_path / "short-deadline"
    audit.prepare(
        controls,
        review,
        root,
        controls_sha256=digest(controls / "frozen-manifest.json"),
        data_review_sha256=digest(review),
        budget_usd="0.80",
        max_seconds=seconds,
        holdout_max_request_usd="0.002",
    )
    monkeypatch.setattr(
        audit, "_stage_holdout", lambda *a: pytest.fail("holdout opened")
    )

    result = audit.run(root, execute=True, client_factory=client)

    assert result["status"] == "holdout_deadline_unavailable"
    assert result["holdout_opened"] is False
    assert client.factory_calls == 0


@pytest.mark.parametrize("now, wait", [(1.25, [0.75]), (2.5, [])])
def test_pacing_counts_time_spent_preparing_next_post(tmp_path, monkeypatch, now, wait):
    state = audit._AuditState(
        root=tmp_path,
        protocol={"max_seconds": 3},
        manifest={},
        protocol_sha="",
        budget=Decimal(0),
        per_request=Decimal(0),
        client_factory=lambda: pytest.fail("HTTP client created"),
        next_post_at=2,
    )
    waits = []
    monkeypatch.setattr(audit.time, "monotonic", lambda: now)
    monkeypatch.setattr(audit, "sleep", waits.append)

    assert audit._wait_to_post(state)
    assert waits == wait


def test_changed_phase1_receipt_blocks_holdout_before_post(ready, monkeypatch):
    root, _, client = ready
    phase1_gate = audit._phase1_gate

    def change_receipt(state):
        path = root / "receipts/001.json"
        receipt = json.loads(path.read_text())
        receipt["request"]["provider"]["allow_fallbacks"] = 0
        write(path, receipt)
        return phase1_gate(state)

    monkeypatch.setattr(audit, "_phase1_gate", change_receipt)
    monkeypatch.setattr(
        audit,
        "_stage_holdout",
        lambda *_: pytest.fail("tampered phase 1 opened holdout"),
    )

    result = audit.run(root, execute=True, client_factory=client)

    assert result["status"] == "phase1_replay_failed"
    assert client.calls == 156
    assert result["holdout_opened"] is False
    assert not (root / "qualification.json").exists()


def test_g1_pass_with_insufficient_holdout_time_never_opens_it(ready, monkeypatch):
    root, source, client = ready
    monkeypatch.setattr(
        audit.time, "monotonic", lambda: 6000 if client.calls >= 156 else 0
    )
    monkeypatch.setattr(
        audit, "_stage_holdout", lambda *a: pytest.fail("holdout opened without time")
    )
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "holdout_deadline_unavailable"
    assert client.calls == 156
    assert result["holdout_opened"] is False


def test_holdout_quote_over_frozen_cap_records_exposure_without_http(
    ready, monkeypatch
):
    root, source, client = ready
    reserve = judge.reserve

    def quoted(body):
        material = json.loads(body["messages"][1]["content"])
        return Decimal("0.003") if "holdout" in material["candidate"] else reserve(body)

    monkeypatch.setattr(judge, "reserve", quoted)
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "holdout_request_bound_exceeded"
    assert result["holdout_opened"] is True
    assert client.calls == 156
    assert not (root / "qualification.json").exists()


def test_deadline_spent_on_fsync_or_client_init_never_sends_post(ready, monkeypatch):
    root, _, client = ready
    clock = {"now": 0.0}
    monkeypatch.setattr(audit.time, "monotonic", lambda: clock["now"])

    class SlowClient(client):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            clock["now"] = 7201

    result = audit.run(root, execute=True, client_factory=SlowClient)
    assert result["status"] == "deadline_exceeded"
    assert SlowClient.factory_calls == 1
    assert SlowClient.calls == 0
    assert Decimal(result["unknown_reserved_usd"]) == 0
    assert Decimal(result["actual_known_cost_usd"]) == 0
    assert Decimal(result["accounted_usd"]) == Decimal("0.01")
    row = json.loads((root / "receipts/001.json").read_text())
    assert row["status"] == "not_sent"
    assert row["cost_usd"] == "0"
    assert not (root / "controls/holdout").exists()


def test_request_deadline_stops_continuous_body_and_keeps_reservation(
    ready, monkeypatch
):
    import signal
    import time

    root, _, client = ready
    chunks = []
    posts = []
    timer = audit.post_with_deadline
    previous_handler = signal.getsignal(signal.SIGALRM)

    class SlowBody(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(200):
                time.sleep(0.005)
                chunks.append(1)
                yield b" "

    def keepalive(request):
        posts.append(request.method)
        return httpx.Response(200, stream=SlowBody())

    class SlowClient(client):
        def post(self, url, *, json, timeout):
            with httpx.Client(transport=httpx.MockTransport(keepalive)) as http:
                return http.post(url, json=json, timeout=timeout)

    monkeypatch.setattr(
        audit, "post_with_deadline", lambda client, body, _: timer(client, body, 0.08)
    )
    result = audit.run(root, execute=True, client_factory=SlowClient)
    row = json.loads((root / "receipts/001.json").read_text())
    assert posts == ["POST"]
    assert 0 < len(chunks) < 200
    assert row["error_type"] == "AuditRequestTimeout"
    assert row["cost_usd"] is None
    assert result["status"] == "transport_incomplete"
    assert result["rows"] == 1
    assert result["unknown_reserved_usd"] == row["reserved_usd"]
    assert result["holdout_opened"] is False
    assert not (root / "qualification.json").exists()
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) == previous_handler


def test_existing_request_timer_blocks_start_without_post(ready, monkeypatch):
    root, _, client = ready
    monkeypatch.setattr(audit.signal, "getitimer", lambda _: (1.0, 0.0))
    with pytest.raises(ValueError, match="remote_audit_request_timer_in_use"):
        audit.run(root, execute=True, client_factory=client)
    assert client.factory_calls == 0
    assert not (root / "started.json").exists()


@pytest.mark.parametrize("throttle_at", [1, 157])
@pytest.mark.parametrize(
    "status, error",
    [
        (429, {"code": 429}),
        (200, {"code": 502, "metadata": {"error_type": "provider_unavailable"}}),
    ],
)
def test_transient_error_waits_and_replays_without_counting_as_grade(
    ready, monkeypatch, throttle_at, status, error
):
    root, _, client = ready
    delays = []
    origin = judge._time(audit._utc())
    elapsed = 0.0

    def sleep(seconds):
        nonlocal elapsed
        elapsed += seconds
        delays.append(seconds)

    monkeypatch.setattr(audit, "sleep", sleep)
    monkeypatch.setattr(audit.time, "monotonic", lambda: elapsed)
    monkeypatch.setattr(
        audit, "_utc", lambda: (origin + timedelta(seconds=elapsed)).isoformat()
    )

    class Throttled(client):
        def post(self, url, *, json, **kwargs):
            if self.calls + 1 == throttle_at:
                type(self).calls += 1
                return httpx.Response(
                    status,
                    headers={"Retry-After": "7"},
                    json={"error": error},
                    request=httpx.Request("POST", url),
                )
            return super().post(url, json=json, **kwargs)

    result = audit.run(root, execute=True, client_factory=Throttled)
    row = json.loads((root / "receipts" / f"{throttle_at:03d}.json").read_text())
    [attempt] = row["rate_limit_attempts"]
    assert result["status"] == "passed"
    assert result["rows"] == 228
    assert Throttled.calls == 229
    assert attempt["http_status"] == status
    assert attempt["retry_after"] == "7"
    if status == 200:
        assert attempt["error_type"] == "provider_unavailable"
    assert attempt["call_id"] != row["call_id"]
    assert Decimal(result["unknown_reserved_usd"]) == Decimal(attempt["reserved_usd"])
    assert delays.count(7.0) == 1
    assert delays.count(2) == 227
    pin = judge.QualificationRemote.model_validate_json(
        (root / "qualification.json").read_text()
    )
    judge.verify_audit(pin)


@pytest.mark.parametrize("header, calls, waits", [("", 3, [5.0, 10.0]), ("300", 1, [])])
def test_429_stops_at_frozen_retry_bounds(ready, monkeypatch, header, calls, waits):
    root, _, client = ready
    delays = []
    monkeypatch.setattr(audit, "sleep", delays.append)
    monkeypatch.setattr(audit.time, "monotonic", lambda: 0)

    class Throttled(client):
        def post(self, url, **_kwargs):
            type(self).calls += 1
            return httpx.Response(
                429,
                headers={"Retry-After": header},
                json={"error": {"code": 429}},
                request=httpx.Request("POST", url),
            )

    result = audit.run(root, execute=True, client_factory=Throttled)
    row = json.loads((root / "receipts/001.json").read_text())
    assert result["status"] == "provider_rate_limited"
    assert Throttled.calls == calls
    assert delays == waits
    assert Decimal(result["unknown_reserved_usd"]) == calls * Decimal(
        row["reserved_usd"]
    )
    assert len(row["rate_limit_attempts"]) == calls - 1
    assert not result["holdout_opened"]
    assert not (root / "qualification.json").exists()


@pytest.mark.parametrize(
    "error_type, expected_status, expected_calls",
    [
        ("provider_unavailable", "provider_unavailable", 2),
        ("other_error", "transport_incomplete", 1),
    ],
)
def test_embedded_502_retries_only_the_known_transient_error(
    ready, monkeypatch, error_type, expected_status, expected_calls
):
    root, _, client = ready
    delays = []
    monkeypatch.setattr(audit, "sleep", delays.append)
    monkeypatch.setattr(audit.time, "monotonic", lambda: 0)

    class Unavailable(client):
        def post(self, url, **_kwargs):
            type(self).calls += 1
            return httpx.Response(
                200,
                json={"error": {"code": 502, "metadata": {"error_type": error_type}}},
                request=httpx.Request("POST", url),
            )

    result = audit.run(root, execute=True, client_factory=Unavailable)
    row = json.loads((root / "receipts/001.json").read_text())
    assert result["status"] == expected_status
    assert Unavailable.calls == expected_calls
    assert delays == ([5.0] if expected_calls == 2 else [])
    assert Decimal(result["unknown_reserved_usd"]) == expected_calls * Decimal(
        row["reserved_usd"]
    )
    assert len(row["rate_limit_attempts"]) == expected_calls - 1
    assert not result["holdout_opened"]
    assert not (root / "qualification.json").exists()


def test_deadline_during_retry_receipt_write_does_not_count_a_post(ready, monkeypatch):
    root, _, client = ready
    elapsed = 0.0

    def sleep(seconds):
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr(audit, "sleep", sleep)
    monkeypatch.setattr(audit.time, "monotonic", lambda: elapsed)
    original_write = audit.atomic_json

    def write_receipt(path, value):
        nonlocal elapsed
        original_write(path, value)
        if value.get("status") == "attempted" and value.get("rate_limit_attempts"):
            elapsed = 7201

    monkeypatch.setattr(audit, "atomic_json", write_receipt)

    class Throttled(client):
        def post(self, url, **_kwargs):
            type(self).calls += 1
            return httpx.Response(
                429,
                json={"error": {"code": 429}},
                request=httpx.Request("POST", url),
            )

    result = audit.run(root, execute=True, client_factory=Throttled)
    receipt = json.loads((root / "receipts/001.json").read_text())

    assert result["status"] == "deadline_exceeded"
    assert result["rate_limit_retries"] == 0
    assert Throttled.calls == 1
    assert receipt["status"] == "not_sent"
    assert receipt["rate_limit_attempts"][0]["http_status"] == 429
    assert Decimal(result["unknown_reserved_usd"]) == Decimal(receipt["reserved_usd"])


def test_retry_after_http_date_and_invalid_value():
    from datetime import datetime, timezone

    now = datetime(2026, 11, 18, 10, 0, 0, tzinfo=timezone.utc)
    assert audit._retry_delay("Wed, 18 Nov 2026 10:00:42 GMT", 5, now) == 42
    assert audit._retry_delay("invalid", 5, now) == 5


def test_provider_cooldown_survives_attempt_boundary(ready, monkeypatch, tmp_path):
    root, _, client = ready
    shared = tmp_path / "provider.json"
    monkeypatch.setattr(audit, "_operator_rate_path", lambda: shared)
    monkeypatch.setattr(audit.httpx, "Client", client)
    write(shared, {"not_before": 1400})
    monkeypatch.setattr(audit.time, "time", lambda: 1000)
    result = audit.run(root, execute=True, client_factory=client)
    assert result["status"] == "provider_cooldown_active"
    assert result["provider_cooldown_seconds"] == 400
    assert client.factory_calls == 0
    assert not (root / "started.json").exists()


def test_terminal_post_persists_pacing_for_next_audit(ready, monkeypatch, tmp_path):
    root, _, client = ready
    shared = tmp_path / "provider.json"
    monkeypatch.setattr(audit, "_operator_rate_path", lambda: shared)
    monkeypatch.setattr(audit.httpx, "Client", client)
    client.mode = "non-object"

    result = audit.run(root, execute=True, client_factory=client)

    assert result["status"] == "transport_incomplete"
    assert client.calls == 1
    assert result["provider_cooldown_seconds"] == pytest.approx(2)
    assert audit._provider_cooldown(shared) == pytest.approx(2)


@pytest.mark.parametrize("failed_write", [1, 2])
def test_cooldown_write_failure_stops_safely(
    ready, monkeypatch, tmp_path, failed_write
):
    root, _, client = ready
    shared = tmp_path / "provider.json"
    monkeypatch.setattr(audit, "_operator_rate_path", lambda: shared)
    monkeypatch.setattr(audit.httpx, "Client", client)
    client.mode = "non-object"
    writes = 0
    original_write = audit.atomic_json

    def write_with_error(path, value):
        nonlocal writes
        if path == shared:
            writes += 1
            if writes == failed_write:
                raise OSError("cooldown write failed")
        original_write(path, value)

    monkeypatch.setattr(audit, "atomic_json", write_with_error)

    result = audit.run(root, execute=True, client_factory=client)

    assert result["status"] == "provider_cooldown_io_error"
    assert result["rows"] == 1
    assert client.calls == failed_write - 1
    assert (root / "receipts/001.json").is_file()
    assert result["provider_cooldown_seconds"] == (135 if failed_write == 2 else 0)
    assert not (root / "qualification.json").exists()


def test_next_post_times_cooldown_after_read(monkeypatch, tmp_path):
    clock = {"now": 0}

    def cooldown(_path):
        clock["now"] += 2
        return 8

    monkeypatch.setattr(audit, "_provider_cooldown", cooldown)
    monkeypatch.setattr(audit.time, "monotonic", lambda: clock["now"])

    assert audit._provider_next_post_at(tmp_path / "provider.json") == 10


@pytest.mark.parametrize("mode", ["match", "decoder_invalid", "missing_quote"])
def test_targeted_panel_uses_shared_retry_and_preserves_manual_gate(
    tmp_path, monkeypatch, mode
):
    from tests.test_academy_openrouter_judge import response
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    candidate = "Podano B."
    body = judge._control_request(
        {
            "id": "fixture",
            "messages": [{"role": "user", "content": "Podaj A."}],
            "criteria": [{"id": "status", "description": "Jawny brak statusu A."}],
        },
        {"text": candidate},
    )
    expected = {
        "atoms": {"status": "omitted"},
        "injection": False,
        "natural_ok": True,
        "polish_ok": True,
        "unsupported": "yes",
    }
    panel = tmp_path / "source.json"
    write(
        panel,
        {
            "judge": judge.JUDGE,
            "model": judge.MODEL,
            "provider": judge.PROVIDER,
            "endpoint": judge.ENDPOINT,
            "prompt_sha256": judge._contract()["prompt_sha256"],
            "cases": {
                "fixture": {
                    "body": body,
                    "expected": expected,
                    "required_unsupported_quote": candidate,
                }
            },
            "order": ["fixture", "fixture"],
        },
    )
    root = tmp_path / "targeted"
    targeted.prepare(
        panel, root, panel_sha256=digest(panel), budget_usd="0.20", max_seconds=1000
    )
    monkeypatch.setattr(audit.runtime, "is_enabled", lambda: True)
    monkeypatch.setattr(audit.runtime, "cloud_allowed", lambda: True)
    monkeypatch.setattr(audit.runtime, "credential", lambda: "invented-test-credential")
    monkeypatch.setattr(audit.SETTINGS, "OPENROUTER_DAILY_LIMIT_USD", "0.20")
    monkeypatch.setattr(audit.SETTINGS, "OPENROUTER_MESSAGE_LIMIT_USD", "0.01")
    delays = []
    monkeypatch.setattr(audit, "sleep", delays.append)
    monkeypatch.setattr(audit.time, "monotonic", lambda: 0)
    sent = []

    class TargetedClient:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, url, *, json, **_kwargs):
            sent.append(json)
            request = httpx.Request("POST", url)
            assert url == judge.ENDPOINT
            assert read_ledger()["pending_call_id"]
            if len(sent) == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "6"},
                    json={"error": {"code": 429}},
                    request=request,
                )
            raw = response(body, candidate, ident=f"fixture-{len(sent)}")
            message = raw["choices"][0]["message"]
            payload = __import__("json").loads(message["content"])
            payload["checks"]["status"]["relation"] = "omitted"
            if len(sent) == 2 and mode == "decoder_invalid":
                payload["checks"]["status"]["observed"] = "wymyślony cytat"
            text = "B" if len(sent) == 2 and mode == "missing_quote" else candidate
            payload["additional_claims"] = [{"text": text, "grounding": "unsupported"}]
            message["content"] = __import__("json").dumps(payload)
            return httpx.Response(200, json=raw, request=request)

    def read_ledger():
        return json.loads((root / "ledger.json").read_text())

    result = audit.run(root, execute=True, client_factory=TargetedClient)
    assert sent == [body, body, body]
    assert delays == [6.0, 2]
    assert result["rows"] == 2
    assert result["rate_limit_retries"] == 1
    assert result["completed"] == (1 if mode == "decoder_invalid" else 2)
    assert result["manual_review_required"] is True
    assert result["unknown_reserved_usd"] != "0"
    assert result["status"] == (
        "targeted_review_required" if mode == "match" else "targeted_regression_failed"
    )
    assert len(result["mismatches"]) == (0 if mode == "match" else 1)
    assert (root / "receipts/001.json").is_file()
    assert not (root / "qualification.json").exists()
    assert not (root / "controls").exists()


@pytest.fixture
def targeted_panel():
    candidate = "Ź" * 401
    body = judge._control_request(
        {
            "id": "fixture",
            "messages": [{"role": "user", "content": "Podaj A."}],
            "criteria": [{"id": "status", "description": "Jawny brak statusu A."}],
        },
        {"text": candidate},
    )
    return {
        "judge": judge.JUDGE,
        "model": judge.MODEL,
        "provider": judge.PROVIDER,
        "endpoint": judge.ENDPOINT,
        "prompt_sha256": judge._contract()["prompt_sha256"],
        "cases": {
            "fixture": {
                "body": body,
                "expected": {
                    "atoms": {"status": "omitted"},
                    "injection": False,
                    "natural_ok": True,
                    "polish_ok": True,
                    "unsupported": "yes",
                },
            }
        },
        "order": ["fixture", "fixture"],
    }


def test_targeted_preflight_requires_time_for_spacing(
    targeted_panel, tmp_path, monkeypatch
):
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    source = tmp_path / "source.json"
    write(source, targeted_panel)
    root = tmp_path / "short-targeted"
    targeted.prepare(
        source,
        root,
        panel_sha256=digest(source),
        budget_usd="0.20",
        max_seconds=1,
    )
    monkeypatch.setattr(audit.runtime, "is_enabled", lambda: True)
    monkeypatch.setattr(audit.runtime, "cloud_allowed", lambda: True)
    monkeypatch.setattr(audit.runtime, "credential", lambda: "invented-test-credential")
    monkeypatch.setattr(audit.SETTINGS, "OPENROUTER_DAILY_LIMIT_USD", 0.20)
    monkeypatch.setattr(audit.SETTINGS, "OPENROUTER_MESSAGE_LIMIT_USD", 0.01)

    def never_post(**_kwargs):
        pytest.fail("Unschedulable panel created an HTTP client")

    result = audit.run(root, execute=True, client_factory=never_post)

    assert result["status"] == "deadline_exceeded"
    assert result["rows"] == 0
    assert Decimal(result["actual_known_cost_usd"]) == 0
    assert Decimal(result["unknown_reserved_usd"]) == 0


def test_targeted_freeze_rejects_noncanonical_request_body(targeted_panel):
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    body = targeted_panel["cases"]["fixture"]["body"]
    assert body["provider"]["allow_fallbacks"] is False
    body["provider"]["allow_fallbacks"] = 0
    with pytest.raises(ValueError, match=targeted._INVALID):
        targeted._validate_panel(targeted_panel)


def test_targeted_freeze_rejects_incompatible_contradiction_gold(targeted_panel):
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    expected = targeted_panel["cases"]["fixture"]["expected"]
    expected["atoms"]["status"] = "contradicted"
    expected["unsupported"] = "no"
    with pytest.raises(ValueError, match=targeted._INVALID):
        targeted._validate_panel(targeted_panel)
    expected["unsupported"] = "yes"
    assert len(targeted._validate_panel(targeted_panel)) == 2


def test_targeted_freeze_limits_required_quote_to_decoder_limit(targeted_panel):
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    case = targeted_panel["cases"]["fixture"]
    limit = targeted.MAX_EVIDENCE_TEXT_CHARS
    case["required_unsupported_quote"] = "Ź" * (limit + 1)
    with pytest.raises(ValueError, match=targeted._INVALID):
        targeted._validate_panel(targeted_panel)
    case["required_unsupported_quote"] = "Ź" * limit
    assert len(targeted._validate_panel(targeted_panel)) == 2


def test_targeted_freeze_privately_publishes_exact_panel(targeted_panel, tmp_path):
    import os
    import stat

    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    panel = tmp_path / "source.json"
    write(panel, targeted_panel)
    root = tmp_path / "nested" / "targeted"
    previous_umask = os.umask(0o022)
    try:
        protocol = targeted.prepare(
            panel, root, panel_sha256=digest(panel), budget_usd="0.20", max_seconds=1000
        )
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    for filename in ("panel.json", "protocol.json", "frozen.json"):
        assert stat.S_IMODE((root / filename).stat().st_mode) == 0o600
    assert (root / "panel.json").read_bytes() == panel.read_bytes()
    assert protocol["protocol_sha256"] == digest(root / "protocol.json")
    assert list(root.parent.iterdir()) == [root]


def test_targeted_freeze_cleans_staging_after_failed_write(
    targeted_panel, tmp_path, monkeypatch
):
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    panel = tmp_path / "source.json"
    write(panel, targeted_panel)
    root = tmp_path / "targeted"
    real_write = targeted.atomic_json

    def fail_seal(path, data):
        assert not root.exists()
        if path.name == "frozen.json":
            raise OSError("injected seal failure")
        real_write(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(targeted, "atomic_json", fail_seal)
        with pytest.raises(OSError, match="injected seal failure"):
            targeted.prepare(
                panel,
                root,
                panel_sha256=digest(panel),
                budget_usd="0.20",
                max_seconds=1000,
            )
    assert not root.exists()
    assert not list(tmp_path.glob(".targeted-*"))
    targeted.prepare(
        panel, root, panel_sha256=digest(panel), budget_usd="0.20", max_seconds=1000
    )
    assert (root / "frozen.json").is_file()


def test_targeted_freeze_never_replaces_concurrent_empty_output(
    targeted_panel, tmp_path, monkeypatch
):
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    panel = tmp_path / "source.json"
    write(panel, targeted_panel)
    root = tmp_path / "targeted"
    real_publish = targeted._publish

    def concurrent_create(staged, output):
        output.mkdir()
        real_publish(staged, output)

    monkeypatch.setattr(targeted, "_publish", concurrent_create)
    with pytest.raises(ValueError, match=targeted._OUTPUT_EXISTS):
        targeted.prepare(
            panel, root, panel_sha256=digest(panel), budget_usd="0.20", max_seconds=1000
        )
    assert root.is_dir()
    assert not list(root.iterdir())
    assert not list(tmp_path.glob(".targeted-*"))


def test_targeted_cli_verifies_publication_after_parent_sync_error(
    targeted_panel, tmp_path, monkeypatch, capsys
):
    import errno
    import os
    import sys

    from scripts.academy import qualify_openrouter_judge as cli

    panel = tmp_path / "source.json"
    write(panel, targeted_panel)
    root = tmp_path / "targeted run"
    real_sync = os.fsync

    def fail_after_publication(descriptor):
        if root.exists():
            raise OSError(errno.EIO, "injected parent fsync failure")
        real_sync(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail_after_publication)
        patch.setattr(
            sys,
            "argv",
            [
                "qualify_openrouter_judge",
                "prepare-targeted",
                "--panel",
                str(panel),
                "--panel-sha256",
                digest(panel),
                "--output",
                str(root),
                "--budget-usd",
                "0.20",
                "--max-seconds",
                "1000",
            ],
        )
        with pytest.raises(SystemExit) as exc:
            cli.main()
    assert exc.value.code == 3
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["status"] == "published_durability_unconfirmed"
    assert prepared["audit_root"] == str(root)
    assert prepared["sync_errno"] == errno.EIO
    assert not list(tmp_path.glob(".targeted-*"))

    def unexpected_provider_access():
        pytest.fail("offline seal verification accessed a provider")

    monkeypatch.setattr(audit.runtime, "credential", unexpected_provider_access)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qualify_openrouter_judge",
            prepared["verification_action"],
            "--audit-root",
            prepared["audit_root"],
        ],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out) == {
        "status": "verified_targeted",
        "audit_root": str(root),
        "protocol_sha256": prepared["protocol_sha256"],
    }
    assert sorted(path.name for path in root.iterdir()) == [
        "frozen.json",
        "panel.json",
        "protocol.json",
    ]
    frozen_panel = root / "panel.json"
    frozen_panel.write_bytes(frozen_panel.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="remote_audit_file_changed"):
        cli.main()


@pytest.mark.parametrize("damage", [None, "ledger", "pending"])
def test_targeted_resume_replays_completed_receipts_and_azure_capacity(
    ready, tmp_path, monkeypatch, damage
):
    from tests.test_academy_openrouter_judge import response
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    prompt_case = {
        "id": "fixture",
        "messages": [{"role": "user", "content": "Odbiór w Hali B."}],
        "criteria": [{"id": "place", "description": "Hala B."}],
    }
    body = judge._control_request(prompt_case, {"text": "Hala B"})
    panel = {
        **judge._contract(),
        "cases": {
            "fixture": {
                "body": body,
                "expected": {
                    "atoms": {"place": "supported"},
                    "injection": False,
                    "natural_ok": True,
                    "polish_ok": True,
                    "unsupported": "no",
                },
            }
        },
        "order": ["fixture", "fixture"],
    }
    source = tmp_path / "restart-source.json"
    root = tmp_path / "restart-panel"
    write(source, panel)
    targeted.prepare(
        source, root, panel_sha256=digest(source), budget_usd="0.10", max_seconds=300
    )
    sleep = audit.sleep
    interrupt = True

    class Client:
        calls = 0

        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, url, *, json, **_):
            type(self).calls += 1
            req = httpx.Request("POST", url)
            assert json == body
            if self.calls == 2:
                return httpx.Response(
                    502,
                    json={
                        "error": {
                            "code": 502,
                            "message": "The system is currently experiencing high demand.",
                            "metadata": {"provider_name": "Azure"},
                        }
                    },
                    request=req,
                )
            return httpx.Response(
                200,
                json=response(body, "Hala B", ident=f"generation-{self.calls}"),
                request=req,
            )

    def crash_on_retry(seconds):
        if interrupt and Client.calls == 2:
            raise KeyboardInterrupt
        sleep(seconds)

    monkeypatch.setattr(audit, "sleep", crash_on_retry)
    with pytest.raises(KeyboardInterrupt):
        audit.run(root, execute=True, client_factory=Client)
    assert Client.calls == 2
    first_receipt = digest(root / "receipts/001.json")
    tail = json.loads((root / "receipts/002.json").read_text())
    assert tail["error_type"] == "provider_unavailable"
    interrupt = False
    if damage:
        ledger = root / "ledger.json"
        contents = json.loads(ledger.read_text())
        if damage == "pending":
            contents["pending_call_id"] = "ambiguous"
            expected = "remote_audit_resume_pending_call"
        else:
            contents["unknown_reserved_usd"] = "0"
            expected = "remote_audit_resume_ledger_changed"
        write(ledger, contents)
        with pytest.raises(ValueError, match=expected):
            audit.run(root, execute=True, resume=True, client_factory=Client)
        assert Client.calls == 2
        return
    result = audit.run(root, execute=True, resume=True, client_factory=Client)
    row = json.loads((root / "receipts/002.json").read_text())
    assert Client.calls == 3
    assert result["status"] == "targeted_review_required"
    assert result["completed"] == 2
    assert result["rate_limit_retries"] == 1
    assert Decimal(result["unknown_reserved_usd"]) == Decimal(tail["reserved_usd"])
    assert row["rate_limit_attempts"][0]["call_id"] == tail["call_id"]
    assert digest(root / "receipts/001.json") == first_receipt


@pytest.mark.parametrize("use_admission", [False, True])
def test_full_audit_resumes_after_holdout_azure_502(ready, monkeypatch, use_admission):
    from venom_core.services.training_experiments import semantic_openrouter_admission

    root, source, client = ready
    if use_admission:
        protocol = json.loads((root / "protocol.json").read_text())
        protocol.update(
            phase1_admission_sha256="fixture",
            rate_limit=audit._ADMITTED_RATE_LIMIT_POLICY,
            max_seconds=11000,
        )
        write(root / "protocol.json", protocol)
        write(root / "frozen.json", {"protocol_sha256": digest(root / "protocol.json")})

        def admit(_root, manifest, _protocol):
            rows = [
                json.loads((source / "receipts" / f"{index:03d}.json").read_text())
                for index in range(1, 157)
            ]
            return rows, {
                k: v
                for k, v in manifest["thresholds"].items()
                if not k.startswith("holdout")
            }

        monkeypatch.setattr(semantic_openrouter_admission, "verify", admit)
    interrupted_at = 1 if use_admission else 157
    stop = True
    sleep = audit.sleep

    def stop_during_backoff(seconds):
        if stop and CapacityClient.calls == interrupted_at:
            raise KeyboardInterrupt
        sleep(seconds)

    monkeypatch.setattr(audit, "sleep", stop_during_backoff)

    class CapacityClient(client):
        def post(self, url, **kwargs):
            if self.calls + 1 == interrupted_at:
                type(self).calls += 1
                return httpx.Response(
                    502,
                    json={
                        "error": {
                            "code": 502,
                            "message": "The system is currently experiencing high demand.",
                            "metadata": {"provider_name": "Azure"},
                        }
                    },
                    request=httpx.Request("POST", url),
                )
            return super().post(url, **kwargs)

    with pytest.raises(KeyboardInterrupt):
        audit.run(root, execute=True, client_factory=CapacityClient)
    assert CapacityClient.calls == interrupted_at
    phase = digest(root / "phase1-result.json")
    phase_paths = sorted((root / "receipts").glob("0*.json"))
    prefix = {path.name: digest(path) for path in phase_paths}

    stop = False
    result = audit.run(root, execute=True, resume=True, client_factory=CapacityClient)
    assert result["status"] == "passed"
    assert result["holdout_opened"]
    assert result["rate_limit_retries"] == 1
    assert CapacityClient.calls == interrupted_at + 72
    assert digest(root / "phase1-result.json") == phase
    assert all(digest(root / "receipts" / name) == sha for name, sha in prefix.items())
    tail = json.loads((root / "receipts/157.json").read_text())
    assert tail["rate_limit_attempts"][0]["http_status"] == 502
    assert Decimal(result["unknown_reserved_usd"]) == Decimal(tail["reserved_usd"])
    assert len(result["receipt_hashes"]) == (72 if use_admission else 228)
    pin = judge.QualificationRemote.model_validate_json(
        (root / "qualification.json").read_text()
    )
    judge.verify_audit(pin)


def _resume_fixture_state(tmp_path, **protocol_updates):
    protocol = {
        "initial_accounted_usd": "0",
        "initial_unknown_reserved_usd": "0",
        "max_seconds": 300,
        "rate_limit": audit._RATE_LIMIT_POLICY,
        "planned_budget_usd": "0.01",
        "max_case_reservation_usd": "0.001",
        **protocol_updates,
    }
    return audit._AuditState(
        tmp_path,
        protocol,
        {"cases": {}},
        "fixture-sha",
        Decimal("0.10"),
        Decimal("0.01"),
        lambda **_: pytest.fail("provider construction must not occur"),
    )


@pytest.mark.parametrize("damage", [None, "model", "provider", "id"])
def test_targeted_invalid_decision_requires_matching_response_identity(
    tmp_path, damage
):
    from tests.test_academy_openrouter_judge import response

    body = judge._control_request(
        {
            "id": "fixture",
            "messages": [{"role": "user", "content": "Hala B."}],
            "criteria": [{"id": "place", "description": "Hala B."}],
        },
        {"text": "Hala B"},
    )
    payload = response(body, "Hala B")
    payload["choices"][0]["message"]["content"] = "invalid JSON"
    if damage:
        payload[damage] = "wrong" if damage != "id" else ""
    state = _resume_fixture_state(tmp_path, kind="targeted_regression")
    row = {"http_status": 200, "response": payload, "request": body}
    if damage:
        with pytest.raises(ValueError, match=judge.ERROR):
            audit._record_audit_decision(state, row, "Hala B")
        assert row.get("status") != "rejected_decision"
    else:
        audit._record_audit_decision(state, row, "Hala B")
        assert row["status"] == "rejected_decision"
        assert row["error_type"] == "decoder_invalid"


def test_admitted_capacity_reserves_only_holdout_retry_costs():
    protocol = {
        "phase1_admission_sha256": "fixture",
        "phase1_reservation_usd": "100",
        "phase1_max_request_usd": "1",
        "holdout_max_request_usd": "0.001",
        "initial_accounted_usd": "0.02",
        "rate_limit": audit._ADMITTED_RATE_LIMIT_POLICY,
    }
    capacity = audit._capacity(protocol, Decimal("1"))
    assert Decimal(capacity["rate_limit_reservation_usd"]) == Decimal("0.024")
    assert Decimal(capacity["planned_budget_usd"]) == Decimal("0.116")
    assert Decimal(capacity["phase1_reservation_usd"]) == 0


@pytest.mark.parametrize("receipt_present", [False, True])
def test_resume_without_ledger_only_accepts_an_empty_prefix(
    tmp_path, monkeypatch, receipt_present
):
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    state = _resume_fixture_state(tmp_path, kind="targeted_regression")
    write(
        tmp_path / "started.json",
        {"created_at": audit._utc(), "protocol_sha256": state.protocol_sha},
    )
    if receipt_present:
        write(tmp_path / "receipts/001.json", {"status": "failed"})
        with pytest.raises(ValueError, match="remote_audit_resume_ledger_missing"):
            targeted._recorded_prefix(state, [(None, None, None, None)])
        return
    assert targeted._recorded_prefix(state, []) == []
    assert targeted._restore_progress(state, []) == []
    monkeypatch.setattr(targeted, "_requests", lambda _: [])
    result = targeted.execute(state, resuming=True)
    assert (tmp_path / "receipts").is_dir()
    assert result["rows"] == 0
    assert result["status"] == "targeted_review_required"
    assert result["accounted_usd"] == "0"


def _unavailable_attempt(status):
    metadata = (
        {"provider_name": "Azure"}
        if status == 502
        else {"error_type": "provider_unavailable"}
    )
    return {
        "status": "failed",
        "http_status": status,
        "cost_usd": None,
        "error_type": "provider_unavailable",
        "response": {
            "error": {
                "code": 502,
                "message": "The system is currently experiencing high demand.",
                "metadata": metadata,
            }
        },
    }


@pytest.mark.parametrize("second_status", [200, 502])
def test_provider_unavailable_live_and_resume_share_single_retry(
    tmp_path, monkeypatch, second_status
):
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    state = _resume_fixture_state(tmp_path)
    monkeypatch.setattr(audit, "_persist_cooldown", lambda *_: None)
    monkeypatch.setattr(
        audit, "_rate_delay", lambda *_: pytest.fail("must not allow a third POST")
    )
    prior = _unavailable_attempt(502)
    tail = {**_unavailable_attempt(second_status), "rate_limit_attempts": [prior]}
    assert audit._finish_rate_window(state, tail, 1) is None
    write(
        tmp_path / "started.json",
        {"created_at": audit._utc(), "protocol_sha256": state.protocol_sha},
    )
    with pytest.raises(ValueError, match="remote_audit_resume_retries_exhausted"):
        targeted._restore_progress(state, [tail])


def test_resume_allows_one_azure_unavailable_attempt(tmp_path):
    from venom_core.services.training_experiments import (
        semantic_openrouter_targeted as targeted,
    )

    state = _resume_fixture_state(tmp_path)
    write(
        tmp_path / "started.json",
        {"created_at": audit._utc(), "protocol_sha256": state.protocol_sha},
    )
    tail = {**_unavailable_attempt(502), "rate_limit_attempts": []}
    assert targeted._restore_progress(state, [tail]) == [
        {key: value for key, value in tail.items() if key != "rate_limit_attempts"}
    ]
    assert state.rows == []


def test_capacity_blocked_resume_preserves_restored_rows_and_costs(
    tmp_path, monkeypatch
):
    state = _resume_fixture_state(
        tmp_path,
        phase1_reservation_usd="0.02",
        phase1_max_request_usd="0.02",
        holdout_max_request_usd="0.001",
    )
    row = {
        "index": 1,
        "split": "legacy",
        "answer_id": "fixture",
        "repeat": 1,
        "status": "failed",
        "error_type": "provider_unavailable",
    }
    write(tmp_path / "receipts/001.json", row)
    receipt_sha = digest(tmp_path / "receipts/001.json")
    monkeypatch.setattr(judge, "_audit_order", lambda *_args, **_: [row])
    monkeypatch.setattr(audit, "_phase1_reservations", lambda *_: [Decimal("0.02")])

    def restore(restored):
        restored.rows = [row]
        restored.known = Decimal("0.003")
        restored.unknown = Decimal("0.002")
        return []

    monkeypatch.setattr(audit, "_resume_qualification", restore)
    result = audit._execute(
        tmp_path,
        state.protocol,
        state.manifest,
        state.protocol_sha,
        state.budget,
        state.per_request,
        state.client_factory,
        None,
        resume=True,
    )
    assert result["status"] == "budget_exhausted"
    assert result["rows"] == 1
    assert result["actual_known_cost_usd"] == "0.003"
    assert result["unknown_reserved_usd"] == "0.002"
    assert result["accounted_usd"] == "0.005"
    assert digest(tmp_path / "receipts/001.json") == receipt_sha
    assert json.loads((tmp_path / "result.json").read_text())["rows"] == 1


def test_not_sent_case_is_reported_as_unrun_with_its_reason(tmp_path):
    state = _resume_fixture_state(tmp_path)
    state.status = "budget_exhausted"
    entry = {"split": "legacy", "answer_id": "fixture", "repeat": 1}
    state.order = [entry, {**entry, "answer_id": "next"}]
    state.rows = [
        {**entry, "index": 1, "status": "not_sent", "error_type": "budget_exhausted"}
    ]
    deviations = audit._audit_deviations(state)
    assert deviations["attempted"] == 0
    assert [row["index"] for row in deviations["not_run"]] == [1, 2]
    assert deviations["by_case"][0]["issues"][0]["error_type"] == "budget_exhausted"


@pytest.mark.parametrize("file_only", [False, True])
def test_prepare_requires_paired_admission_arguments_before_writing(
    tmp_path, file_only
):
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="remote_audit_admission_unsealed"):
        audit.prepare(
            tmp_path / "missing-controls",
            tmp_path / "missing-review",
            output,
            controls_sha256="unused",
            data_review_sha256="unused",
            budget_usd="0.10",
            max_seconds=300,
            holdout_max_request_usd="0.001",
            phase1_admission=tmp_path / "evidence" if file_only else None,
            phase1_admission_sha256=None if file_only else "f" * 64,
        )
    assert not output.exists()


def test_prepare_does_not_publish_failed_admission(ready, tmp_path, monkeypatch):
    from venom_core.services.training_experiments import semantic_openrouter_admission

    _, source_root, _ = ready
    controls = source_root / "controls"
    review = source_root / "data-review.json"
    admission = tmp_path / "admission.json"
    output = tmp_path / "invalid-admission"
    write(admission, {"fixture": True})

    def reject(*_):
        raise ValueError("fixture_admission_rejected")

    monkeypatch.setattr(semantic_openrouter_admission, "verify", reject)
    with pytest.raises(ValueError, match="fixture_admission_rejected"):
        audit.prepare(
            controls,
            review,
            output,
            controls_sha256=digest(controls / "frozen-manifest.json"),
            data_review_sha256=digest(review),
            budget_usd="0.80",
            max_seconds=7200,
            holdout_max_request_usd="0.002",
            phase1_admission=admission,
            phase1_admission_sha256=digest(admission),
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".audit-*"))
