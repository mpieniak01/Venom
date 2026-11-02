"""Offline milestone recovery and historical artifact isolation contracts."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from venom_core.services.remote_training import milestones, remote
from venom_core.services.remote_training.artifacts import verify_result_bundle
from venom_core.services.remote_training.client import RemoteClient
from venom_core.services.remote_training.lifecycle import (
    JobStore,
    atomic_json,
    process_identity,
)


def identity():
    return {
        "model": "ibm-granite/granite-4.2-3b",
        "revision": "4e9c275e232f10211ec88644d106a1f6a1b60e06",
        **{
            key: "a" * 64
            for key in [
                "tokenizer_sha256",
                "template_sha256",
                "profile_sha256",
                "data_sha256",
                "code_sha256",
                "dependencies_sha256",
            ]
        },
        "dataset": "domain",
        "limits": {"max_updates": 160, "max_seconds": 7200},
    }


@pytest.mark.parametrize("value", [0, -1, True, 161, "80"])
def test_targets_cannot_exceed_frozen_budget(value):
    manifest = {"identity": identity()}
    with pytest.raises(ValueError):
        milestones.target_update(manifest, "train", value)


def test_plan_is_bounded_and_does_not_launch_anything():
    p = milestones.plan("experiment", [80, 125, 160], 7200)
    assert p["max_updates"] == 160
    assert not any((s["auto_advance"] for s in p["steps"]))
    assert milestones.target_update({"identity": identity()}, "train", 80) == 80
    assert milestones.target_update({}, "smoke", None) is None
    manifest = {"identity": identity()}
    with pytest.raises(ValueError):
        milestones.target_update(manifest, "smoke", 80)


@pytest.mark.parametrize("steps", [[125, 80], [80, 80], [], [257], [False]])
def test_invalid_plans_fail_before_execution(steps):
    with pytest.raises(ValueError):
        milestones.plan("experiment", steps, 7200)


@pytest.fixture
def archived(tmp_path):
    store = JobStore(tmp_path / "host")
    manifest = {"run_id": "job1", "identity": identity(), "files": {}}
    store.prepare(manifest)
    directory = store.directory("job1")
    (directory / "input").mkdir()
    atomic_json(directory / "input/.bundle-manifest.json", manifest)

    def finish(attempt, step, status="succeeded", target=None):
        result = directory / "attempts" / f"{attempt:04d}" / "result"
        (result / "logs").mkdir(parents=True)
        (result / "checkpoint").mkdir()
        (result / "adapter_model.safetensors").write_bytes(
            ("weights-" + str(step)).encode()
        )
        (result / "logs/training.log").write_text("training evidence")
        (result.parent / "worker.log").write_text("coordinator evidence")
        documents = {
            "adapter_config.json": {"peft_type": "LORA"},
            "identity.json": identity(),
            "profile.json": {"rank": 16},
            "data-manifest.json": {"version": 3},
            "metrics.json": {"global_step": step, "candidate_step": step},
            "environment.json": {"qualified": True},
            "qualification.json": {"status": "PASS"},
            "status.json": {
                "run_id": "job1",
                "state": status,
                "exit_code": 0 if status == "succeeded" else 1,
            },
            "checkpoint/receipt.json": {"step": step},
        }
        for name, value in documents.items():
            atomic_json(result / name, value)
        state = store._read(directory)
        state.update(
            attempt=attempt,
            status=status,
            stage="train",
            until_update=target or step,
            attempt_root=f"runs/job1/attempts/{attempt:04d}",
            exit_code=0 if status == "succeeded" else 1,
            supervisor=None,
            worker=None,
        )
        atomic_json(directory / "state.json", state)
        store.status("job1")
        return result

    result = finish(1, 80)

    class RPC:
        def request(self, action, payload):
            answer = remote.response(store, action, payload)
            if not answer["ok"]:
                raise ValueError(answer["error"])
            return answer["result"]

    return store, directory, result, finish, RemoteClient(RPC(), chunk_bytes=1024)


def test_collect_first_candidate_while_later_attempt_is_running(archived, tmp_path):
    store, directory, result, finish, client = archived
    sealed = (result.parent / "outcome.json").read_bytes()
    state = store._read(directory)
    state.update(
        attempt=2,
        status="running",
        until_update=125,
        attempt_root="runs/job1/attempts/0002",
        supervisor=process_identity(os.getpid()),
    )
    atomic_json(directory / "state.json", state)
    response = client.collect(
        "job1", tmp_path / "80.zip", attempt=1, include_checkpoint=True
    )
    receipt = verify_result_bundle(
        tmp_path / "80.zip", expected_identity=identity(), expected_run_id="job1"
    )
    assert receipt["complete"]
    assert receipt["supervisor"]["attempt"] == 1
    assert (result.parent / "outcome.json").read_bytes() == sealed
    assert store.status("job1")["status"] == "running"
    assert client.attempt_history("job1")["attempts"][0]["completed_updates"] == 80
    assert (
        client.collect("job1", tmp_path / "80.zip", attempt=1, include_checkpoint=True)[
            "sha256"
        ]
        == response["sha256"]
    )
    with pytest.raises(ValueError, match="requires_terminal"):
        client.collect("job1", tmp_path / "active.zip", attempt=2)


def test_failed_next_attempt_does_not_invalidate_previous_adapter(archived, tmp_path):
    store, directory, result, finish, client = archived
    earlier = (
        result.read_bytes()
        if result.is_file()
        else (result / "adapter_model.safetensors").read_bytes()
    )
    finish(2, 92, status="failed", target=125)
    assert not client.collect("job1", tmp_path / "failed.zip", attempt=2)["manifest"][
        "receipt"
    ]["complete"]
    assert client.collect("job1", tmp_path / "80.zip", attempt=1)["manifest"][
        "receipt"
    ]["complete"]
    assert (result / "adapter_model.safetensors").read_bytes() == earlier
    assert [r["status"] for r in store.attempts("job1")] == ["succeeded", "failed"]


def test_sealed_result_tampering_cannot_be_published(archived, tmp_path):
    _, _, result, _, client = archived
    (result / "adapter_model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="sealed_artifact_changed"):
        client.collect("job1", tmp_path / "bad.zip", attempt=1)
    assert not (tmp_path / "bad.zip").exists()


@pytest.mark.parametrize("attempt", [0, -1, True, "../1", None])
def test_invalid_explicit_attempt_selectors_are_rejected(archived, attempt):
    store, directory, _, _, _ = archived
    if attempt is None:
        with pytest.raises(ValueError):
            milestones.read_attempt(directory, 99)
    else:
        with pytest.raises(ValueError):
            store.attempt_status("job1", attempt)


def test_target_is_part_of_idempotent_launch_identity(archived, monkeypatch):
    store, directory, _, _, _ = archived
    from venom_core.services.remote_training import bundles

    monkeypatch.setattr(bundles, "verify_directory", lambda *a: None)
    spawn = Mock(return_value=SimpleNamespace(pid=os.getpid()))
    monkeypatch.setattr(store, "_spawn", spawn)
    checkpoint = "attempts/0001/result/checkpoint"
    state = store.resume("job1", checkpoint, until_update=125)
    assert state["until_update"] == 125
    assert store.resume("job1", checkpoint, until_update=125)["attempt"] == 2
    assert spawn.call_count == 1
    with pytest.raises(ValueError, match="conflicting_active_start"):
        store.resume("job1", checkpoint, until_update=160)
    req = json.loads((directory / "attempts/0002/request.json").read_text())
    assert req["until_update"] == 125


def test_resume_failed_step_retains_its_target_instead_of_skipping_ahead(
    archived, monkeypatch
):
    store, directory, result, finish, _ = archived
    finish(2, 92, status="failed", target=125)
    from venom_core.services.remote_training import bundles

    monkeypatch.setattr(bundles, "verify_directory", lambda *a: None)
    monkeypatch.setattr(store, "_spawn", lambda *a: SimpleNamespace(pid=os.getpid()))
    state = store.resume("job1", "attempts/0002/result/checkpoint")
    assert state["until_update"] == 125


def test_cli_plan_is_local_and_cannot_overwrite_different_plan(tmp_path):
    from venom_core.services.remote_training.cli import dispatch, parser

    args = parser().parse_args(
        ["plan", "--run-id", "job1", "--output", str(tmp_path / "plan.json")]
    )
    assert dispatch(args)["milestones"] == [80, 125, 160]
    assert dispatch(args)["execution"] == "explicit_one_step_at_a_time"
    args.milestones = [80, 125]
    with pytest.raises(ValueError, match="plan_exists"):
        dispatch(args)


def test_downloaded_attempt_identity_must_match_selected_candidate():
    with pytest.raises(ValueError, match="attempt_mismatch"):
        RemoteClient._verify_attempt({"receipt": {"supervisor": {"attempt": 2}}}, 1)


@pytest.mark.parametrize("corrupt", [False, True])
def test_seal_recovers_crash_between_result_commit_and_job_state(archived, corrupt):
    store, directory, result, _, _ = archived
    state = store._read(directory)
    state.update(status="running", supervisor=None, worker=None, elapsed_seconds=987.0)
    if corrupt:
        (result / "adapter_model.safetensors").write_bytes(b"broken_after_power_loss")
    atomic_json(directory / "state.json", state)
    recovered = store.status("job1")
    assert recovered["status"] == ("failed" if corrupt else "succeeded")
    assert recovered["error"] == ("sealed_attempt_invalid" if corrupt else None)
    if not corrupt:
        assert recovered["elapsed_seconds"] == 0.0


@pytest.mark.parametrize(
    "action,extra",
    [
        ("start", ["--stage", "train", "--until-update", "80"]),
        (
            "resume",
            [
                "--checkpoint",
                "attempts/0001/result/checkpoint",
                "--until-update",
                "125",
            ],
        ),
        ("collect", ["--output", "/tmp/candidate.zip", "--attempt", "2"]),
        ("attempts", []),
    ],
)
def test_cli_exposes_independent_stage_and_collection_actions(
    monkeypatch, action, extra
):
    from venom_core.services.remote_training import cli

    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True}

    client = SimpleNamespace(
        start=capture, resume=capture, collect=capture, attempt_history=capture
    )
    monkeypatch.setattr(cli, "SSHTransport", lambda _: None)
    monkeypatch.setattr(cli, "RemoteClient", lambda _: client)
    args = cli.parser().parse_args(
        ["--host", "fixture", action, "--run-id", "job1", *extra]
    )
    assert cli.dispatch(args)["ok"]
    if action in ("start", "resume"):
        assert calls[0][1]["until_update"] == (80 if action == "start" else 125)
    if action == "collect":
        assert calls[0][1]["attempt"] == 2


def test_client_carries_explicit_targets_and_rejects_invalid_limits():
    calls = []

    class Transport:
        def request(self, action, payload):
            calls.append((action, payload))
            return {}

    client = RemoteClient(Transport())
    client.start("job1", stage="train", until_update=80)
    client.resume("job1", "attempts/0001/result/checkpoint", until_update=125)
    assert [p["until_update"] for _, p in calls] == [80, 125]
    for value in [0, True, 257]:
        with pytest.raises(ValueError):
            client.start("job1", stage="train", until_update=value)
        with pytest.raises(ValueError):
            client.resume("job1", "checkpoint", until_update=value)
    with pytest.raises(ValueError):
        client.start("job1", until_update=80)
    with pytest.raises(ValueError):
        client.collect("job1", Path("/tmp/unused.zip"), attempt=0)


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": "other"},
        {"attempt": 9},
        {"status": "running"},
        {"attempt_root": "/elsewhere"},
        [],
    ],
)
def test_sealed_attempt_identity_is_not_taken_from_untrusted_paths(archived, change):
    _, directory, result, _, _ = archived
    file = result.parent / "outcome.json"
    proof = json.loads(file.read_text())
    if isinstance(change, dict):
        proof.update(change)
    else:
        proof = change
    file.write_text(json.dumps(proof))
    with pytest.raises(ValueError):
        milestones.read_attempt(directory, 1)


@pytest.mark.parametrize("corruption", ["json", "oversized", "identity", "status"])
def test_corrupt_attempt_is_reported_without_blocking_other_candidates(
    archived, tmp_path, corruption
):
    store, directory, _, finish, client = archived
    finish(2, 125)
    outcome = directory / "attempts/0002/outcome.json"
    proof = json.loads(outcome.read_text())
    if corruption == "json":
        outcome.write_text("{")
    elif corruption == "oversized":
        outcome.write_text(" " * (8 * 1024**2 + 1))
    else:
        proof["run_id" if corruption == "identity" else "status"] = (
            "other" if corruption == "identity" else {}
        )
        outcome.write_text(json.dumps(proof))
    history = store.attempts("job1")
    assert [row["attempt"] for row in history] == [1, 2]
    assert history[0]["completed_updates"] == 80
    assert history[1]["status"] == "invalid"
    assert history[1]["error"] == "remote_training_attempt_outcome_unreadable"
    client.collect("job1", tmp_path / "candidate-80.zip", attempt=1)
    with pytest.raises(ValueError):
        client.collect("job1", tmp_path / "invalid.zip", attempt=2)


def test_atomic_json_rejects_outside_roots_and_symlinks(tmp_path, monkeypatch):
    from venom_core.services.remote_training import paths

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr(paths, "_data_roots", lambda: (allowed,))
    outside = tmp_path / "outside.json"
    with pytest.raises(ValueError, match="outside_roots"):
        atomic_json(outside, {})
    assert not outside.exists()
    outside.write_text("original")
    link = allowed / "state.json"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        atomic_json(link, {})
    assert outside.read_text() == "original"


def test_atomic_json_rejects_directory_swap_after_validation(tmp_path, monkeypatch):
    from venom_core.services.remote_training import paths

    root, outside = tmp_path / "approved", tmp_path / "outside"
    target = root / "target"
    target.mkdir(parents=True)
    outside.mkdir()
    monkeypatch.setattr(paths, "_data_roots", lambda: (root,))
    original = paths.os.open
    swapped = False

    def replace_before_open(name, flags, *args, **kwargs):
        nonlocal swapped
        if name == "target" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            target.rename(root / "previous")
            target.symlink_to(outside, target_is_directory=True)
        return original(name, flags, *args, **kwargs)

    monkeypatch.setattr(paths.os, "open", replace_before_open)
    destination = target / "state.json"
    with pytest.raises(OSError):
        atomic_json(destination, {"unsafe": True})
    assert not (outside / "state.json").exists()


def test_atomic_json_syncs_private_descriptor_relative_state(tmp_path, monkeypatch):
    from venom_core.services.remote_training import paths

    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    monkeypatch.setattr(paths, "_data_roots", lambda: (root,))
    target = nested / "state.json"
    atomic_json(target, {"value": 1})
    atomic_json(target, {"value": 2})
    assert json.loads(target.read_text()) == {"value": 2}
    assert target.stat().st_mode & 0o777 == 0o600
    assert not (nested / "state.json.tmp").exists()
    bad = root / "bad\\name"
    bad.mkdir()
    invalid = bad / "state.json"
    with pytest.raises(ValueError, match="path_invalid"):
        atomic_json(invalid, {})


@pytest.mark.parametrize(
    "payload", ["{", '{"step":true}', '{"step":"125"}', "[]", "null"]
)
def test_invalid_checkpoint_evidence_is_sealed_without_blocking_history(
    archived, tmp_path, payload
):
    store, directory, _, finish, client = archived
    result = finish(2, 125)
    outcome = result.parent / "outcome.json"
    outcome.unlink()
    (result / "checkpoint/receipt.json").write_text(payload)
    assert store.status("job1")["status"] == "succeeded"
    invalid = json.loads(outcome.read_text())
    assert invalid["status"] == "invalid_evidence"
    assert invalid["result_checkpoint"] is None
    assert invalid["artifact_hashes"] == {}
    assert store.attempts("job1")[1]["status"] == "invalid"
    client.collect("job1", tmp_path / "valid-80.zip", attempt=1)
    with pytest.raises(ValueError):
        client.collect("job1", tmp_path / "invalid-125.zip", attempt=2)
    (result / "checkpoint/receipt.json").write_text('{"step":125}')
    assert store.status("job1")["attempt"] == 2
    with pytest.raises(ValueError, match="outcome_invalid"):
        milestones.read_attempt(directory, 2)
