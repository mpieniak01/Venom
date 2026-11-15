"""Academy adoption of a prepared, explicitly dedicated Vast VM."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import (
    EnvironmentPlan,
    EnvironmentRecord,
    WorkloadProfile,
    now,
)
from venom_core.services.training_experiments import remote_text_vast as rental
from venom_core.services.vast_environments.assessment import quote
from venom_core.services.vast_environments.store import Journal

PLAN = "a" * 32
CAMPAIGN = "dialogue"
HOST = {
    "repo": "/workspace/venom",
    "python": "/workspace/venv/bin/python",
    "root": "/workspace/academy/experiments",
    "commit": "b" * 40,
    "sandbox_manifest": "/workspace/benchmarks/manifest.json",
}
SANDBOX = {
    "status": "PASS",
    "checks": {"writable": "PASS", "readonly": "PASS"},
    "gpu_used": False,
    "model_loaded": False,
}


class Provider:
    def __init__(self, instance):
        self.value = instance.copy()
        self.visible = self.value.copy()
        self.requests = []
        self.destroy_result = "gone"
        self.stopped_status = "stopped"
        self.storage = []

    def instance(self, instance_id):
        self.requests.append(("instance", instance_id))
        if self.value is None:
            raise VastError("vast.instance_not_found", status=404)
        return self.value.copy()

    def instances(self):
        return [self.visible] if self.visible else [{"id": 828, "label": "other"}]

    def volumes(self):
        return self.storage

    def destroy(self, instance_id):
        self.requests.append(("destroy", instance_id))
        if self.destroy_result == "timeout":
            raise VastError("vast.transport_error", ambiguous=True)
        self.value = None
        self.visible = None

    def set_state(self, instance_id, state):
        self.requests.append(("set_state", instance_id, state))
        actual_status = self.stopped_status if state == "stopped" else state
        self.value.update(actual_status=actual_status, intended_status=state)
        self.visible.update(self.value)

    def charges(self, start, end):
        assert end > start
        return [
            {"source": "instance-42", "amount": "0.03"},
            {"source": "instance-828", "amount": "3.5"},
        ]

    def close(self):
        pass


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "vast")
    profile = WorkloadProfile(
        cpu_arch="amd64",
        image="image@sha256:" + "a" * 64,
        name="text-training",
        vm_required=True,
        template_hash="known-template",
        template_configuration_sha256="b" * 64,
        duration_minutes=60,
        upload_gb=Decimal(1),
        download_gb=Decimal(2),
    )
    offer = {
        "host_id": 4,
        "machine_id": 5,
        "search": {"totalHour": "0.5", "diskHour": "0.1"},
        "internet_down_cost_per_tb": "20",
        "internet_up_cost_per_tb": "50",
    }
    key = tmp_path / "key"
    key.touch()
    plan = EnvironmentPlan(
        plan_id=PLAN,
        profile=profile,
        assessment={
            "status": "eligible",
            "offer": offer,
            "reasons": [],
            "unknown": [],
            "quote": quote(offer, profile),
        },
        expires_at=now() - timedelta(minutes=5),
        max_hourly_usd=Decimal(1),
        max_total_usd=Decimal(2),
        finish_policy="destroy",
        ssh_identity_file=str(key),
        ssh_known_hosts=str(tmp_path / "known_hosts"),
        ssh_fingerprint="fingerprint",
        startup_sha256="digest",
    )
    plan.checksum = plan.calculate_checksum()
    journal.save_plan(plan)
    instance = {
        "id": 42,
        "label": "venom-" + PLAN,
        "host_id": 4,
        "machine_id": 5,
        "actual_status": "running",
        "dph_total": "0.5",
        "public_ipaddr": "192.0.2.45",
        "ports": {"22/tcp": [{"HostPort": "12345", "HostIp": "0.0.0.0"}]},
    }
    record = EnvironmentRecord(
        plan_id=PLAN,
        state="running",
        instance_id=42,
        instance=instance,
        submitted_at=now() - timedelta(minutes=10),
    )
    journal.save_record(record)
    provider = Provider(instance)
    backend = rental.VastTextRental(journal, None, client_factory=lambda _: provider)

    def sandbox(prefix, host):
        assert "StrictHostKeyChecking=yes" in prefix
        assert "ForwardAgent=no" in prefix
        assert prefix[-1] == "root@192.0.2.45"
        assert host == HOST
        return SANDBOX

    monkeypatch.setattr(rental, "_qualify_over_ssh", sandbox)
    return backend, provider


def qualify(backend):
    return backend.qualify_prepared(PLAN, campaign_id=CAMPAIGN, **HOST)


def test_adopt_only_qualified_vm_and_validate_budget_offline(prepared):
    backend, provider = prepared
    with pytest.raises(VastError, match="qualification_required"):
        backend.validate(PLAN, 200, 500_000, campaign_id=CAMPAIGN)
    receipt = qualify(backend)
    request_count = len(provider.requests)
    assert qualify(backend) == receipt
    result = backend.validate(PLAN, 200, 500_000, campaign_id=CAMPAIGN)
    assert result["hourly_microusd"] == 500_000
    assert result["transfer_microusd"] == 90_000
    assert result["estimated_microusd"] >= 201_112
    assert result["max_upload_bytes"] == 1_000_000_000
    assert result["commit"] == HOST["commit"]
    assert result["cleanup_reserve_seconds"] == 180
    with pytest.raises(VastError, match="budget_exceeded"):
        backend.validate(PLAN, 200, 200_000, campaign_id=CAMPAIGN)
    with pytest.raises(VastError, match="duration_exceeds_plan"):
        backend.validate(PLAN, 3_001, 2_000_000, campaign_id=CAMPAIGN)
    with pytest.raises(VastError, match="duration_exceeds_plan"):
        backend.validate(PLAN, 100, 2_000_000, campaign_id=CAMPAIGN)
    with pytest.raises(VastError, match="campaign_mismatch"):
        backend.validate(PLAN, 200, 500_000, campaign_id="other")
    assert len(provider.requests) == request_count
    assert backend.acquire(PLAN, campaign_id=CAMPAIGN)["instance_id"] == 42
    assert backend.acquire(PLAN, campaign_id=CAMPAIGN)["root"] == HOST["root"]
    assert "StrictHostKeyChecking=yes" in backend.ssh_prefix(PLAN, campaign_id=CAMPAIGN)
    assert all(command == "instance" for command, _ in provider.requests)
    assert backend.cost(PLAN, campaign_id=CAMPAIGN)["billed_microusd"] == 30_000


def test_missing_qualification_never_adopts_a_fresh_offer(prepared):
    backend, provider = prepared
    backend.journal.save_record(EnvironmentRecord(plan_id=PLAN))
    with pytest.raises(VastError, match="prepared_instance_required"):
        qualify(backend)
    assert provider.requests == []


def test_rejects_budget_after_observed_price_increase(prepared):
    backend, provider = prepared
    qualify(backend)
    provider.value["dph_total"] = "0.51"
    with pytest.raises(VastError, match="price_unverified"):
        backend.acquire(PLAN, campaign_id=CAMPAIGN)


@pytest.mark.parametrize(
    "key,value", [("label", "other"), ("host_id", 2), ("machine_id", 9)]
)
def test_cleanup_never_targets_changed_instance(prepared, key, value):
    backend, provider = prepared
    qualify(backend)
    provider.value[key] = value
    result = backend.cleanup(PLAN, campaign_id=CAMPAIGN)
    assert result["state"] == "cleanup_pending"
    assert result["error"] == "vast.text_instance_mismatch"
    assert ("destroy", 42) not in provider.requests


def test_cleanup_is_confirmed_and_leaves_unrelated_resources(prepared):
    backend, provider = prepared
    qualify(backend)
    provider.storage = [{"id": 9, "host_id": 100}]
    assert backend.cleanup(PLAN, campaign_id=CAMPAIGN)["state"] == "destroyed"
    assert backend.cleanup(PLAN, campaign_id=CAMPAIGN)["state"] == "destroyed"
    assert provider.requests.count(("destroy", 42)) == 1
    assert provider.instances() == [{"id": 828, "label": "other"}]


@pytest.mark.parametrize("stopped_status", ["stopped", "exited"])
def test_stop_policy_retains_the_vm_for_a_new_campaign(prepared, stopped_status):
    backend, provider = prepared
    provider.stopped_status = stopped_status
    plan = backend.journal.plan(PLAN)
    plan.finish_policy = "stop"
    plan.checksum = plan.calculate_checksum()
    backend.journal.save_plan(plan)
    first = qualify(backend)
    assert backend.cleanup(PLAN, campaign_id=CAMPAIGN)["state"] == "stopped"
    assert backend.cleanup(PLAN, campaign_id=CAMPAIGN)["state"] == "stopped"
    assert provider.requests.count(("set_state", 42, "stopped")) == 1
    assert ("destroy", 42) not in provider.requests
    with backend._service() as environments:
        environments.change(PLAN, "start")
    second = backend.qualify_prepared(PLAN, campaign_id="second", **HOST)
    assert first["instance_id"] == second["instance_id"] == 42
    assert second["campaign_id"] == "second"
    assert (
        backend.validate(PLAN, 200, 500_000, campaign_id="second")["state"]
        == "prepared"
    )
    assert qualify(backend) == first
    with pytest.raises(VastError, match="vast.text_campaign_invalid"):
        backend.qualify_prepared(PLAN, campaign_id="bad/name", **HOST)


@pytest.mark.parametrize(
    ("finish_policy", "flag", "exit_code"),
    [
        ("destroy", "--authorize-destroy", 0),
        ("stop", "--authorize-stop", 0),
        ("destroy", "--authorize-stop", 1),
        ("stop", "--authorize-destroy", 1),
    ],
)
def test_qualification_cli_checks_finish_policy(
    prepared, monkeypatch, capsys, finish_policy, flag, exit_code
):
    backend, _ = prepared
    plan = backend.journal.plan(PLAN)
    plan.finish_policy = finish_policy
    plan.checksum = plan.calculate_checksum()
    backend.journal.save_plan(plan)
    monkeypatch.setattr(rental.VastTextRental, "from_settings", lambda: backend)
    arguments = ["remote_text_vast", PLAN, "--campaign-id", CAMPAIGN, flag]
    for key, value in HOST.items():
        arguments.extend(("--" + key.replace("_", "-"), value))
    monkeypatch.setattr("sys.argv", arguments)
    if exit_code:
        with pytest.raises(SystemExit) as caught:
            rental.main()
        assert caught.value.code == exit_code
        assert "vast.text_finish_policy_mismatch" in capsys.readouterr().err
    else:
        rental.main()
        assert '"instance_id": 42' in capsys.readouterr().out


def test_estimate_stops_on_first_confirmed_closure(prepared, monkeypatch):
    backend, _ = prepared
    qualify(backend)
    earliest = backend.cleanup(PLAN, campaign_id=CAMPAIGN)
    before = backend.cost(PLAN, campaign_id=CAMPAIGN)
    later = now() + timedelta(hours=1)
    monkeypatch.setattr(rental, "now", lambda: later)
    again = backend.cleanup(PLAN, campaign_id=CAMPAIGN)
    after = backend.cost(PLAN, campaign_id=CAMPAIGN)
    assert again["checked_at"] != earliest["checked_at"]
    assert again["closed_at"] == earliest["closed_at"]
    assert after["estimated_microusd"] == before["estimated_microusd"]


@pytest.mark.parametrize(
    ("policy", "method", "expected"),
    [("stop", "set_state", "stopped"), ("destroy", "destroy", "destroyed")],
)
def test_definitive_provider_rejection_allows_cleanup_retry(
    prepared, monkeypatch, policy, method, expected
):
    backend, provider = prepared
    plan = backend.journal.plan(PLAN)
    plan.finish_policy = policy
    plan.checksum = plan.calculate_checksum()
    backend.journal.save_plan(plan)
    qualify(backend)
    rejected = Mock(side_effect=VastError("vast.http_error", status=429))
    with monkeypatch.context() as patch:
        patch.setattr(provider, method, rejected)
        if policy == "stop":
            with pytest.raises(VastError, match="vast.http_error"):
                backend.cleanup(PLAN, campaign_id=CAMPAIGN)
            rejected.assert_called_once_with(42, "stopped")
        else:
            result = backend.cleanup(PLAN, campaign_id=CAMPAIGN)
            assert result["state"] == "cleanup_pending"
            assert result["error"] == "vast.http_error"
            rejected.assert_called_once_with(42)

    record = backend.journal.record(PLAN)
    assert record.state == policy + "_failed"
    assert record.pending_action is None
    assert backend.cleanup(PLAN, campaign_id=CAMPAIGN)["state"] == expected


def test_ambiguous_delete_reconciles_without_replaying(prepared):
    backend, provider = prepared
    qualify(backend)
    provider.destroy_result = "timeout"
    assert backend.cleanup(PLAN, campaign_id=CAMPAIGN)["state"] == "cleanup_pending"
    assert backend.cleanup(PLAN, campaign_id=CAMPAIGN)["state"] == "cleanup_pending"
    provider.value = None
    assert backend.cleanup(PLAN, campaign_id=CAMPAIGN)["state"] == "cleanup_pending"
    provider.visible = None
    assert backend.cleanup(PLAN, campaign_id=CAMPAIGN)["state"] == "destroyed"
    assert provider.requests.count(("destroy", 42)) == 1


def test_unattributed_storage_keeps_cleanup_pending(prepared):
    backend, provider = prepared
    qualify(backend)
    provider.storage = [{"id": 9, "host_id": 4}]
    result = backend.cleanup(PLAN, campaign_id=CAMPAIGN)
    assert result["state"] == "cleanup_pending"
    assert result["error"] == "vast.text_volume_cleanup_unverified"
    assert provider.requests.count(("destroy", 42)) == 1


def test_qualification_uses_pinned_interpreter_and_validates_both_modes(monkeypatch):
    import json
    import subprocess

    def run(argv, **kwargs):
        assert "git rev-parse HEAD" in argv[-1]
        assert "git status --porcelain" in argv[-1]
        assert HOST["python"] in argv[-1]
        assert HOST["sandbox_manifest"] in argv[-1]
        assert kwargs["timeout"] == 150
        value = dict(SANDBOX, checks={"writable": "PASS", "readonly": "FAIL"})
        return subprocess.CompletedProcess(argv, 0, json.dumps(value).encode())

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(VastError, match="sandbox_unqualified"):
        rental._qualify_over_ssh(["ssh", "host"], HOST)
