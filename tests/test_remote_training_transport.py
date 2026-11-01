"""SSH isolation, lost-ack retries and verified/resumable artifact transport."""

import base64
import hashlib
import json
import os
import shlex
import sys
import time

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
