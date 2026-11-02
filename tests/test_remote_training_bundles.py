"""Safe transfer contracts using local synthetic data; no model/GPU/provider access."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile

import pytest

from venom_core.services.remote_training.artifacts import (
    create_result_bundle,
    inspect_artifacts,
    verify_result_bundle,
)
from venom_core.services.remote_training.bundles import (
    MANIFEST_NAME,
    canonical,
    create_bundle,
    extract_bundle,
    safe_relative,
    validate_identity,
    verify_bundle,
)


@pytest.fixture
def identity():
    return {
        "model": "test/model",
        "revision": "a" * 40,
        **{
            field + "_sha256": "b" * 64
            for field in (
                "tokenizer",
                "template",
                "profile",
                "data",
                "code",
                "dependencies",
            )
        },
        "dataset": "domain",
        "limits": {"max_seconds": 60, "updates": 2},
    }


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    (root / "data").mkdir(parents=True)
    (root / "data/train.jsonl").write_text('{"messages":[],"tools":[]}\n')
    (root / "profile.json").write_text('{"rank":16}')
    (root / "secret.env").write_text("DO_NOT_TRANSFER=private")
    return root


def make_archive(tmp_path, source, identity):
    archive = tmp_path / "input.zip"
    manifest = create_bundle(
        source,
        ["data/train.jsonl", "profile.json"],
        archive,
        run_id="run-01",
        identity=identity,
    )
    return archive, manifest


def rewrite_archive(
    source,
    destination,
    *,
    mutate_manifest=None,
    rename=None,
    mutate_data=None,
    extra=None,
):
    with (
        zipfile.ZipFile(source) as archive,
        zipfile.ZipFile(destination, "w") as target,
    ):
        for info in archive.infolist():
            name, value = info.filename, archive.read(info)
            if name == "manifest.json" and mutate_manifest:
                data = json.loads(value)
                mutate_manifest(data)
                data["manifest_sha256"] = hashlib.sha256(
                    canonical({k: v for k, v in data.items() if k != "manifest_sha256"})
                ).hexdigest()
                value = canonical(data)
            if mutate_data and name.startswith("payload/"):
                value = mutate_data(name, value)
            if rename:
                name = rename(name)
            target.writestr(name, value)
        if extra:
            target.writestr(*extra)


def test_selected_files_roundtrip_and_retry(tmp_path, source, identity):
    archive, manifest = make_archive(tmp_path, source, identity)
    assert list(manifest["files"]) == ["data/train.jsonl", "profile.json"]
    assert manifest["identity"] == identity
    assert (
        verify_bundle(archive, expected_identity=identity, expected_run_id="run-01")
        == manifest
    )
    target = tmp_path / "received"
    assert extract_bundle(archive, target, expected_identity=identity) == manifest
    assert (target / "data/train.jsonl").read_bytes() == (
        source / "data/train.jsonl"
    ).read_bytes()
    assert not (target / "secret.env").exists()
    assert json.loads((target / MANIFEST_NAME).read_text()) == manifest
    assert extract_bundle(archive, target) == manifest


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "a/../b",
        "a//b",
        "./a",
        "C:/file",
        "a\\b",
        "bad\x00name",
        ".env",
        ".ssh/key",
        "folder/.git/config",
        MANIFEST_NAME,
    ],
)
def test_portable_paths_reject_escapes_and_credentials(name):
    with pytest.raises(ValueError):
        safe_relative(name)


@pytest.mark.parametrize(
    "files", [[], ["profile.json", "profile.json"], ["a", "a/b"], ["A", "a"]]
)
def test_file_list_is_unambiguous(tmp_path, source, identity, files):
    with pytest.raises(ValueError):
        create_bundle(
            source, files, tmp_path / "input.zip", run_id="r", identity=identity
        )


def test_parent_symlink_and_limit_are_rejected(tmp_path, source, identity):
    (source / "linked").symlink_to(source / "data", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        create_bundle(
            source,
            ["linked/train.jsonl"],
            tmp_path / "a.zip",
            run_id="r",
            identity=identity,
        )
    with pytest.raises(ValueError, match="size"):
        create_bundle(
            source,
            ["profile.json"],
            tmp_path / "a.zip",
            run_id="r",
            identity=identity,
            max_bytes=1,
        )


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(password="secret"),
        lambda value: value.update(revision="main"),
        lambda value: value.update(code_sha256="invalid"),
        lambda value: value.update(snapshot="/home/private"),
    ],
)
def test_identity_cannot_embed_credentials_paths_or_floating_revisions(
    identity, change
):
    change(identity)
    with pytest.raises(ValueError):
        validate_identity(identity)


def test_destination_and_identity_are_not_overwritten(tmp_path, source, identity):
    archive, _ = make_archive(tmp_path, source, identity)
    with pytest.raises(FileExistsError):
        create_bundle(source, ["profile.json"], archive, run_id="r", identity=identity)
    with pytest.raises(ValueError, match="identity_mismatch"):
        extract_bundle(
            archive, tmp_path / "bad", expected_identity={**identity, "model": "other"}
        )
    with pytest.raises(ValueError, match="run_id_mismatch"):
        verify_bundle(archive, expected_run_id="other")
    target = tmp_path / "received"
    extract_bundle(archive, target)
    (target / "profile.json").write_text("changed")
    with pytest.raises(ValueError, match="payload_changed"):
        extract_bundle(archive, target)
    assert (target / "profile.json").read_text() == "changed"


def test_partial_and_changed_archives_never_publish(tmp_path, source, identity):
    archive, _ = make_archive(tmp_path, source, identity)
    changed = tmp_path / "changed.zip"
    rewrite_archive(archive, changed, mutate_data=lambda name, value: b"X" * len(value))
    with pytest.raises(ValueError, match="checksum"):
        extract_bundle(changed, tmp_path / "target")
    assert not (tmp_path / "target").exists()
    truncated = tmp_path / "truncated.zip"
    truncated.write_bytes(archive.read_bytes()[:20])
    with pytest.raises(zipfile.BadZipFile):
        verify_bundle(truncated)


def test_unlisted_and_duplicate_archive_members_are_rejected(
    tmp_path, source, identity
):
    archive, _ = make_archive(tmp_path, source, identity)
    changed = tmp_path / "changed.zip"
    rewrite_archive(archive, changed, extra=("../escape", b"bad"))
    with pytest.raises(ValueError, match="unlisted"):
        verify_bundle(changed)
    with pytest.warns(UserWarning, match="Duplicate"):
        rewrite_archive(archive, changed, extra=("payload/profile.json", b"duplicate"))
    with pytest.raises(ValueError, match="duplicate"):
        verify_bundle(changed)


def test_manifest_rehash_does_not_authorize_path_traversal(tmp_path, source, identity):
    archive, _ = make_archive(tmp_path, source, identity)
    changed = tmp_path / "changed.zip"

    def mutate(value):
        value["files"]["../escape"] = value["files"].pop("profile.json")

    rewrite_archive(
        archive,
        changed,
        mutate_manifest=mutate,
        rename=lambda name: name.replace("payload/profile.json", "payload/../escape"),
    )
    with pytest.raises(ValueError, match="path"):
        verify_bundle(changed)


def test_archive_special_file_and_expansion_limit(tmp_path, source, identity):
    archive, _ = make_archive(tmp_path, source, identity)
    special = tmp_path / "special.zip"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(special, "w") as target:
        for info in original.infolist():
            content = original.read(info)
            if info.filename.startswith("payload/"):
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            target.writestr(info, content)
    with pytest.raises(ValueError, match="special_entry"):
        verify_bundle(special)
    with pytest.raises(ValueError, match="size_exceeded"):
        verify_bundle(archive, max_bytes=1)


@pytest.fixture
def result(tmp_path, identity):
    folder = tmp_path / "result"
    folder.mkdir()
    docs = {
        "identity.json": identity,
        "adapter_config.json": {"r": 16},
        "profile.json": {"rank": 16},
        "data-manifest.json": {"splits": ["train", "validation"]},
        "metrics.json": {"loss": 0.1},
        "environment.json": {"python": "3.12"},
        "qualification.json": {"status": "PASS"},
        "supervisor.json": {
            "run_id": "run-01",
            "attempt": 1,
            "status": "succeeded",
            "exit_code": 0,
        },
        "status.json": {"state": "succeeded", "run_id": "run-01", "exit_code": 0},
    }
    for name, value in docs.items():
        (folder / name).write_text(json.dumps(value))
    (folder / "adapter_model.safetensors").write_bytes(b"synthetic-adapter")
    (folder / "logs").mkdir()
    (folder / "logs/training.log").write_text("completed")
    return folder


def test_complete_result_requires_fresh_local_reload(tmp_path, result, identity):
    manifest = create_result_bundle(
        result, tmp_path / "result.zip", run_id="run-01", identity=identity
    )
    assert manifest["kind"] == "result"
    receipt = verify_result_bundle(
        tmp_path / "result.zip", expected_identity=identity, expected_run_id="run-01"
    )
    assert receipt["complete"]
    assert receipt["local_reload_required"]
    assert not receipt["activation_authorized"]
    assert not receipt["destroy_authorized"]


def test_failed_run_evidence_is_collectable_but_incomplete(tmp_path, result, identity):
    (result / "adapter_model.safetensors").unlink()
    (result / "status.json").write_text(
        json.dumps({"state": "failed", "run_id": "run-01", "exit_code": 1})
    )
    create_result_bundle(
        result, tmp_path / "result.zip", run_id="run-01", identity=identity
    )
    receipt = verify_result_bundle(
        tmp_path / "result.zip", expected_identity=identity, expected_run_id="run-01"
    )
    assert not receipt["complete"]
    assert receipt["status"] == "failed"
    assert "adapter_model.safetensors" in receipt["missing"]


@pytest.mark.parametrize(
    "name,value",
    [
        ("identity.json", {}),
        ("identity.json", {"model": "wrong"}),
        ("qualification.json", {}),
        ("qualification.json", {"status": "FAIL"}),
        ("status.json", {"state": "succeeded", "run_id": "wrong", "exit_code": 0}),
        ("metrics.json", {"loss": float("nan")}),
    ],
)
def test_result_metadata_rejects_false_success(result, identity, name, value):
    (result / name).write_text(json.dumps(value))
    receipt = inspect_artifacts(result, identity, "run-01")
    assert not receipt["complete"]
    assert receipt["errors"]


def test_checkpoint_selection_and_receipt_tampering(tmp_path, result, identity):
    (result / "checkpoint").mkdir()
    (result / "checkpoint/optimizer.pt").write_bytes(b"state-not-loaded")
    assert (
        "checkpoint/optimizer.pt"
        not in inspect_artifacts(result, identity, "run-01")["files"]
    )
    archive = tmp_path / "result.zip"
    create_result_bundle(
        result, archive, run_id="run-01", identity=identity, include_checkpoint=True
    )
    receipt = verify_result_bundle(
        archive, expected_identity=identity, expected_run_id="run-01"
    )
    assert "checkpoint/optimizer.pt" in receipt["files"]
    altered = tmp_path / "altered.zip"
    rewrite_archive(
        archive,
        altered,
        mutate_manifest=lambda value: value["receipt"].update(complete=False),
    )
    with pytest.raises(ValueError, match="receipt_mismatch"):
        verify_result_bundle(
            altered, expected_identity=identity, expected_run_id="run-01"
        )


def test_artifact_parent_symlink_does_not_read_external_log(tmp_path, result, identity):
    (result / "logs/training.log").unlink()
    (result / "logs").rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "training.log").write_text("private")
    (result / "logs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        inspect_artifacts(result, identity, "run-01")


def test_parallel_retries_publish_one_verified_tree(tmp_path, source, identity):
    from concurrent.futures import ThreadPoolExecutor

    archive, manifest = make_archive(tmp_path, source, identity)
    destination = tmp_path / "received"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(extract_bundle, archive, destination) for _ in range(2)]
        assert [future.result() for future in futures] == [manifest, manifest]
    assert json.loads((destination / MANIFEST_NAME).read_text()) == manifest


def test_bare_secret_token_is_rejected(identity):
    identity["hf_token"] = "never-export"
    with pytest.raises(ValueError, match="secret_field"):
        validate_identity(identity)


def test_pack_retry_reuses_verified_original_archive(tmp_path, source, identity):
    archive, manifest = make_archive(tmp_path, source, identity)
    original = archive.read_bytes()
    repeated = create_bundle(
        source,
        ["profile.json", "data/train.jsonl"],
        archive,
        run_id="run-01",
        identity=identity,
    )
    assert repeated == manifest
    assert archive.read_bytes() == original
    (source / "profile.json").write_text("changed")
    with pytest.raises(FileExistsError, match="archive_conflict"):
        create_bundle(
            source,
            ["profile.json", "data/train.jsonl"],
            archive,
            run_id="run-01",
            identity=identity,
        )
    assert archive.read_bytes() == original


def test_published_archive_is_private_under_shared_umask(tmp_path, source, identity):
    import os

    previous = os.umask(0o022)
    try:
        archive, _ = make_archive(tmp_path, source, identity)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "state,code", [("failed", 1), ("stopped", -15), ("timed_out", -9), ("succeeded", 1)]
)
def test_supervisor_failure_blocks_complete_worker_result(
    tmp_path, result, identity, state, code
):
    archive = tmp_path / "supervised.zip"
    create_result_bundle(
        result,
        archive,
        run_id="run-01",
        identity=identity,
        supervisor={
            "run_id": "run-01",
            "attempt": 1,
            "status": state,
            "exit_code": code,
        },
    )
    receipt = verify_result_bundle(
        archive, expected_identity=identity, expected_run_id="run-01"
    )
    assert not receipt["complete"]
    assert receipt["supervisor"]["status"] == state
    assert json.loads((result / "status.json").read_text())["state"] == "succeeded"


def test_partial_stage_checkpoint_and_coordinator_log_are_retained(
    tmp_path, result, identity
):
    checkpoint = result / "stages/train-first/checkpoint"
    checkpoint.mkdir(parents=True)
    original = b'{"step":12,"fingerprint":"native-original","files":{}}'
    (checkpoint / "receipt.json").write_bytes(original)
    (checkpoint / "chat_template.jinja").write_text("native template unchanged")
    (checkpoint / "training-state.pt").write_bytes(b"foreign-optimizer-unchanged")
    (result / "checkpoint").mkdir()
    (result / "checkpoint/training-state.pt").write_bytes(b"partial-normalization")
    (result / "stages/train-resume/checkpoint").mkdir(parents=True)
    (result / "stages/train-resume/checkpoint/training-state.pt").write_bytes(
        b"partial"
    )
    coordinator = tmp_path / "worker.log"
    coordinator.write_text("preflight traceback: fixture")
    archive = tmp_path / "interrupted.zip"
    create_result_bundle(
        result,
        archive,
        run_id="run-01",
        identity=identity,
        include_checkpoint=True,
        supervisor={
            "run_id": "run-01",
            "attempt": 1,
            "status": "failed",
            "exit_code": 1,
        },
        coordinator_log=coordinator,
    )
    extracted = tmp_path / "extracted-interrupted"
    manifest = extract_bundle(archive, extracted)
    assert not manifest["receipt"]["complete"]
    assert (
        extracted / "stages/train-first/checkpoint/receipt.json"
    ).read_bytes() == original
    assert (
        extracted / "stages/train-first/checkpoint/training-state.pt"
    ).read_bytes() == b"foreign-optimizer-unchanged"
    assert "stages/train-resume/checkpoint/training-state.pt" not in manifest["files"]
    assert (
        extracted / "stages/train-first/checkpoint/chat_template.jinja"
    ).read_text() == "native template unchanged"
    assert (extracted / "logs/coordinator.log").read_text() == coordinator.read_text()
    verify_result_bundle(archive, expected_identity=identity, expected_run_id="run-01")


@pytest.mark.parametrize("operation", ["source", "hash", "archive", "extract"])
def test_bundle_io_rejects_symlink_ancestors(tmp_path, source, identity, operation):
    from venom_core.services.remote_training.bundles import sha256

    archive, _ = make_archive(tmp_path, source, identity)
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        if operation == "source":
            create_bundle(
                alias / "source",
                ["profile.json"],
                tmp_path / "new.zip",
                run_id="r",
                identity=identity,
            )
        elif operation == "hash":
            sha256(alias / "source/profile.json")
        elif operation == "archive":
            create_bundle(
                source,
                ["profile.json"],
                alias / "new.zip",
                run_id="r",
                identity=identity,
            )
        else:
            extract_bundle(archive, alias / "new-result")
    assert not (tmp_path / "new.zip").exists()
    assert not (tmp_path / "new-result").exists()


def test_job_copy_refuses_staging_symlink_before_external_write(
    tmp_path, source, monkeypatch
):
    from venom_core.services.remote_training import job

    staging, outside = tmp_path / "staging", tmp_path / "outside"
    staging.mkdir()
    outside.mkdir()
    (staging / "data").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(job, "DATA_FILES", ("data/train.jsonl",))
    with pytest.raises(ValueError):
        job._copy_inputs(source, staging)
    assert not list(outside.iterdir())


def test_job_copy_cannot_escape_explicit_staging_root(tmp_path, source, monkeypatch):
    from venom_core.services.remote_training import job

    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setattr(job, "DATA_FILES", ("../profile.json",))
    with pytest.raises(ValueError):
        job._copy_inputs(source, staging)
    assert not (tmp_path / "profile.json").exists()
    assert not list(staging.iterdir())
