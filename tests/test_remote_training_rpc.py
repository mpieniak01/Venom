"""Offline full RPC upload/collect contract with prepared local job stores."""

import base64
import hashlib
import json
import subprocess
import sys

import pytest

from venom_core.services.remote_training.bundles import create_bundle, verify_directory
from venom_core.services.remote_training.client import RemoteClient
from venom_core.services.remote_training.lifecycle import JobStore, atomic_json
from venom_core.services.remote_training.remote import response
from venom_core.services.remote_training.transport import TransportError


def input_bundle(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.jsonl").write_text('{"tools":[],"messages":[]}\n')
    identity = {
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
    bundle = tmp_path / "input.zip"
    manifest = create_bundle(
        source, ["train.jsonl"], bundle, run_id="job1", identity=identity
    )
    return bundle, manifest


class LocalRPC:
    def __init__(self, store):
        self.store = store
        self.requests = []

    def request(self, action, payload):
        self.requests.append((action, payload.copy()))
        result = response(self.store, action, payload)
        if not result["ok"]:
            raise TransportError(result["error"])
        return result["result"]


def terminal(store, manifest, *, result_files=False):
    directory = store.directory(manifest["run_id"])
    state = json.loads((directory / "state.json").read_text())
    state.update(
        status="failed",
        exit_code=3,
        attempt=1,
        attempt_root="runs/job1/attempts/0001",
        error="test_worker_failed",
    )
    attempt = store.root / state["attempt_root"]
    attempt.mkdir(parents=True)
    (attempt / "worker.log").write_text("before\ntraining failed\n")
    if result_files:
        result = attempt / "result"
        result.mkdir()
        atomic_json(
            result / "status.json",
            {"state": "failed", "run_id": "job1", "exit_code": 3},
        )
    atomic_json(directory / "state.json", state)
    return attempt


def test_rpc_roundtrip_lost_ack_and_failed_result_collection(tmp_path, monkeypatch):
    bundle, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    transport = LocalRPC(store)
    client = RemoteClient(transport, chunk_bytes=128)
    assert client.prepare(manifest)["status"] == "prepared"
    client.upload("job1", bundle)
    verify_directory(store.directory("job1") / "input", manifest)
    assert client.upload("job1", bundle)["ready"] is True
    captured = []
    monkeypatch.setattr(
        store,
        "start",
        lambda run_id, **kw: captured.append((run_id, kw)) or {"status": "running"},
    )
    monkeypatch.setattr(store, "stop", lambda run_id: {"status": "stopped"})
    monkeypatch.setattr(
        store,
        "resume",
        lambda run_id, checkpoint, **kw: {
            "status": "running",
            "checkpoint": checkpoint,
        },
    )
    assert client.start("job1")["status"] == "running"
    assert captured[0][1]["stage"] == "smoke"
    attempt = terminal(store, manifest)
    assert client.logs("job1", offset=7, max_bytes=8)["text"] == "training"
    assert client.stop("job1")["status"] == "stopped"
    assert (
        client.resume("job1", "attempts/0001/result/checkpoint")["status"] == "running"
    )
    downloaded = tmp_path / "collected.zip"
    receipt = client.collect("job1", downloaded)
    assert receipt["manifest"]["receipt"]["complete"] is False
    assert receipt["manifest"]["receipt"]["supervisor"]["status"] == "failed"
    assert "adapter_model.safetensors" in receipt["manifest"]["receipt"]["missing"]
    assert (attempt / "worker.log").read_text() == "before\ntraining failed\n"
    assert client.collect("job1", downloaded)["sha256"] == receipt["sha256"]


def test_prepare_rejects_unsealed_manifest_and_unlisted_rpc_fields(tmp_path):
    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    manifest["files"]["train.jsonl"]["size"] += 1
    assert response(store, "prepare", {"manifest": manifest})["ok"] is False
    assert response(store, "status", {"run_id": "../escape"})["ok"] is False
    assert response(store, "start", {"run_id": "job1", "command": "rm"})["ok"] is False
    assert not (tmp_path / "escape").exists()


def test_upload_rejects_changed_retry_and_bad_final_hash(tmp_path):
    bundle, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    client = RemoteClient(LocalRPC(store))
    client.prepare(manifest)
    checksum = hashlib.sha256(bundle.read_bytes()).hexdigest()
    payload = {
        "run_id": "job1",
        "upload_id": checksum,
        "sha256": checksum,
        "total_bytes": bundle.stat().st_size,
        "offset": 0,
        "data_b64": base64.b64encode(bundle.read_bytes()[:32]).decode(),
        "final": False,
    }
    assert response(store, "upload", payload)["ok"] is True
    changed = {**payload, "data_b64": base64.b64encode(b"x" * 32).decode()}
    assert (
        response(store, "upload", changed)["error"]
        == "remote_training_upload_retry_changed"
    )
    bad = {
        **payload,
        "upload_id": "c" * 64,
        "sha256": "c" * 64,
        "data_b64": base64.b64encode(bundle.read_bytes()).decode(),
        "final": True,
    }
    assert (
        response(store, "upload", bad)["error"]
        == "remote_training_upload_checksum_mismatch"
    )
    assert not (store.directory("job1") / "input").exists()


def test_upload_rejects_bad_range_and_collect_rejects_active_job(tmp_path):
    bundle, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    client = RemoteClient(LocalRPC(store))
    client.prepare(manifest)
    assert (
        response(store, "collect", {"run_id": "job1", "offset": 0, "max_bytes": 128})[
            "error"
        ]
        == "remote_training_collect_requires_terminal"
    )
    checksum = hashlib.sha256(bundle.read_bytes()).hexdigest()
    payload = {
        "run_id": "job1",
        "upload_id": checksum,
        "sha256": checksum,
        "total_bytes": 100,
        "offset": 101,
        "data_b64": "eA==",
        "final": False,
    }
    assert (
        response(store, "upload", payload)["error"]
        == "remote_training_upload_range_invalid"
    )
    payload.update(offset=1, total_bytes=bundle.stat().st_size)
    assert (
        response(store, "upload", payload)["error"]
        == "remote_training_upload_offset_invalid"
    )


def test_collect_partial_result_does_not_invent_adapter(tmp_path):
    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    terminal(store, manifest, result_files=True)
    client = RemoteClient(LocalRPC(store))
    receipt = client.collect("job1", tmp_path / "partial.zip")
    assert receipt["manifest"]["receipt"]["complete"] is False
    assert {"status.json", "supervisor.json", "logs/coordinator.log"} <= receipt[
        "manifest"
    ]["files"].keys()


def test_json_entrypoint_handles_invalid_input_without_disclosing_paths(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "venom_core.services.remote_training.remote",
            "--root",
            str(tmp_path / "remote"),
            "status",
        ],
        input=b"{bad-private-data",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "remote_training_rpc_invalid",
    }
    assert b"private" not in result.stdout


def test_empty_result_directory_remains_collectable_as_failed(tmp_path):
    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    attempt = terminal(store, manifest)
    (attempt / "result").mkdir()
    receipt = RemoteClient(LocalRPC(store)).collect("job1", tmp_path / "failed.zip")
    assert receipt["manifest"]["receipt"]["complete"] is False
    assert "logs/coordinator.log" in receipt["manifest"]["files"]


def test_rpc_entrypoint_limits_and_valid_json_without_shell(tmp_path, monkeypatch):
    import io
    import types

    from venom_core.services.remote_training import remote

    _, manifest = input_bundle(tmp_path)

    def invoke(action, raw):
        output = io.BytesIO()
        monkeypatch.setattr(
            remote.sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(raw))
        )
        monkeypatch.setattr(remote.sys, "stdout", types.SimpleNamespace(buffer=output))
        assert remote.main(["--root", str(tmp_path / "rpc-root"), action]) == 0
        return json.loads(output.getvalue())

    assert invoke("prepare", json.dumps({"manifest": manifest}).encode())["ok"] is True
    assert invoke("status", b"{not-json")["error"] == "remote_training_rpc_invalid"
    assert (
        invoke("status", b"x" * (remote.MAX_RPC_BYTES + 1))["error"]
        == "remote_training_rpc_too_large"
    )
    monkeypatch.setattr(
        remote,
        "response",
        lambda *_: {"ok": True, "result": {"data": "x" * remote.MAX_RPC_BYTES}},
    )
    assert invoke("status", b"{}")["error"] == "remote_training_rpc_too_large"


def test_rpc_rejects_invalid_training_stage_and_resume_checkpoint(tmp_path):
    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    assert (
        response(store, "start", {"run_id": "job1", "stage": "shell"})["error"]
        == "remote_training_stage_invalid"
    )
    assert (
        response(store, "resume", {"run_id": "job1", "checkpoint": ""})["error"]
        == "remote_training_checkpoint_path_invalid"
    )


def worker_reports_success(attempt, manifest):
    from venom_core.services.remote_training.artifacts import REQUIRED_FILES

    result = attempt / "result"
    result.mkdir(exist_ok=True)
    for name in REQUIRED_FILES:
        if name == "supervisor.json":
            continue
        path = result / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name == "identity.json":
            value = manifest["identity"]
        elif name == "status.json":
            value = {"state": "succeeded", "run_id": "job1", "exit_code": 0}
        elif name == "qualification.json":
            value = {"status": "PASS"}
        else:
            value = {"test": True}
        if name.endswith(".json"):
            atomic_json(path, value)
        else:
            path.write_bytes(b"actual worker evidence")
    return result


@pytest.mark.parametrize("state", ["failed", "stopped", "timed_out"])
def test_final_supervisor_failure_overrides_worker_success_without_rewriting_it(
    tmp_path, state
):
    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    attempt = terminal(store, manifest)
    result = worker_reports_success(attempt, manifest)
    before = (result / "status.json").read_bytes()
    path = store.directory("job1") / "state.json"
    final = json.loads(path.read_text())
    final.update(status=state, exit_code=3)
    atomic_json(path, final)
    receipt = RemoteClient(LocalRPC(store), chunk_bytes=128).collect(
        "job1", tmp_path / "result.zip"
    )
    proof = receipt["manifest"]["receipt"]
    assert proof["complete"] is False
    assert proof["supervisor"] == {
        "run_id": "job1",
        "attempt": 1,
        "status": state,
        "exit_code": 3,
    }
    assert "logs/coordinator.log" in receipt["manifest"]["files"]
    assert (result / "status.json").read_bytes() == before


def test_coordinator_log_is_retained_when_worker_created_partial_result(tmp_path):
    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    attempt = terminal(store, manifest, result_files=True)
    atomic_json(attempt / "result" / "identity.json", manifest["identity"])
    receipt = RemoteClient(LocalRPC(store)).collect("job1", tmp_path / "partial.zip")
    assert "logs/coordinator.log" in receipt["manifest"]["files"]
    assert receipt["manifest"]["receipt"]["complete"] is False


def test_cached_collection_chunks_never_rescan_worker_artifacts(tmp_path, monkeypatch):
    from venom_core.services.remote_training import remote_io

    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    terminal(store, manifest)
    payload = {
        "run_id": "job1",
        "offset": 0,
        "max_bytes": 128,
        "include_checkpoint": False,
    }
    first = response(store, "collect", payload)
    assert first["ok"] is True

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "cached chunks must not hash or repackage complete archives"
        )

    monkeypatch.setattr(remote_io, "create_result_bundle", forbidden)
    monkeypatch.setattr(remote_io, "verify_bundle", forbidden)
    monkeypatch.setattr(remote_io, "sha256", forbidden)
    last = response(store, "collect", {**payload, "offset": 128})
    assert last["ok"] is True
    assert last["result"]["sha256"] == first["result"]["sha256"]


def test_modified_same_size_cached_archive_is_rejected_before_next_chunk(tmp_path):
    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    terminal(store, manifest)
    payload = {
        "run_id": "job1",
        "offset": 0,
        "max_bytes": 128,
        "include_checkpoint": False,
    }
    assert response(store, "collect", payload)["ok"] is True
    archive = next((store.directory("job1") / "collections").glob("*.zip"))
    original_stat = archive.stat()
    before = original_stat.st_size
    with archive.open("r+b") as stream:
        byte = stream.read(1)
        stream.seek(0)
        stream.write(bytes([byte[0] ^ 1]))
    # Filesystems may give two same-tick writes identical timestamps.
    # Exercise the stat drift guard deterministically; the client still checks
    # the complete archive checksum independently of this cheap server guard.
    import os

    os.utime(
        archive,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000_000),
    )
    assert archive.stat().st_size == before
    result = response(store, "collect", {**payload, "offset": 128})
    assert result["error"] == "remote_training_collect_cache_changed"


def test_log_cursor_continues_after_supervisor_buffer_rotation(tmp_path):
    from venom_core.services.remote_training.lifecycle import LOG_LIMIT
    from venom_core.services.remote_training.supervisor import _append

    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    attempt = terminal(store, manifest)
    path = attempt / "worker.log"
    path.unlink()
    client = RemoteClient(LocalRPC(store))
    _append(path, b"a" * LOG_LIMIT)
    first = client.logs("job1", max_bytes=LOG_LIMIT)
    assert first["offset"] == LOG_LIMIT
    _append(path, b"model-progress")
    second = client.logs("job1", offset=first["offset"])
    assert second["text"] == "model-progress"
    assert second["offset"] == LOG_LIMIT + len(b"model-progress")
    _append(path, b"c" * (LOG_LIMIT + 20))
    third = client.logs("job1", offset=second["offset"], max_bytes=32)
    assert third["text"] == "c" * 32
    assert third["truncated"] is True
    assert third["base_offset"] > second["offset"]
    assert third["offset"] > second["offset"]


def test_checkpoint_free_retry_survives_lost_ack_without_resetting_budget(
    tmp_path, monkeypatch
):
    import os
    from types import SimpleNamespace

    bundle, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    base = LocalRPC(store)
    client = RemoteClient(base)
    client.prepare(manifest)
    client.upload("job1", bundle)
    attempt = terminal(store, manifest)
    state_path = store.directory("job1") / "state.json"
    state = json.loads(state_path.read_text())
    state.update(stage="smoke", elapsed_seconds=3.25)
    atomic_json(state_path, state)
    spawned = []

    def spawn(directory, number):
        spawned.append(number)
        return SimpleNamespace(pid=os.getpid())

    monkeypatch.setattr(store, "_spawn", spawn)

    class LostAck(LocalRPC):
        first = True

        def request(self, action, payload):
            result = super().request(action, payload)
            if action == "retry" and self.first:
                self.first = False
                saved = json.loads(state_path.read_text())
                saved.update(status="succeeded", exit_code=0)
                atomic_json(state_path, saved)
                raise TransportError("remote_ssh_failed", retryable=True)
            return result

    receipt = RemoteClient(LostAck(store)).retry("job1", from_attempt=1)
    assert receipt["status"] == "succeeded"
    assert receipt["attempt"] == 2
    assert receipt["elapsed_seconds"] == 3.25
    assert spawned == [2]
    assert (attempt / "worker.log").read_text() == "before\ntraining failed\n"
    with pytest.raises(TransportError, match="retry"):
        client.retry("job1", from_attempt=2)


def test_cli_exposes_explicit_checkpoint_free_retry(monkeypatch, capsys):
    from types import SimpleNamespace

    from venom_core.services.remote_training import cli

    calls = []
    monkeypatch.setattr(cli, "SSHTransport", lambda _: object())
    monkeypatch.setattr(
        cli,
        "RemoteClient",
        lambda _: SimpleNamespace(
            retry=lambda run_id, **kw: calls.append((run_id, kw))
            or {"status": "starting"}
        ),
    )
    assert (
        cli.main(
            ["--host", "fixture", "retry", "--run-id", "job1", "--from-attempt", "1"]
        )
        == 0
    )
    assert calls == [("job1", {"from_attempt": 1})]


def test_log_cursor_recovers_interrupted_publication_once(tmp_path):
    from venom_core.services.remote_training.supervisor import _append

    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    attempt = terminal(store, manifest)
    path = attempt / "worker.log"
    _append(path, b"old")
    replacement = attempt / "replacement"
    replacement.write_bytes(b"recovered-log")
    replacement.replace(path)
    client = RemoteClient(LocalRPC(store))
    first = client.logs("job1", offset=3)
    assert first["reset"] is True
    assert first["text"] == "recovered-log"
    second = client.logs("job1", offset=first["offset"])
    assert second["text"] == ""
    assert second["reset"] is False


@pytest.mark.parametrize("attempt", [0, -1, True, "1", None])
def test_retry_requires_explicit_valid_failed_attempt(tmp_path, attempt):
    _, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    terminal(store, manifest)
    result = response(store, "retry", {"run_id": "job1", "from_attempt": attempt})
    assert result["error"] == "remote_training_retry_attempt_invalid"
    with pytest.raises(ValueError, match="retry_attempt"):
        RemoteClient(LocalRPC(store)).retry("job1", from_attempt=attempt)
    assert store.status("job1")["attempt"] == 1


def test_checkpoint_free_retry_cannot_replenish_spent_budget(tmp_path, monkeypatch):
    bundle, manifest = input_bundle(tmp_path)
    store = JobStore(tmp_path / "remote")
    store.prepare(manifest)
    RemoteClient(LocalRPC(store)).upload("job1", bundle)
    terminal(store, manifest)
    state_path = store.directory("job1") / "state.json"
    state = json.loads(state_path.read_text())
    state.update(elapsed_seconds=3600)
    atomic_json(state_path, state)
    monkeypatch.setattr(
        store, "_spawn", lambda *_: pytest.fail("exhausted budget must not spawn")
    )
    with pytest.raises(ValueError, match="budget_exhausted"):
        store.retry("job1", from_attempt=1)
    assert store.status("job1")["attempt"] == 1
