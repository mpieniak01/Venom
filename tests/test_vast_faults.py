"""Recovery, SSH cleanup and degraded workload paths."""

import json
from contextlib import contextmanager
from unittest.mock import Mock, patch

import httpx
import pytest

from tests.test_vast_operations import probe
from tests.test_vast_operations import service as source_service
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.services.vast_environments.operations import monitor, workload
from venom_core.services.vast_environments.ssh import inspect, tunnel


@pytest.fixture
def service(tmp_path):
    return source_service.__wrapped__(tmp_path)


def test_tunnel_closes_after_success_and_exception(service):
    svc, plan, _ = service
    process = Mock()
    process.poll.return_value = None
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    with (
        patch(
            "venom_core.services.vast_environments.ssh.subprocess.Popen",
            return_value=process,
        ),
        patch(
            "venom_core.services.vast_environments.ssh.socket.create_connection",
            return_value=connection,
        ),
    ):
        with tunnel(plan, svc.client.instance.return_value) as endpoint:
            assert endpoint.startswith("http://127.0.0.1:")
        with pytest.raises(ValueError):
            with tunnel(plan, svc.client.instance.return_value):
                raise ValueError("fixture")
    assert process.terminate.call_count == 2
    assert process.wait.call_count == 2


def test_tunnel_process_error_and_kill(service):
    import subprocess

    svc, plan, _ = service
    process = Mock()
    process.poll.return_value = 1
    process.wait.side_effect = [subprocess.TimeoutExpired("ssh", 5), 0]
    with patch(
        "venom_core.services.vast_environments.ssh.subprocess.Popen",
        return_value=process,
    ):
        with pytest.raises(VastError, match="vast.tunnel_failed"):
            with tunnel(plan, svc.client.instance.return_value):
                pass
    process.kill.assert_called_once()
    with patch(
        "venom_core.services.vast_environments.ssh.subprocess.Popen",
        side_effect=OSError,
    ):
        with pytest.raises(VastError, match="vast.ssh_failed"):
            with tunnel(plan, svc.client.instance.return_value):
                pass


def test_tunnel_timeout(service):
    svc, plan, _ = service
    process = Mock()
    process.poll.return_value = None
    with (
        patch(
            "venom_core.services.vast_environments.ssh.subprocess.Popen",
            return_value=process,
        ),
        patch(
            "venom_core.services.vast_environments.ssh.socket.create_connection",
            side_effect=OSError,
        ),
        patch(
            "venom_core.services.vast_environments.ssh.time.monotonic",
            side_effect=[0, 25],
        ),
    ):
        with pytest.raises(VastError, match="vast.tunnel_timeout"):
            with tunnel(plan, svc.client.instance.return_value):
                pass
    process.terminate.assert_called_once()


@pytest.mark.parametrize("output", ["bad json", "[]", '{"schema_version":2}'])
def test_inspect_bad_response(service, output):
    svc, plan, _ = service
    with patch(
        "venom_core.services.vast_environments.ssh.subprocess.run",
        return_value=Mock(returncode=0, stdout=output),
    ):
        with pytest.raises(VastError, match="vast.inspect_invalid"):
            inspect(plan, svc.client.instance.return_value)


def test_inspect_cgroup_and_disk(service):
    svc, plan, _ = service
    facts = {
        "schema_version": 1,
        "arch": "aarch64",
        "disk": {"free_bytes": 1},
        "memory": "MemTotal: 128000000 kB",
        "cpu_count": 20,
        "cgroup_memory_max": "1000000000",
        "cgroup_cpu_max": "100000 100000",
        "gpu": "GB10, 615.0, 1000, 100",
        "startup_state": "ready",
    }
    with patch(
        "venom_core.services.vast_environments.ssh.subprocess.run",
        return_value=Mock(returncode=0, stdout=json.dumps(facts)),
    ):
        result = inspect(plan, svc.client.instance.return_value)
    assert result["reasons"] == ["free_disk", "cpu_ram", "cpu_cores", "gpu_ram"]


def test_workload_records_error_and_success(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    plan.profile.mode = "ollama"
    plan.profile.model = "test"
    plan.profile.model_digest = "digest"
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)

    @contextmanager
    def fake_tunnel(*_):
        yield "http://127.0.0.1:1234"

    p = probe(plan.profile)
    with (
        patch(
            "venom_core.services.vast_environments.operations.inspect",
            return_value={"reasons": [], "unknown": [], "facts": {}},
        ),
        patch("venom_core.services.vast_environments.operations.tunnel", fake_tunnel),
        patch(
            "venom_core.services.vast_environments.operations.OllamaProbe",
            return_value=p,
        ),
    ):
        assert workload(svc, plan.plan_id, "ready")["runtime"] == "ready"
        assert workload(svc, plan.plan_id, "benchmark")["status"] == "suitable"
    with patch(
        "venom_core.services.vast_environments.operations.inspect",
        side_effect=VastError("vast.ssh_failed"),
    ):
        with pytest.raises(VastError):
            workload(svc, plan.plan_id, "ready")
    rec = svc.journal.record(plan.plan_id)
    assert rec.runtime_state == "error" and rec.ssh_state == "unknown"
    assert rec.reports["ready"]["status"] == "error"
    with patch(
        "venom_core.services.vast_environments.operations.subprocess.run",
        return_value=Mock(returncode=0),
    ):
        assert workload(svc, plan.plan_id, "provision")["startup"] == "completed"
    with pytest.raises(VastError):
        workload(svc, plan.plan_id, "invalid")
    p.client.close()


def test_incomplete_and_missing_model(service):
    _, plan, _ = service
    cfg = plan.profile.model_copy(update={"model": "missing"})
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"models": []})
    )
    from venom_core.services.vast_environments.evaluation import OllamaProbe

    p = OllamaProbe(httpx.Client(base_url="http://127.0.0.1", transport=transport), cfg)
    with pytest.raises(VastError, match="vast.model_missing"):
        p.metadata()
    p.client.close()
    p = probe(plan.profile)
    with patch(
        "venom_core.services.vast_environments.evaluation.time.monotonic",
        side_effect=[0] + [10000] * 20,
    ):
        assert p.benchmark(1)["status"] == "inconclusive"
    p.client.close()


def test_monitor_timeout_and_destroyed(service):
    svc, plan, _ = service
    svc.create(plan.plan_id)
    plan.finish_policy = "stop"
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    with patch(
        "venom_core.services.vast_environments.operations.time.monotonic",
        side_effect=[0, 1000],
    ):
        assert (
            monitor(svc, plan.plan_id, 1)["monitor"]
            == "ended_resources_may_still_be_billed"
        )
    svc.reconcile = Mock(return_value=Mock(state="destroyed"))
    assert monitor(svc, plan.plan_id)["state"] == "destroyed"


def test_billing_window_does_not_include_previous_day(service):
    from datetime import timedelta
    from decimal import Decimal

    from venom_core.infrastructure.providers.vast.models import now
    from venom_core.services.vast_environments.billing import costs

    svc, plan, _ = service
    rec = svc.create(plan.plan_id)
    fixed = now()
    rec.submitted_at = fixed - timedelta(days=1)
    svc.client.charges.return_value = []
    with patch("venom_core.services.vast_environments.billing.now", return_value=fixed):
        result = costs(svc.client, plan, rec, fixed - timedelta(hours=1), fixed)
    assert Decimal(result["estimate"]["usd"]) == Decimal("0.4")


def test_recovery_needs_both_host_identifiers(service):
    svc, plan, _ = service
    rec = svc.journal.record(plan.plan_id)
    svc._event(rec, "submitting")
    svc.client.instances.return_value = [{"id": 88, "label": "venom-" + plan.plan_id}]
    assert svc.reconcile(plan.plan_id).state == "outcome_unknown"
    assert svc.journal.record(plan.plan_id).instance_id is None
    svc.client.instances.return_value[0].update(host_id=3, machine_id=4)
    assert svc.reconcile(plan.plan_id).instance_id == 88
    svc.client.create.assert_not_called()


def test_monitor_preserves_finish_policy_on_transient_read(service):
    from datetime import timedelta

    from venom_core.infrastructure.providers.vast.models import now

    svc, plan, _ = service
    rec = svc.create(plan.plan_id)
    plan.finish_policy = "stop"
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    rec.submitted_at = now() - timedelta(hours=1)
    svc.journal.save_record(rec)
    svc.reconcile = Mock(side_effect=VastError("vast.transport_error"))
    assert monitor(svc, plan.plan_id)["state"] == "stop_requested"
    svc.client.set_state.assert_called_once_with(88, "stopped")
    svc.reconcile = Mock(side_effect=VastError("vast.http_error", 403))
    with pytest.raises(VastError):
        monitor(svc, plan.plan_id)


def test_streaming_tools_before_final_chunk(service):
    from venom_core.services.vast_environments.evaluation import OllamaProbe

    _, plan, _ = service
    cfg = plan.profile.model_copy(
        update={"model": "fixture", "model_digest": "fixture"}
    )
    rows = [
        {
            "done": False,
            "message": {
                "tool_calls": [{"function": {"name": "read_benchmark_sensor"}}]
            },
        },
        {"done": True, "message": {}},
    ]
    with httpx.Client(
        base_url="http://127.0.0.1",
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, content="\n".join(json.dumps(row) for row in rows) + "\n"
            )
        ),
    ) as client:
        assert OllamaProbe(client, cfg).sample("tools", {})["correct"] is True


def test_cli_profile_validation_and_late_cost_window(service, tmp_path):
    from datetime import timedelta

    from venom_core.infrastructure.providers.vast.models import now
    from venom_core.services.vast_environments.cli import dispatch, parser, ssh_profile

    svc, plan, _ = service
    config = tmp_path / "ssh.json"
    for content in ["not json", "[]", "{}", '{"identity_file":"", "known_hosts":1}']:
        config.write_text(content)
        with pytest.raises(VastError, match="invalid_ssh_profile"):
            ssh_profile(config)
    config.write_text('{"identity_file":"id","known_hosts":"hosts"}')
    assert ssh_profile(config)["identity_file"] == "id"
    with pytest.raises(SystemExit):
        parser().parse_args(
            ["costs", "--plan", plan.plan_id, "--from-utc", "2026-10-16T12:00:00"]
        )
    args = parser().parse_args(["costs", "--plan", plan.plan_id])
    assert args.from_utc is None and args.to_utc is None
    fixed = now()
    with (
        patch("venom_core.services.vast_environments.cli.now", return_value=fixed),
        patch(
            "venom_core.services.vast_environments.cli.costs",
            return_value={"status": "fixture"},
        ) as called,
    ):
        assert dispatch(args, svc)["status"] == "fixture"
    assert called.call_args.args[-2:] == (fixed - timedelta(days=7), fixed)
