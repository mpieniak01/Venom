"""SSH isolation, lost-ack retries and verified/resumable artifact transport."""

import base64
import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from venom_core.services.remote_training.bundles import create_bundle
from venom_core.services.remote_training.client import RemoteClient
from venom_core.services.remote_training.transport import (
    MAX_RPC_BYTES,
    SSHConfig,
    SSHTransport,
    TransportError,
    execute_ssh,
)
from venom_core.services.training_experiments import remote_text_host


def identity():
    return {
        "model": "ibm-granite/granite-4.2-3b",
        "revision": "a" * 40,
        **{
            name + "_sha256": "b" * 64
            for name in (
                "tokenizer",
                "template",
                "profile",
                "data",
                "code",
                "dependencies",
            )
        },
    }


def archive(tmp_path, *, kind="input"):
    source = tmp_path / (kind + "-source")
    source.mkdir(exist_ok=True)
    (source / "data.jsonl").write_text('{"messages": [], "tools": []}\n')
    bundle = tmp_path / (kind + ".zip")
    manifest = create_bundle(
        source, ["data.jsonl"], bundle, run_id="run_1", identity=identity(), kind=kind
    )
    return bundle, manifest


class FakeHost:
    def __init__(self, result=b"", *, fail_ack=False, interrupt=False):
        self.result = result
        self.received = bytearray()
        self.actions = []
        self.fail_ack = fail_ack
        self.interrupt = interrupt

    def request(self, action, payload):
        self.actions.append((action, payload.copy()))
        if action == "upload":
            data = base64.b64decode(payload["data_b64"])
            offset = payload["offset"]
            if offset < len(self.received):
                assert self.received[offset : offset + len(data)] == data
            else:
                assert offset == len(self.received)
                self.received.extend(data)
            if self.fail_ack:
                self.fail_ack = False
                raise TransportError("remote_ssh_failed", retryable=True)
            return {"offset": offset + len(data)}
        if action == "collect":
            offset = payload["offset"]
            if self.interrupt and offset > 0:
                raise TransportError("remote_ssh_failed", retryable=True)
            data = self.result[offset : offset + payload["max_bytes"]]
            return {
                "data_b64": base64.b64encode(data).decode(),
                "total_bytes": len(self.result),
                "sha256": hashlib.sha256(self.result).hexdigest(),
                "eof": offset + len(data) == len(self.result),
            }
        return {"state": action}


def _text_host(
    executor=None,
    *,
    python="/workspace/venom/.venv/bin/python",
    repo="/workspace/venom; false",
    **limits,
):
    options = {} if executor is None else {"executor": executor}
    return remote_text_host.RemoteTextHost(
        ["ssh", "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes", "root@host"],
        python,
        repo,
        "/workspace/campaigns",
        **options,
        **limits,
    )


def test_text_host_uses_qualified_rpc_python_and_requested_timeout():
    python = "/workspace/data/remote-training/rpc-python"

    def executor(argv, raw, timeout, limit):
        parts = shlex.split(argv[-1])
        assert parts[4:6] == ["env", "RUNTIME_ADMISSION_ENABLED=true"]
        assert parts[6].startswith("VENOM_OPTUNA_PYTHON=")
        assert parts[7] == python
        assert timeout == 15 and limit == MAX_RPC_BYTES
        assert json.loads(raw) == {"campaign_id": "text"}
        return 0, b'{"ok":true,"result":{"status":"running"}}'

    host = _text_host(executor, python=python, request_timeout=15)
    assert host.status("text") == {"status": "running"}


@pytest.mark.parametrize("seconds", [0, 61, True, 1.5])
def test_text_host_caps_request_timeout(seconds):
    with pytest.raises(ValueError, match="remote_text_request_timeout_invalid"):
        _text_host(request_timeout=seconds)


def test_text_host_verifies_pinned_checkout_before_running_rpc(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    tracked = tmp_path / "tracked"
    tracked.write_text("expected")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.email=fixture@example.test",
            "-c",
            "user.name=Fixture",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    commit = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    python = tmp_path / "rpc-python"
    python.write_text('#!/bin/sh\nprintf \'{"ok":true,"result":{}}\'\n')
    python.chmod(0o700)

    def executor(argv, raw, timeout, limit):
        return execute_ssh(["sh", "-c", argv[-1]], raw, timeout, limit)

    kwargs = {"python": str(python), "repo": str(tmp_path)}
    clean = _text_host(executor, expected_commit=commit, **kwargs)
    assert clean.status("text") == {}
    with pytest.raises(TransportError, match="remote_ssh_failed"):
        _text_host(executor, expected_commit="0" * 40, **kwargs).status("text")
    tracked.write_text("different")
    with pytest.raises(TransportError, match="remote_ssh_failed"):
        clean.status("text")
    with pytest.raises(ValueError, match="remote_text_commit_invalid"):
        _text_host(executor, expected_commit="$(false)", **kwargs)


def _text_spec(review_mode="automatic"):
    return {
        "review_mode": review_mode,
        "campaign_id": "text",
        "profile_id": "pl_chat",
        "variants": [{}],
        "budget": {
            "max_trials": 1,
            "max_updates": 8,
            "max_tokens": 8192,
            "max_seconds": 3600,
            "trial_seconds": 120,
            "max_retries": 0,
            "max_artifact_bytes": 1000,
            "min_free_bytes": 0,
        },
    }


def test_text_host_round_trip_retry_sends_same_plan_and_cutoff(monkeypatch, tmp_path):
    calls = []
    sha = "a" * 64
    profile = "b" * 64
    cutoff = 1769000000.25

    class Campaign:
        def __init__(self, experiments):
            self.experiments = experiments

        def plan(self, spec):
            assert spec.review_mode == "automatic" and spec.profile_id == "pl_chat"
            calls.append("plan")
            return {"plan": {"plan_sha256": sha}}

        def start(self, campaign_id, plan_sha256, *, cutoff_at):
            assert (campaign_id, plan_sha256, cutoff_at) == ("text", sha, cutoff)
            calls.append("start")
            return self.status(campaign_id)

        def status(self, campaign_id):
            assert campaign_id == "text"
            return {"status": "running", "cutoff_at": cutoff}

        def resume(self, campaign_id):
            calls.append("resume")
            return self.status(campaign_id)

        def stop(self, campaign_id):
            calls.append("stop")
            return {**self.status(campaign_id), "status": "stopping"}

    monkeypatch.setattr(remote_text_host, "CampaignService", Campaign)
    monkeypatch.setattr(remote_text_host, "load_profile", lambda *args: (None, profile))
    lost = {"start"}

    def executor(argv, raw, timeout, limit):
        assert "-T" in argv and argv[-2] == "root@host"
        command = shlex.split(argv[-1])
        assert command[:4] == ["cd", "/workspace/venom; false", "&&", "exec"]
        assert limit == MAX_RPC_BYTES and timeout == 60
        output = io.BytesIO()
        action = command[-1]
        code = remote_text_host.serve(tmp_path, action, raw, output)
        if action in lost:
            lost.remove(action)
            return 255, b""
        return code, output.getvalue()

    host = _text_host(executor)
    assert (
        host.plan(_text_spec(), expected_profile_identity=profile)["plan"][
            "plan_sha256"
        ]
        == sha
    )
    with pytest.raises(TransportError, match="remote_ssh_failed"):
        host.start("text", sha, cutoff_at=cutoff)
    assert host.start("text", sha, cutoff_at=cutoff)["status"] == "running"
    assert host.status("text")["cutoff_at"] == cutoff
    assert host.resume("text")["status"] == "running"
    assert host.stop("text")["status"] == "stopping"
    assert calls == ["plan", "start", "start", "resume", "stop"]
    with pytest.raises(TransportError, match="remote_text_profile_changed"):
        host.plan(_text_spec(), expected_profile_identity="c" * 64)
    with pytest.raises(TransportError, match="remote_text_automatic_review_required"):
        host.plan(_text_spec("manual"))
    with pytest.raises(TransportError, match="remote_text_cutoff_required"):
        host.start("text", sha)


@pytest.mark.parametrize(
    ("action", "payload", "error"),
    [
        ("status", {"campaign_id": "unknown"}, "remote_text_not_found"),
        ("status", {"campaign_id": "../unsafe"}, "remote_text_operation_failed"),
        ("stop", {"campaign_id": "text", "exec": "private"}, "remote_text_rpc_invalid"),
        ("other", {}, "remote_text_rpc_invalid"),
    ],
)
def test_text_rpc_rejects_invalid_or_missing_campaigns(
    tmp_path, action, payload, error
):
    stream = io.BytesIO()
    assert (
        remote_text_host.serve(tmp_path, action, json.dumps(payload).encode(), stream)
        == 0
    )
    assert json.loads(stream.getvalue()) == {"ok": False, "error": error}


def test_text_rpc_requires_existing_remote_ownership_for_resume_and_stop(
    monkeypatch, tmp_path
):
    class Campaign:
        def __init__(self, experiments):
            pass

        def status(self, campaign_id):
            return {"status": "running", "started_at": 1}

    monkeypatch.setattr(remote_text_host, "CampaignService", Campaign)
    for action in ("resume", "stop"):
        stream = io.BytesIO()
        assert (
            remote_text_host.serve(tmp_path, action, b'{"campaign_id":"text"}', stream)
            == 0
        )
        assert (
            json.loads(stream.getvalue())["error"] == "remote_text_campaign_not_started"
        )


def test_text_artifact_is_published_only_after_bounded_success(tmp_path):
    contents = b"fake tar result"
    destination = tmp_path / "text.tar"
    calls = []

    def transfer(argv, raw, timeout, limit, *, sink):
        calls.append((timeout, limit))
        assert argv[-1].endswith(" fetch")
        assert json.loads(raw) == {"campaign_id": "text", "run_id": "text-01"}
        sink.write(contents)
        return (1 if len(calls) == 1 else 0), b""

    host = _text_host(transfer)
    with pytest.raises(TransportError, match="remote_text_fetch_failed"):
        host.fetch("text", "text-01", destination, 100, timeout=7)
    assert not list(tmp_path.iterdir())
    assert host.fetch("text", "text-01", destination, 100, timeout=7) == {
        "sha256": hashlib.sha256(contents).hexdigest(),
        "size": len(contents),
    }
    assert destination.read_bytes() == contents
    with pytest.raises(FileExistsError):
        host.fetch("text", "text-01", destination, 100, timeout=7)
    assert destination.read_bytes() == contents
    assert calls == [(7, 100)] * 3


def test_bounded_executor_streams_to_sink_without_returning_contents():
    command = [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x' * 4096)"]
    sink = io.BytesIO()
    assert execute_ssh(command, b"", 5, 4096, sink=sink) == (0, b"")
    assert sink.getvalue() == b"x" * 4096
    with pytest.raises(TransportError, match="remote_reply_too_large"):
        execute_ssh(command, b"", 5, 2048, sink=io.BytesIO())


def test_transport_quotes_remote_paths_and_does_not_expose_payload(tmp_path):
    config = tmp_path / "ssh-config"
    config.write_text("Host test\n")
    called = []

    def executor(argv, data, timeout, limit):
        called.append((argv, data, timeout, limit))
        return 0, b'{"ok":true,"result":{"state":"ready"}}'

    root = "/workspace/jobs; printf unsafe"
    transport = SSHTransport(
        SSHConfig(config, "training-host", root), executor=executor
    )
    assert transport.request("status", {"run_id": "run_1"}) == {"state": "ready"}
    argv, data, timeout, limit = called[0]
    assert "StrictHostKeyChecking=yes" in argv
    assert "BatchMode=yes" in argv
    assert argv[-2] == "training-host"
    assert shlex.split(argv[-1]) == [
        "python3",
        "-m",
        "venom_core.services.remote_training.remote",
        "--root",
        root,
        "status",
    ]
    assert json.loads(data) == {"run_id": "run_1"}
    assert timeout == 60 and limit == MAX_RPC_BYTES


@pytest.mark.parametrize("alias", ["-oProxyCommand=id", "x y", "x;id", "x\nHost other"])
def test_ssh_alias_option_injection_is_rejected(tmp_path, alias):
    config = tmp_path / "config"
    config.touch()
    with pytest.raises(ValueError, match="alias_invalid"):
        SSHTransport(SSHConfig(config, alias, "/workspace/jobs"))


@pytest.mark.parametrize(
    "root",
    ["/", "/workspace", "relative/path", "/workspace/../home", "/workspace/a\nrm"],
)
def test_ssh_root_boundaries_are_explicit(tmp_path, root):
    config = tmp_path / "config"
    config.touch()
    with pytest.raises(ValueError, match="root_invalid"):
        SSHTransport(SSHConfig(config, "host", root))


@pytest.mark.parametrize(
    "reply", [b"not-json", b"[]", b'{"ok":1}', b'{"ok":true,"result":[]}']
)
def test_invalid_rpc_replies_do_not_become_success(tmp_path, reply):
    config = tmp_path / "config"
    config.touch()
    transport = SSHTransport(
        SSHConfig(config, "host", "/workspace/jobs"), executor=lambda *_: (0, reply)
    )
    with pytest.raises(TransportError, match="remote_reply_invalid"):
        transport.request("status", {})


def test_remote_diagnostics_are_not_disclosed(tmp_path):
    config = tmp_path / "config"
    config.touch()
    response = b'{"ok":false,"error":"password=private-sensitive-data"}'
    transport = SSHTransport(
        SSHConfig(config, "host", "/workspace/jobs"), executor=lambda *_: (0, response)
    )
    with pytest.raises(TransportError, match="^remote_operation_failed$"):
        transport.request("status", {})
    with pytest.raises(ValueError, match="remote_action_invalid"):
        transport.request("destroy", {})
    with pytest.raises(ValueError, match="remote_request_too_large"):
        transport.request("prepare", {"manifest": "x" * MAX_RPC_BYTES})


def test_real_executor_bounds_reply_timeout_and_stderr():
    code, reply = execute_ssh(
        [sys.executable, "-c", "import sys;sys.stderr.write('private');print('ok')"],
        b"{}",
        5,
        1024,
    )
    assert code == 0 and reply == b"ok\n"
    with pytest.raises(TransportError, match="remote_reply_too_large"):
        execute_ssh([sys.executable, "-c", "print('x'*2048)"], b"{}", 5, 1024)
    with pytest.raises(TransportError, match="remote_ssh_timeout"):
        execute_ssh(
            [sys.executable, "-c", "import time;time.sleep(10)"], b"{}", 1, 1024
        )


def test_upload_retry_after_lost_ack_never_duplicates_bytes(tmp_path):
    bundle, manifest = archive(tmp_path)
    host = FakeHost(fail_ack=True)
    client = RemoteClient(host, chunk_bytes=128)
    assert client.prepare(manifest)["state"] == "prepare"
    result = client.upload("run_1", bundle)
    assert result["offset"] == bundle.stat().st_size
    assert bytes(host.received) == bundle.read_bytes()
    uploads = [payload for action, payload in host.actions if action == "upload"]
    assert uploads[0] == uploads[1]
    assert uploads[-1]["final"] is True


def test_collect_resumes_partial_transfer_and_keeps_completed_result(tmp_path):
    bundle, _ = archive(tmp_path, kind="result")
    host = FakeHost(bundle.read_bytes(), interrupt=True)
    client = RemoteClient(host, chunk_bytes=128, attempts=1)
    destination = tmp_path / "download" / "result.zip"
    with pytest.raises(TransportError, match="remote_ssh_failed"):
        client.collect("run_1", destination)
    assert not destination.exists()
    partial = destination.with_name(destination.name + ".part")
    assert partial.stat().st_size == 128
    host.interrupt = False
    start = len(host.actions)
    receipt = client.collect("run_1", destination)
    assert receipt["manifest"]["run_id"] == "run_1"
    assert destination.read_bytes() == bundle.read_bytes()
    offsets = [
        payload["offset"]
        for action, payload in host.actions[start:]
        if action == "collect"
    ]
    assert offsets[:2] == [0, 128]
    assert not partial.exists()
    client.collect("run_1", destination)
    assert destination.read_bytes() == bundle.read_bytes()


def test_collect_detects_corrupt_bytes_before_publication(tmp_path):
    bundle, _ = archive(tmp_path, kind="result")

    class CorruptHost(FakeHost):
        def request(self, action, payload):
            result = super().request(action, payload)
            data = bytearray(base64.b64decode(result["data_b64"]))
            if payload["offset"] == 0:
                data[0] ^= 1
            result["data_b64"] = base64.b64encode(data).decode()
            return result

    destination = tmp_path / "downloaded-result.zip"
    with pytest.raises(ValueError, match="remote_collect_hash_mismatch"):
        RemoteClient(CorruptHost(bundle.read_bytes()), chunk_bytes=128).collect(
            "run_1", destination
        )
    assert not destination.exists()


def test_explicit_job_operations_keep_run_identity():
    host = FakeHost()
    client = RemoteClient(host)
    client.start("run_1")
    client.status("run_1")
    client.logs("run_1", offset=5, max_bytes=32)
    client.stop("run_1")
    client.resume("run_1", "smoke-first/checkpoint")
    assert [name for name, _ in host.actions] == [
        "start",
        "status",
        "logs",
        "stop",
        "resume",
    ]
    assert all(payload["run_id"] == "run_1" for _, payload in host.actions)
    with pytest.raises(ValueError, match="remote_stage_invalid"):
        client.start("run_1", stage="shell")
    with pytest.raises(ValueError, match="remote_run_id_invalid"):
        client.status("../other")
    with pytest.raises(ValueError, match="remote_log_range_invalid"):
        client.logs("run_1", offset=-1)


def test_invalid_limits_and_symlink_destination_are_rejected(tmp_path):
    for options in ({"chunk_bytes": 0}, {"attempts": 0}, {"max_bytes": 0}):
        with pytest.raises(ValueError):
            RemoteClient(FakeHost(), **options)
    source = tmp_path / "source"
    source.touch()
    destination = tmp_path / "result.zip"
    destination.symlink_to(source)
    with pytest.raises(ValueError, match="remote_collect_destination_invalid"):
        RemoteClient(FakeHost()).collect("run_1", destination)


def test_network_error_retries_only_bounded_transport_failures():
    class FailedHost(FakeHost):
        def request(self, action, payload):
            self.actions.append((action, payload))
            raise TransportError("remote_ssh_failed", retryable=True)

    host = FailedHost()
    with pytest.raises(TransportError):
        RemoteClient(host, attempts=2).status("run_1")
    assert len(host.actions) == 2

    class SemanticHost(FakeHost):
        def request(self, action, payload):
            self.actions.append((action, payload))
            raise TransportError("remote_training_bad_identity")

    host = SemanticHost()
    with pytest.raises(TransportError):
        RemoteClient(host, attempts=3).status("run_1")
    assert len(host.actions) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"total_bytes": 10**20},
        {"sha256": "not-a-hash"},
        {"eof": 1},
        {"data_b64": "not base64!"},
        {"data_b64": ""},
    ],
)
def test_collect_rejects_bad_remote_metadata_before_writing(tmp_path, change):
    bundle, _ = archive(tmp_path, kind="result")

    class InvalidHost(FakeHost):
        def request(self, action, payload):
            return {**super().request(action, payload), **change}

    destination = tmp_path / "downloaded.zip"
    with pytest.raises(TransportError):
        RemoteClient(InvalidHost(bundle.read_bytes()), chunk_bytes=128).collect(
            "run_1", destination
        )
    assert not destination.exists()


def test_changed_result_during_download_preserves_partial(tmp_path):
    bundle, _ = archive(tmp_path, kind="result")

    class ChangedHost(FakeHost):
        def request(self, action, payload):
            result = super().request(action, payload)
            if payload["offset"] > 0:
                result["sha256"] = "c" * 64
            return result

    destination = tmp_path / "downloaded.zip"
    with pytest.raises(TransportError, match="remote_collect_changed"):
        RemoteClient(ChangedHost(bundle.read_bytes()), chunk_bytes=128).collect(
            "run_1", destination
        )
    assert not destination.exists()
    assert destination.with_name(destination.name + ".part").stat().st_size == 128


def test_existing_destination_is_never_overwritten(tmp_path):
    bundle, _ = archive(tmp_path, kind="result")
    destination = tmp_path / "unrelated.zip"
    destination.write_bytes(b"keep my data")
    with pytest.raises(ValueError, match="remote_collect_destination_exists"):
        RemoteClient(FakeHost(bundle.read_bytes())).collect("run_1", destination)
    assert destination.read_bytes() == b"keep my data"


def test_input_and_result_archive_purposes_are_not_interchangeable(tmp_path):
    bundle, _ = archive(tmp_path, kind="result")
    with pytest.raises(ValueError, match="remote_input_bundle_required"):
        RemoteClient(FakeHost()).upload("run_1", bundle)
    bundle, _ = archive(tmp_path, kind="input")
    with pytest.raises(ValueError, match="remote_result_bundle_required"):
        RemoteClient(FakeHost(bundle.read_bytes())).collect(
            "run_1", tmp_path / "not-result.zip"
        )


def test_download_parts_are_private_from_creation_under_default_umask(tmp_path):
    bundle, _ = archive(tmp_path, kind="result")
    host = FakeHost(bundle.read_bytes(), interrupt=True)
    client = RemoteClient(host, chunk_bytes=128, attempts=1)
    destination = tmp_path / "private.zip"
    previous = os.umask(0o022)
    try:
        with pytest.raises(TransportError):
            client.collect("run_1", destination)
        part = destination.with_name(destination.name + ".part")
        metadata = destination.with_name(destination.name + ".part.json")
        assert part.stat().st_mode & 0o777 == 0o600
        assert metadata.stat().st_mode & 0o777 == 0o600
        host.interrupt = False
        client.collect("run_1", destination)
        assert destination.stat().st_mode & 0o777 == 0o600
    finally:
        os.umask(previous)


def test_executor_reaps_pipe_holding_descendant_after_leader_exit(tmp_path):
    from venom_core.services.remote_training.lifecycle import process_identity

    pidfile = tmp_path / "child.pid"
    leader = (
        "import subprocess,sys;from pathlib import Path;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
        "Path(sys.argv[1]).write_text(str(child.pid))"
    )
    started = time.monotonic()
    with pytest.raises(TransportError, match="remote_ssh_timeout"):
        execute_ssh([sys.executable, "-c", leader, str(pidfile)], b"{}", 1, 1024)
    assert time.monotonic() - started < 4
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 1
    while process_identity(pid) is not None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert process_identity(pid) is None


def test_client_rejects_parent_symlinks_before_transfer(tmp_path):
    bundle, _ = archive(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(bundle.parent, target_is_directory=True)
    host = FakeHost()
    client = RemoteClient(host)
    with pytest.raises(ValueError, match="bundle_path_invalid"):
        client.upload("run_1", alias / bundle.name)
    with pytest.raises(ValueError, match="collect_destination_invalid"):
        client.collect("run_1", alias / "output.zip")
    assert host.actions == []


def test_direct_archive_digest_cannot_read_private_paths():
    from venom_core.services.remote_training.client import _sha

    with pytest.raises(ValueError, match="outside_roots"):
        _sha(Path("/etc/passwd"))
