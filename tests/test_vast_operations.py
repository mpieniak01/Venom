"""Local rental recovery and workload tests; fake API only."""

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from venom_core.infrastructure.providers.vast.client import VastError, ssh_fingerprint
from venom_core.infrastructure.providers.vast.models import WorkloadProfile, digest, now
from venom_core.services.vast_environments.billing import costs
from venom_core.services.vast_environments.cli import main
from venom_core.services.vast_environments.evaluation import (
    OllamaProbe,
    compare,
    fixture_image,
)
from venom_core.services.vast_environments.lifecycle import Environments
from venom_core.services.vast_environments.operations import monitor, workload
from venom_core.services.vast_environments.ssh import inspect, ssh_args
from venom_core.services.vast_environments.startup import startup
from venom_core.services.vast_environments.store import Journal

PUBLIC_KEY = "ssh-ed25519 YWJjZA== fixture"


@pytest.fixture
def service(tmp_path):
    profile = WorkloadProfile(
        name="fake", cpu_arch="arm64", image="test@sha256:" + "a" * 64
    )
    offer = {
        "id": 12,
        "host_id": 3,
        "machine_id": 4,
        "cpu_arch": "arm64",
        "num_gpus": 1,
        "gpu_frac": 1,
        "rentable": True,
        "rented": False,
        "verification": "verified",
        "cpu_ram": 128000,
        "gpu_ram": 119000,
        "cpu_cores_effective": 20,
        "reliability": 0.999,
        "disk_space": 250,
        "duration": 10000,
        "direct_port_count": 10,
        "search": {"totalHour": "0.4", "diskHour": "0.02"},
    }
    identity = tmp_path / "identity"
    identity.write_text("fake-private-key-for-test")
    Path(str(identity) + ".pub").write_text(PUBLIC_KEY)
    api = Mock()
    api.offers.return_value = [offer]
    api.ssh_fingerprints.return_value = [ssh_fingerprint(PUBLIC_KEY)]
    api.create.return_value = 88
    api.instance.return_value = {
        "id": 88,
        "actual_status": "running",
        "ssh_host": "example.test",
        "ssh_port": 22,
    }
    api.instances.return_value = []
    svc = Environments(api, Journal(tmp_path / "journal"))
    plan = svc.plan(
        profile, 12, Decimal("0.5"), Decimal("1"), identity, tmp_path / "known_hosts"
    )
    return svc, plan, offer


def test_create_and_recover(service):
    svc, plan, _ = service
    assert svc.create(plan.plan_id).instance_id == 88
    assert svc.reconcile(plan.plan_id).state == "running"
    with pytest.raises(VastError, match="vast.reconcile_required"):
        svc.create(plan.plan_id)
    assert svc.client.create.call_count == 1
    payload = svc.client.create.call_args.args[1]
    assert payload["cancel_unavail"] is True
    assert payload["disk"] == 150
    assert payload["label"] == "venom-" + plan.plan_id
    assert "VAST_API_KEY" not in json.dumps(payload)


@pytest.mark.parametrize(
    "ambiguous,state", [(True, "outcome_unknown"), (False, "failed")]
)
def test_create_error(service, ambiguous, state):
    svc, plan, _ = service
    svc.client.create.side_effect = VastError(
        "vast.transport_error", ambiguous=ambiguous
    )
    with pytest.raises(VastError):
        svc.create(plan.plan_id)
    assert svc.journal.record(plan.plan_id).state == state
    with pytest.raises(VastError):
        svc.create(plan.plan_id)
    assert svc.client.create.call_count == 1


def test_reconcile_unknown_never_rerents(service):
    svc, plan, _ = service
    rec = svc.journal.record(plan.plan_id)
    svc._event(rec, "submitting")
    assert svc.reconcile(plan.plan_id).state == "outcome_unknown"
    svc.client.instances.return_value = [
        {"id": 88, "label": "venom-" + plan.plan_id, "host_id": 3, "machine_id": 4}
    ]
    assert svc.reconcile(plan.plan_id).instance_id == 88
    svc.client.create.assert_not_called()


def test_unknown_observation_preserves_intent(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    svc.export(plan.plan_id)
    svc.change(plan.plan_id, "destroy")
    assert svc.reconcile(plan.plan_id).state == "running"
    assert svc.journal.record(plan.plan_id).pending_action == "destroy"
    svc.client.instance.side_effect = VastError("vast.http_error", 404)
    assert svc.reconcile(plan.plan_id).state == "destroyed"


def test_stop_not_destroyed_on_missing_data(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    svc.change(plan.plan_id, "stop")
    svc.client.instance.side_effect = VastError("vast.http_error", 404)
    with pytest.raises(VastError):
        svc.reconcile(plan.plan_id)
    assert svc.journal.record(plan.plan_id).state == "unknown"
    assert svc.journal.record(plan.plan_id).pending_action == "stop"


def test_stop_start_export_cleanup(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    assert svc.change(plan.plan_id, "stop").state == "stop_requested"
    svc.client.instance.return_value = {"id": 88, "actual_status": "stopped"}
    assert svc.reconcile(plan.plan_id).pending_action is None
    assert svc.change(plan.plan_id, "start").state == "start_requested"
    with pytest.raises(VastError, match="vast.export_required"):
        svc.change(plan.plan_id, "destroy")
    assert svc.export(plan.plan_id)["record"]["instance_id"] == 88
    assert svc.change(plan.plan_id, "destroy").state == "destroy_requested"
    assert (
        svc.journal.path(plan.plan_id, ".export.json").stat().st_mode & 0o777 == 0o600
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ({"cpu_arch": "amd64"}, "vast.offer_not_eligible"),
        ({"machine_id": 99}, "vast.offer_changed"),
        ({"search": {"totalHour": "0.45"}}, "vast.price_changed"),
        ({"search": {"totalHour": "0.9"}}, "vast.budget_exceeded"),
    ],
)
def test_fresh_offer_checks(service, change, code):
    svc, plan, offer = service
    svc.client.offers.return_value = [{**offer, **change}]
    with pytest.raises(VastError, match=code):
        svc.create(plan.plan_id)
    svc.client.create.assert_not_called()


def test_expiry_checksum_and_keys(service):
    svc, plan, _ = service
    original = plan.checksum
    plan.expires_at = now() - timedelta(seconds=1)
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    with pytest.raises(VastError, match="vast.plan_expired"):
        svc.create(plan.plan_id)
    plan.expires_at = now() + timedelta(minutes=5)
    plan.checksum = original
    svc.journal.save_plan(plan)
    with pytest.raises(VastError, match="vast.plan_changed"):
        svc.create(plan.plan_id)
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    svc.client.ssh_fingerprints.return_value = []
    with pytest.raises(VastError, match="vast.ssh_key_not_registered"):
        svc.create(plan.plan_id)


def test_plan_rejects_missing_offers_and_budget(service):
    svc, plan, _ = service
    svc.client.offers.return_value = []
    with pytest.raises(VastError, match="vast.offer_expired"):
        svc._offer(plan.profile, 12)
    with pytest.raises(VastError, match="vast.invalid_plan_id"):
        svc.journal.record("../bad")


def test_locks_and_record_mismatch(service):
    svc, plan, _ = service
    with svc.journal.lock(plan.plan_id):
        with pytest.raises(VastError, match="vast.plan_busy"):
            with svc.journal.lock(plan.plan_id):
                pass
    rec = svc.journal.record(plan.plan_id)
    other = plan.plan_id[:-1] + ("a" if plan.plan_id[-1] != "a" else "b")
    rec.plan_id = other
    svc.journal.write(
        svc.journal.path(plan.plan_id, ".record.json"), rec.model_dump(mode="json")
    )
    with pytest.raises(VastError, match="vast.record_mismatch"):
        svc.journal.record(plan.plan_id)


def test_cleanup_policy_and_monitor(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    with pytest.raises(VastError, match="vast.manual_cleanup_required"):
        svc.cleanup(plan.plan_id)
    plan.finish_policy = "destroy"
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    rec = svc.journal.record(plan.plan_id)
    rec.submitted_at = now() - timedelta(hours=1)
    svc.journal.save_record(rec)
    assert monitor(svc, plan.plan_id)["state"] == "destroy_requested"
    svc.client.destroy.assert_called_once_with(88)


def test_wait_and_invalid_actions(service):
    svc, plan, _ = service
    assert svc.wait(plan.plan_id, 1, sleep=lambda _: None).state == "planned"
    with pytest.raises(VastError):
        svc.wait(plan.plan_id, 0)
    with pytest.raises(VastError):
        svc.change(plan.plan_id, "invalid")
    with pytest.raises(VastError):
        svc.change(plan.plan_id, "stop")
    with pytest.raises(VastError):
        monitor(svc, plan.plan_id, 0)
    with pytest.raises(VastError):
        monitor(svc, plan.plan_id)


def test_billing_uses_parent_only_and_distinct_sources(service):
    svc, plan, _ = service
    record = svc.create(plan.plan_id)
    svc.client.charges.return_value = [
        {"source": "instance-88", "amount": "0.25", "items": [{"amount": "0.24"}]},
        {"source": "volume-1", "amount": "0.1"},
        {"source": "instance-88", "amount": None},
    ]
    result = costs(svc.client, plan, record, now() - timedelta(hours=1), now())
    assert result["provider_reported"]["usd"] == "0.25"
    assert result["provider_reported"]["unknown_amounts"] == 1
    assert result["unattributed_contracts"] == ["volume-1"]
    assert result["status"] == "provisional"
    svc.client.charges.return_value = []
    assert (
        costs(svc.client, plan, record, now() - timedelta(hours=1), now())["status"]
        == "pending"
    )
    window_start = now()
    window_end = now() - timedelta(seconds=1)
    with pytest.raises(VastError):
        costs(svc.client, plan, record, window_start, window_end)


def test_startup_is_deterministic(service):
    _, plan, _ = service
    expected = startup(plan.profile)
    restored = WorkloadProfile.model_validate_json(plan.profile.model_dump_json())
    assert startup(restored) == expected
    assert "docker run" not in startup(plan.profile)
    cfg = plan.profile.model_copy(
        update={"mode": "ollama", "model": "test", "download_gb": Decimal("25")}
    )
    script = startup(cfg)
    assert "ollama pull" not in script
    assert "awaiting_capacity_check" in script
    assert "ollama pull" in startup(cfg, download_model=True)
    assert "flock" in script
    assert "curl" in script
    assert "ollama pull" not in startup(
        cfg.model_copy(update={"download_gb": Decimal("0")})
    )


def test_ssh_validation_and_args(service):
    svc, plan, _ = service
    instance = svc.client.instance.return_value
    args = ssh_args(plan, instance)
    assert "StrictHostKeyChecking=yes" in args
    assert "ForwardAgent=no" in args
    assert "IdentityAgent=none" in args
    assert "StrictHostKeyChecking=accept-new" in ssh_args(plan, instance, True)
    for changed in (
        {"ssh_host": "-evil"},
        {"ssh_host": "bad;id"},
        {"ssh_port": 0},
        {"ssh_port": "bad"},
    ):
        with pytest.raises(VastError):
            ssh_args(plan, {**instance, **changed})


def test_inspection_facts_and_failed_startup(service):
    svc, plan, _ = service
    facts = {
        "schema_version": 1,
        "arch": "aarch64",
        "disk": {"free_bytes": 20_000_000_000},
        "startup_state": "ready",
    }
    with patch(
        "venom_core.services.vast_environments.ssh.subprocess.run",
        return_value=Mock(returncode=0, stdout=json.dumps(facts)),
    ):
        result = inspect(plan, svc.client.instance.return_value)
    assert result["capacity_status"] == "inconclusive"
    facts.update(arch="x86_64", startup_state="failed")
    with patch(
        "venom_core.services.vast_environments.ssh.subprocess.run",
        return_value=Mock(returncode=0, stdout=json.dumps(facts)),
    ):
        assert inspect(plan, svc.client.instance.return_value)["reasons"] == [
            "cpu_arch",
            "startup",
        ]
    with patch(
        "venom_core.services.vast_environments.ssh.subprocess.run",
        return_value=Mock(returncode=1),
    ):
        with pytest.raises(VastError):
            inspect(plan, svc.client.instance.return_value)


def test_workload_saves_and_uses_latest_record(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    with patch(
        "venom_core.services.vast_environments.operations.inspect",
        return_value={"ssh": "ready"},
    ):
        assert workload(svc, plan.plan_id, "inspect") == {"ssh": "ready"}
    assert svc.journal.record(plan.plan_id).ssh_state == "ready"
    with pytest.raises(VastError, match="vast.ollama_profile_required"):
        workload(svc, plan.plan_id, "ready")
    with patch(
        "venom_core.services.vast_environments.operations.subprocess.run",
        return_value=Mock(returncode=1),
    ):
        with pytest.raises(VastError, match="vast.provision_failed"):
            workload(svc, plan.plan_id, "provision")


def probe(profile, fail=False, digest="digest"):
    def respond(req):
        if req.url.path == "/api/version":
            return httpx.Response(200, json={"version": "fixture"})
        if req.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "test", "digest": digest, "size": 123}]}
            )
        body = json.loads(req.content)
        message = {"content": "steps"}
        if body.get("format"):
            message = {"content": '{"ok":true}'}
        if body["messages"][0].get("images"):
            message = {"content": "green yellow"}
        if body.get("tools"):
            message = {
                "content": "",
                "tool_calls": [{"function": {"name": "read_benchmark_sensor"}}],
            }
        row = {
            "done": True,
            "message": message,
            "eval_count": 10,
            "eval_duration": 100000000,
            "prompt_eval_count": 20,
            "prompt_eval_duration": 10000000,
        }
        if fail:
            row = {"error": "CUDA illegal memory access with private context"}
        return httpx.Response(200, content=json.dumps(row) + "\n")

    cfg = profile.model_copy(
        update={"mode": "ollama", "model": "test", "model_digest": "digest"}
    )
    return OllamaProbe(
        httpx.Client(
            base_url="http://127.0.0.1:1234", transport=httpx.MockTransport(respond)
        ),
        cfg,
    )


def test_ready_and_full_suite(service):
    _, plan, _ = service
    p = probe(plan.profile)
    assert p.ready()["runtime"] == "ready"
    p.profile.runtime.capabilities = ["json", "vision", "tools"]
    result = p.benchmark()
    assert result["status"] == "suitable"
    assert len(result["samples"]) == 12
    assert result["samples"][0]["output_characters"] == 5
    assert result["samples"][0]["characters_s"] > 0
    assert result["suite_version"].endswith("v4")
    assert compare([result, result])["comparable"]
    assert fixture_image().startswith("iVBOR")
    p.client.close()


def test_cuda_failure_and_digest_mismatch(service):
    _, plan, _ = service
    p = probe(plan.profile, fail=True)
    assert p.benchmark()["status"] == "unsuitable"
    with pytest.raises(VastError, match="vast.model_not_ready"):
        p.ready()
    p.client.close()
    p = probe(plan.profile, digest="other")
    with pytest.raises(VastError, match="vast.model_digest_mismatch"):
        p.metadata()
    with pytest.raises(VastError):
        p.benchmark(0)
    with pytest.raises(VastError):
        compare([])
    p.client.close()


def test_cli_account_and_error(service, capsys, tmp_path):
    svc, _, _ = service
    svc.client.account.return_value = {"credit": 9.52}
    assert (
        main(
            ["--state-dir", str(tmp_path), "--json", "account"],
            client_factory=lambda _: svc.client,
        )
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert out["result"]["credit"] == 9.52
    svc.client.account.side_effect = VastError("vast.http_error", 403)
    assert (
        main(
            ["--state-dir", str(tmp_path), "account"],
            client_factory=lambda _: svc.client,
        )
        == 1
    )
    out = capsys.readouterr().out
    assert "403" in out
    assert "vast.http_error" in out
    svc.client.close.assert_called()


def test_billing_unavailable_preserves_quote(service):
    svc, plan, _ = service
    record = svc.create(plan.plan_id)
    svc.client.charges.side_effect = VastError("vast.charges_unavailable_for_host", 200)
    result = costs(svc.client, plan, record, now() - timedelta(hours=1), now())
    assert result["status"] == "unavailable"
    assert result["quote"]["hourly_usd"] == "0.4"
    assert result["provider_reported"]["usd"] is None
    assert result["provider_reported"]["error"] == "vast.charges_unavailable_for_host"
    svc.client.charges.side_effect = VastError("vast.transport_error")
    window_start = now() - timedelta(hours=1)
    window_end = now()
    with pytest.raises(VastError):
        costs(svc.client, plan, record, window_start, window_end)


def test_synthetic_prompt_is_repeatable_across_profile_roundtrip(service):
    _, plan, _ = service
    first = probe(plan.profile)
    restored = WorkloadProfile.model_validate_json(plan.profile.model_dump_json())
    second = probe(restored)
    try:
        expected = first._payload("synthetic", 64)
        assert second._payload("synthetic", 64) == expected
        assert first._payload("other", 64) != expected
    finally:
        first.client.close()
        second.client.close()


@pytest.mark.parametrize(
    "version,tags",
    [
        ({}, {"models": []}),
        ({"version": ""}, {"models": []}),
        ([], {"models": []}),
        ({"version": "1.0"}, {}),
        ({"version": "1.0"}, {"models": [None]}),
        ({"version": "1.0"}, []),
    ],
)
def test_engine_only_readiness_rejects_malformed_api(service, version, tags):
    _, plan, _ = service

    def respond(req):
        assert req.method == "GET"
        return httpx.Response(
            200, json=version if req.url.path == "/api/version" else tags
        )

    with httpx.Client(
        base_url="http://127.0.0.1:1234", transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(VastError, match="vast.ollama_api_invalid"):
            OllamaProbe(client, plan.profile).engine_ready()


def test_engine_only_workload_ready_has_no_generation_or_gpu_probe(service):
    svc, plan, _ = service
    plan.profile.mode = "ollama"
    plan.startup_sha256 = digest(startup(plan.profile))
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    svc.create(plan.plan_id)
    requests = []

    def respond(req):
        requests.append((req.method, req.url.path))
        return httpx.Response(
            200,
            json={"version": "0.40.11"}
            if req.url.path == "/api/version"
            else {"models": []},
        )

    client = httpx.Client(
        base_url="http://127.0.0.1:1234", transport=httpx.MockTransport(respond)
    )
    with (
        patch(
            "venom_core.services.vast_environments.operations.inspect",
            return_value={"reasons": []},
        ),
        patch("venom_core.services.vast_environments.operations.tunnel") as tunnel,
        patch(
            "venom_core.services.vast_environments.operations.httpx.Client",
            return_value=client,
        ),
        patch("venom_core.services.vast_environments.operations._gpu_facts") as gpu,
    ):
        tunnel.return_value.__enter__.return_value = "http://127.0.0.1:1234"
        result = workload(svc, plan.plan_id, "ready")
    assert result["runtime"] == "ready"
    assert result["acceptance_scope"] == "engine_only"
    assert result["model_count"] == 0
    assert result["generation_tested"] is False
    assert requests == [("GET", "/api/version"), ("GET", "/api/tags")]
    gpu.assert_not_called()
    with pytest.raises(VastError, match="vast.model_digest_required"):
        workload(svc, plan.plan_id, "benchmark")


def test_reconcile_null_provider_status_stays_readable(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    svc.client.instance.return_value["actual_status"] = None
    assert svc.reconcile(plan.plan_id).state == "unknown"
    assert svc.journal.record(plan.plan_id).state == "unknown"


@pytest.mark.parametrize("reasons,unknown", [(["cpu_ram"], []), ([], ["cpu_cores"])])
def test_provision_blocks_download_on_insufficient_or_unknown_capacity(
    service, reasons, unknown
):
    from venom_core.services.vast_environments.operations import _provision

    _, plan, _ = service
    plan.profile.mode = "ollama"
    with (
        patch(
            "venom_core.services.vast_environments.operations.inspect",
            return_value={"reasons": reasons, "unknown": unknown, "facts": {}},
        ),
        patch("venom_core.services.vast_environments.operations.subprocess.run") as run,
    ):
        with pytest.raises(VastError, match="vast.capacity_mismatch"):
            _provision(plan, {}, False)
        run.assert_not_called()


def test_ollama_order_carries_context_and_parallelism(service):
    svc, plan, _ = service
    plan.profile.mode = "ollama"
    plan.profile.context_tokens = 8192
    plan.profile.max_parallel_requests = 1
    plan.startup_sha256 = digest(startup(plan.profile))
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    svc.create(plan.plan_id)
    body = svc.client.create.call_args.args[1]
    assert body["env"]["OLLAMA_CONTEXT_LENGTH"] == "8192"
    assert body["env"]["OLLAMA_NUM_PARALLEL"] == "1"
    assert body["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert "ollama pull" not in body["onstart"]


@pytest.mark.parametrize(
    "driver,engine,accepted",
    [
        ("535.146.02", "0.40.11", False),
        ("595.84", "0.19.0", False),
        ("595.84", "0.40.11", True),
        ("", "", False),
    ],
)
def test_real_versions_checked_before_download(service, driver, engine, accepted):
    from venom_core.services.vast_environments.operations import _check_ollama_capacity

    _, plan, _ = service
    plan.profile.runtime.min_driver = "550"
    plan.profile.runtime.min_engine_version = "0.40.11"
    capacity = {
        "reasons": [],
        "unknown": [],
        "facts": {
            "gpu": "RTX 3090, " + driver + ", 24576, 0",
            "ollama_version": "ollama version is " + engine,
        },
    }
    if accepted:
        _check_ollama_capacity(plan, capacity)
    else:
        with pytest.raises(VastError, match="vast.runtime_version_mismatch"):
            _check_ollama_capacity(plan, capacity)
