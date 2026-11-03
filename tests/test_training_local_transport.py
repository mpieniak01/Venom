"""Local RPC retains the remote lifecycle without SSH or GPU execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from venom_core.services.remote_training import cli
from venom_core.services.remote_training.bundles import create_bundle
from venom_core.services.remote_training.client import RemoteClient
from venom_core.services.remote_training.local_transport import (
    LocalConfig,
    LocalTransport,
)
from venom_core.services.remote_training.transport import TransportError


def config(tmp_path):
    return LocalConfig(tmp_path / "local jobs; literal", Path(sys.executable))


def test_request_uses_fixed_rpc_and_explicit_interpreter(tmp_path):
    calls = []

    def execute(argv, raw, timeout, limit):
        calls.append((argv, raw, timeout, limit))
        return 0, b'{"ok":true,"result":{"state":"ready"}}'

    transport = LocalTransport(config(tmp_path), executor=execute)
    assert transport.request("status", {"run_id": "test"}) == {"state": "ready"}
    argv, raw, timeout, limit = calls[0]
    assert argv[0] == str(Path(sys.executable).absolute())
    assert argv[1] == "-c"
    assert "remote_training.remote" in argv[2]
    assert argv[-3:] == ["--root", str(config(tmp_path).root), "status"]
    assert json.loads(raw) == {"run_id": "test"}
    assert timeout == 60
    assert limit == 2 * 1024 * 1024
    assert not any(arg == "ssh" for arg in argv)


@pytest.mark.parametrize("timeout", [0, 601, True])
def test_config_rejects_unbounded_timeout(tmp_path, timeout):
    local_config_1 = LocalConfig(tmp_path / "root", Path(sys.executable), timeout)
    with pytest.raises(ValueError, match="timeout_invalid"):
        local_config_1.validate()


def test_interpreter_is_not_an_arbitrary_command(tmp_path):
    local_config_2 = LocalConfig(tmp_path / "root", tmp_path / "run.sh")
    with pytest.raises(ValueError, match="python_path_invalid"):
        local_config_2.validate()


@pytest.mark.parametrize(
    "reply", [b"bad", b"[]", b'{"ok":1}', b'{"ok":true,"result":[]}']
)
def test_reply_validation(tmp_path, reply):
    transport = LocalTransport(config(tmp_path), executor=lambda *_: (0, reply))
    with pytest.raises(TransportError, match="local_training_reply_invalid"):
        transport.request("status", {})


def test_semantic_error_is_stable_and_not_retried(tmp_path):
    transport = LocalTransport(
        config(tmp_path),
        executor=lambda *_: (0, b'{"ok":false,"error":"remote_training_run_missing"}'),
    )
    with pytest.raises(TransportError, match="^remote_training_run_missing$") as caught:
        transport.request("status", {})
    assert caught.value.retryable is False
    transport.executor = lambda *_: (0, b'{"ok":false,"error":"token=private secret"}')
    with pytest.raises(TransportError, match="^local_training_operation_failed$"):
        transport.request("status", {})


def test_transport_failure_mapping(tmp_path):
    def fail(*_):
        raise TransportError("remote_ssh_timeout", retryable=True)

    transport = LocalTransport(config(tmp_path), executor=fail)
    with pytest.raises(TransportError, match="local_training_rpc_failed") as caught:
        transport.request("status", {})
    assert caught.value.retryable is True
    transport.executor = lambda *_: (1, b"private diagnostic")
    with pytest.raises(TransportError, match="local_training_rpc_failed"):
        transport.request("status", {})


def test_request_bounds_and_reply_limit(tmp_path, monkeypatch):
    import venom_core.services.remote_training.local_transport as local

    transport = LocalTransport(config(tmp_path), executor=lambda *_: (0, b"x" * 20))
    with pytest.raises(ValueError, match="action_invalid"):
        transport.request("shell", {})
    invalid_number_3 = float("nan")
    with pytest.raises(ValueError, match="request_invalid"):
        transport.request("status", {"x": invalid_number_3})
    with pytest.raises(ValueError, match="action_invalid"):
        transport.request("status", [])
    monkeypatch.setattr(local, "MAX_RPC_BYTES", 10)
    with pytest.raises(ValueError, match="request_too_large"):
        transport.request("status", {"long": "x" * 20})
    with pytest.raises(TransportError, match="reply_too_large"):
        transport.request("status", {})


def identity():
    return {
        "model": "ibm-granite/granite-4.2-3b",
        "revision": "a" * 40,
        **{
            key + "_sha256": "b" * 64
            for key in (
                "tokenizer",
                "template",
                "profile",
                "data",
                "code",
                "dependencies",
            )
        },
    }


def test_real_local_rpc_prepare_upload_and_status(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "input.json").write_text("{}")
    archive = tmp_path / "input.zip"
    manifest = create_bundle(
        source, ["input.json"], archive, run_id="cpu_only", identity=identity()
    )
    client = RemoteClient(LocalTransport(config(tmp_path)), chunk_bytes=1024)
    assert client.prepare(manifest)["run_id"] == "cpu_only"
    assert client.upload("cpu_only", archive)["ready"] is True
    assert client.status("cpu_only")["status"] == "prepared"
    assert client.attempt_history("cpu_only")["attempts"] == []


def local_args(tmp_path, action, *extra):
    return cli.parser().parse_args(
        [
            "--execution",
            "local",
            "--local-root",
            str(tmp_path / "host"),
            "--local-python",
            str(Path(sys.executable)),
            action,
            *extra,
        ]
    )


def test_cli_local_is_explicit_and_remote_remains_default(tmp_path, monkeypatch):
    assert cli.parser().parse_args(["status", "--run-id", "r"]).execution == "remote"
    parsed_args_4 = cli.parser().parse_args(["status", "--run-id", "r"])
    with pytest.raises(ValueError, match="ssh_alias_required"):
        cli.dispatch(parsed_args_4)
    parsed_args_5 = cli.parser().parse_args(
        ["--execution", "local", "status", "--run-id", "r"]
    )
    with pytest.raises(ValueError, match="root_and_interpreter"):
        cli.dispatch(parsed_args_5)
    args = local_args(tmp_path, "status", "--run-id", "r")
    seen = []
    monkeypatch.setattr(
        cli,
        "RemoteClient",
        lambda transport: SimpleNamespace(
            status=lambda run_id: seen.append(transport) or {"state": "ok"}
        ),
    )
    assert cli.dispatch(args) == {"state": "ok"}
    assert isinstance(seen[0], LocalTransport)
    args.host = "unexpected"
    with pytest.raises(ValueError, match="ssh_alias_not_allowed"):
        cli.dispatch(args)


@pytest.mark.parametrize(
    "action,extra",
    [
        ("start", []),
        ("resume", ["--checkpoint", "checkpoint"]),
        ("retry", ["--from-attempt", "1"]),
    ],
)
def test_local_start_requires_host_readiness(tmp_path, monkeypatch, action, extra):
    monkeypatch.setitem(
        sys.modules,
        "venom_core.services.remote_training.local_host",
        SimpleNamespace(readiness=lambda root: {"ready": False}),
    )
    parsed_args_6 = local_args(tmp_path, action, "--run-id", "run", *extra)
    with pytest.raises(ValueError, match="remote_training_local_host_not_ready"):
        cli.dispatch(parsed_args_6)


def test_local_host_check(tmp_path, monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "venom_core.services.remote_training.local_host",
        SimpleNamespace(readiness=lambda root: {"ready": False, "reason": "busy"}),
    )
    args = cli.parser().parse_args(
        ["--execution", "local", "--local-root", str(tmp_path / "host"), "host-check"]
    )
    assert cli.dispatch(args)["reason"] == "busy"
    parsed_args_7 = cli.parser().parse_args(["host-check"])
    with pytest.raises(ValueError, match="requires_local_root"):
        cli.dispatch(parsed_args_7)


def test_local_start_with_ready_host(tmp_path, monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "venom_core.services.remote_training.local_host",
        SimpleNamespace(readiness=lambda root: {"ready": True}),
    )
    monkeypatch.setattr(
        cli,
        "RemoteClient",
        lambda transport: SimpleNamespace(start=lambda *a, **k: {"started": True}),
    )
    assert cli.dispatch(local_args(tmp_path, "start", "--run-id", "run")) == {
        "started": True
    }


def test_local_host_init_returns_readiness(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "initialize", lambda *a, **k: {"configured": True})
    monkeypatch.setitem(
        sys.modules,
        "venom_core.services.remote_training.local_host",
        SimpleNamespace(readiness=lambda root: {"ready": False}),
    )
    args = local_args(
        tmp_path,
        "host-init",
        "--root",
        str(tmp_path / "root"),
        "--worker-python",
        sys.executable,
        "--snapshot",
        str(tmp_path / "snapshot"),
        "--admission-db",
        str(tmp_path / "admission.sqlite3"),
        "--code-root",
        str(tmp_path / "code"),
    )
    assert cli.dispatch(args) == {"configured": True, "readiness": {"ready": False}}
