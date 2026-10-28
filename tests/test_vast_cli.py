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
    ssh_root = tmp_path / "secrets" / "ssh"
    ssh_root.mkdir(parents=True)
    monkeypatch.setattr(
        "venom_core.services.vast_environments.cli.SSH_PROFILE_ROOT", ssh_root
    )
    ssh = ssh_root / "ssh.json"
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


@pytest.mark.parametrize(
    "document", [[], None, "text", 1, {"result": []}, {"result": None}]
)
def test_compare_rejects_non_object_reports(document, tmp_path, capsys):
    report = tmp_path / "bad.json"
    report.write_text(json.dumps(document))
    assert main(["--json", "compare", str(report)]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "error": "vast.invalid_input",
    }


def test_ssh_profile_stays_in_secret_store(tmp_path, monkeypatch):
    from pathlib import Path

    from venom_core.services.vast_environments import cli

    root = tmp_path / "secrets" / "ssh"
    root.mkdir(parents=True)
    monkeypatch.setattr(cli, "SSH_PROFILE_ROOT", root)
    monkeypatch.chdir(tmp_path)
    profile = root / "connection.json"
    content = json.dumps(
        {"identity_file": "/existing/key", "known_hosts": "/existing/hosts"}
    )
    profile.write_text(content)
    assert cli.ssh_profile(profile)["identity_file"] == "/existing/key"
    assert (
        cli.ssh_profile(Path("secrets/ssh/connection.json"))["known_hosts"]
        == "/existing/hosts"
    )
    outside = tmp_path / "outside.json"
    outside.write_text(content)
    (root / "link.json").symlink_to(outside)
    (root / "folder").symlink_to(tmp_path, target_is_directory=True)
    invalid_suffix = root / "profile.txt"
    invalid_suffix.write_text(content)
    for path in [
        outside,
        root / ".." / ".." / "outside.json",
        root / "link.json",
        root / "folder" / "outside.json",
        invalid_suffix,
        root,
        root / "missing.json",
    ]:
        with patch.object(
            Path, "read_text", side_effect=AssertionError("must not read")
        ):
            with pytest.raises(VastError, match="invalid_ssh_profile"):
                cli.ssh_profile(path)


def test_cli_json_reads_use_utf8(tmp_path, monkeypatch, capsys):
    from pathlib import Path

    from venom_core.services.vast_environments import cli

    root = tmp_path / "ssh"
    root.mkdir()
    monkeypatch.setattr(cli, "SSH_PROFILE_ROOT", root)
    profile = root / "connection.json"
    identity = "/shared/klucz-łódź"
    profile.write_text(
        json.dumps(
            {"identity_file": identity, "known_hosts": "/shared/hosts"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {"suite_version": "próba", "profile": {}, "metadata": {}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    original = Path.read_text
    reads = []

    def utf8_read(path, *args, **kwargs):
        assert kwargs.get("encoding") == "utf-8"
        reads.append(path)
        return original(path, *args, **kwargs)

    with patch.object(Path, "read_text", utf8_read):
        assert cli.ssh_profile(profile)["identity_file"] == identity
        assert main(["compare", str(report), str(report)]) == 0
    assert profile in reads
    assert report in reads
    assert json.loads(capsys.readouterr().out.split("\n", 1)[1])["result"]["comparable"]


def test_offer_table_price_filter_and_ties():
    from scripts.cloud.vast.offers_table import select

    def row(identifier, price, status="eligible"):
        return {
            "offer": {"id": identifier},
            "quote": {"hourly_usd": price},
            "status": status,
        }

    rows = [
        row(5, "10"),
        row(3, "2"),
        row(1, "2"),
        row(2, "0.1", "ineligible"),
        row(4, None),
        row(6, "0.2", "unknown"),
        row(7, "NaN"),
    ]
    selected, count = select(rows, 2)
    assert [entry["offer"]["id"] for entry in selected] == [1, 3]
    assert count == 3


def test_offer_table_readonly_and_render(service, tmp_path, capsys):
    from scripts.cloud.vast import offers_table

    svc, plan, _ = service
    assessment = svc.search(plan.profile)[0].model_dump(mode="json")
    assessment["offer"].update(
        cpu_name="Xeon | test\nCPU", cpu_ram=64000, total_flops=35.58
    )
    assessment["runtime"]["memory_allocation"]["baseline_ram_mb"] = "32000"
    payload = {"ok": True, "result": [assessment]}

    # Assert only the offers action is dispatched; never lifecycle operations.
    with patch.object(offers_table, "vast_main") as cli:
        cli.side_effect = lambda argv: (print(json.dumps(payload)) or 0)
        assert offers_table.main(["--profile", str(tmp_path / "profile.json")]) == 0
        argv = cli.call_args.args[0]
        assert argv[5:] == [
            "offers",
            "--profile",
            str(tmp_path / "profile.json"),
            "--sort",
            "price",
            "--no-country-preference",
            "--any-gpu",
        ]
    output = capsys.readouterr().out
    assert "64000" in output and "32000" in output
    assert "FLOPS [TFLOPS]" in output and "| 36 |" in output
    assert "Xeon / test CPU" in output
    for locale in ("pl", "en", "de"):
        assert offers_table.TEXT[locale]["empty"] in offers_table.render([], 0, locale)

    with patch.object(offers_table, "vast_main") as cli:
        cli.side_effect = lambda argv: (
            print('{"ok": false, "error": "vast.http_error"}') or 1
        )
        assert offers_table.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["ok"] is False


def test_offer_table_any_gpu_preserves_other_requirements(service, tmp_path):
    from venom_core.services.vast_environments.assessment import search_filters
    from venom_core.services.vast_environments.cli import workload_profile

    _, plan, _ = service
    profile = plan.profile.model_copy(update={"gpu_names": ["RTX 3090"]})
    path = tmp_path / "profile.json"
    path.write_text(profile.model_dump_json(), encoding="utf-8")
    args = parser().parse_args(["offers", "--profile", str(path), "--any-gpu"])
    result = workload_profile(args)
    assert result.gpu_names == []
    assert "gpu_name" not in search_filters(result)
    expected = profile.model_dump()
    expected["gpu_names"] = []
    assert result.model_dump() == expected
    assert json.loads(path.read_text(encoding="utf-8"))["gpu_names"] == ["RTX 3090"]
