"""Every terminal action delegates to the shared service."""

import json
from unittest.mock import patch

import pytest

from tests.test_vast_operations import service as source_service
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.services.vast_environments.cli import dispatch, main, parser


@pytest.fixture
def service(tmp_path):
    return source_service.__wrapped__(tmp_path)


@pytest.mark.parametrize(
    "command",
    [
        "account",
        "list",
        "volumes",
        "create",
        "status",
        "reconcile",
        "start",
        "stop",
        "destroy",
        "export",
        "cleanup",
        "wait",
        "monitor",
        "inspect",
        "provision",
        "ready",
        "benchmark",
        "costs",
    ],
)
def test_dispatch(command, service):
    svc, plan, _ = service
    if command not in {"account", "list", "volumes", "create"}:
        svc.create(plan.plan_id)
    svc.client.account.return_value = {"credit": 1}
    svc.client.instances.return_value = []
    svc.client.volumes.return_value = []
    svc.client.charges.return_value = []
    if command == "destroy":
        svc.export(plan.plan_id)
    if command in {"cleanup", "monitor"}:
        plan.finish_policy = "stop"
        plan.checksum = plan.calculate_checksum()
        svc.journal.save_plan(plan)
    argv = [command]
    if command not in {"account", "list", "volumes"}:
        argv += ["--plan", plan.plan_id]
    args = parser().parse_args(argv)
    with (
        patch(
            "venom_core.services.vast_environments.cli.workload",
            return_value={"probe": True},
        ),
        patch(
            "venom_core.services.vast_environments.cli.monitor",
            return_value={"monitor": True},
        ),
    ):
        result = dispatch(args, svc)
    assert result is not None


def test_cli_profiles_compare_and_env(service, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ENV_FILE", ".env.dev")
    svc, plan, _ = service
    profile = tmp_path / "profile.json"
    profile.write_text(plan.profile.model_dump_json())
    for cmd in ["offers", "assess"]:
        argv = [cmd, "--profile", str(profile)]
        if cmd == "assess":
            argv += ["--offer", "12"]
        assert dispatch(parser().parse_args(argv), svc)
    ssh = tmp_path / "ssh.json"
    ssh.write_text(
        json.dumps(
            {
                "identity_file": plan.ssh_identity_file,
                "known_hosts": plan.ssh_known_hosts,
            }
        )
    )
    args = parser().parse_args(
        [
            "plan",
            "--profile",
            str(profile),
            "--offer",
            "12",
            "--max-hourly",
            "1",
            "--max-total",
            "2",
            "--ssh-profile",
            str(ssh),
        ]
    )
    assert dispatch(args, svc)["plan_id"]
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"suite_version": "one", "profile": {}, "metadata": {}})
    )
    assert dispatch(parser().parse_args(["compare", str(report), str(report)]), svc)[
        "comparable"
    ]
    assert main(["--json", "compare", str(report), str(report)]) == 0
    capsys.readouterr()
    env = tmp_path / "local.env"
    env.write_text("VAST_API_KEY=synthetic-test-key\n")
    seen = []
    svc.client.account.return_value = {"credit": 1}

    def factory(key):
        seen.append(key.get_secret_value())
        return svc.client

    assert (
        main(
            [
                "--json",
                "--env-file",
                str(env),
                "--state-dir",
                str(tmp_path / "state"),
                "account",
            ],
            client_factory=factory,
        )
        == 0
    )
    assert seen == ["synthetic-test-key"]
    assert "synthetic-test-key" not in capsys.readouterr().out


def test_cli_validation(service, tmp_path, capsys):
    svc, plan, _ = service
    svc.client.offers.return_value = []
    profile = tmp_path / "profile.json"
    profile.write_text(plan.profile.model_dump_json())
    args = parser().parse_args(["assess", "--profile", str(profile), "--offer", "12"])
    with pytest.raises(VastError):
        dispatch(args, svc)
    args.command = "bad"
    with pytest.raises(VastError):
        dispatch(args, svc)
    assert (
        main(
            [
                "--json",
                "compare",
                str(tmp_path / "missing.json"),
                str(tmp_path / "missing.json"),
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["error"] == "vast.invalid_input"
