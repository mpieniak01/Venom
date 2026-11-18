"""The operator auditor is exercised only with invented fixtures and fake HTTP."""

from __future__ import annotations

import copy
import json
from decimal import Decimal

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
    monkeypatch.setattr(audit, "sleep", lambda _: None)
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


@pytest.mark.parametrize("fail_at", [1, 2])
def test_system_error_stops_without_retry_and_retains_unknown_cost(ready, fail_at):
    root, _, client = ready
    client.mode, client.fail_at = "404-text", fail_at
    result = audit.run(root, execute=True, client_factory=client)
    assert client.calls == fail_at
    assert result["status"] == "transport_incomplete"
    assert audit.judge._money(result["unknown_reserved_usd"]) > 0
    assert result["metrics"] is None
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
    monkeypatch.setattr(audit.time, "monotonic", lambda: next(ticks))
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
def test_429_waits_and_replays_without_counting_throttle_as_grade(
    ready, monkeypatch, throttle_at
):
    root, _, client = ready
    delays = []
    monkeypatch.setattr(audit, "sleep", delays.append)

    class Throttled(client):
        def post(self, url, *, json, **kwargs):
            if self.calls + 1 == throttle_at:
                type(self).calls += 1
                return httpx.Response(
                    429,
                    headers={"Retry-After": "7"},
                    json={"error": {"code": 429}},
                    request=httpx.Request("POST", url),
                )
            return super().post(url, json=json, **kwargs)

    result = audit.run(root, execute=True, client_factory=Throttled)
    row = json.loads((root / "receipts" / f"{throttle_at:03d}.json").read_text())
    [attempt] = row["rate_limit_attempts"]
    assert result["status"] == "passed"
    assert result["rows"] == 228
    assert Throttled.calls == 229
    assert attempt["http_status"] == 429
    assert attempt["retry_after"] == "7"
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
