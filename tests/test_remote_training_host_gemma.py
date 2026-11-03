"""Gemma bootstrap acceptance with native profile identities and fake processes."""

import hashlib
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.remote_training_host import prepare
from venom_core.services.gemma4_operator.profile import (
    E4B_MODEL,
    LOADER,
    MODEL,
    SNAPSHOT_FILES,
    GemmaProfile,
)


@pytest.fixture(params=(MODEL, E4B_MODEL))
def prepared(request, tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA_OPERATOR_DATA_ROOT", str(tmp_path))
    repository = Path(__file__).resolve().parents[1]
    name = (
        "gemma4_operator_profile.json"
        if request.param == MODEL
        else "gemma4_operator_e4b_profile.json"
    )
    preset = GemmaProfile.load(repository / "config" / name)
    contents = {name: "{}" for name in SNAPSHOT_FILES}
    contents["config.json"] = json.dumps(
        {
            "architectures": [preset.loader],
            "text_config": {"max_position_embeddings": 4096},
        }
    )
    profile = replace(
        preset,
        files={
            name: hashlib.sha256(value.encode()).hexdigest()
            for name, value in contents.items()
        },
    )
    profile_file = tmp_path / "selected-profile.json"
    profile_file.write_text(json.dumps({"schema_version": 1, **profile.identity()}))
    source = tmp_path / "source"
    for path in (
        prepare.LOCK,
        prepare.CONTROL,
        "venom_core/services/remote_training/remote.py",
        "venom_core/services/gemma4_operator/profile.py",
        "venom_core/services/gemma4_operator/training_worker.py",
    ):
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture")
    snapshot = tmp_path / "models" / profile.revision
    snapshot.mkdir(parents=True)

    def populate(target):
        for name, content in contents.items():
            (target / name).write_text(content)
        (target / "model.safetensors").write_bytes(b"fixture-not-model-weights")

    populate(snapshot)
    metadata = profile.validate_snapshot(snapshot)
    (snapshot / prepare.MODEL_RECEIPT).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model": profile.model,
                "revision": profile.revision,
                "files": prepare.payload_hashes(snapshot),
                "native_snapshot_metadata": metadata,
            }
        )
    )
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("fixture")
    python = venv / "bin/python"
    python.write_text("fixture")
    python.chmod(0o700)
    args = prepare.parser().parse_args(
        [
            "--python",
            sys.executable,
            "--code-root",
            str(source),
            "--commit",
            "a" * 40,
            "--venv",
            str(venv),
            "--snapshot",
            str(snapshot),
            "--root",
            str(tmp_path / "component"),
            "--admission-db",
            str(tmp_path / "admission.sqlite3"),
            "--model-profile",
            str(profile_file),
            "--offline-model",
            "--apply",
        ]
    )
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return args.commit
        if "platform.python_version()" in command[-1]:
            return prepare.PYTHON
        if prepare.GEMMA_METADATA in command:
            actual = GemmaProfile(**json.loads(command[4]))
            return json.dumps(actual.validate_snapshot(Path(command[3])))
        if prepare.DOWNLOAD in command:
            populate(Path(command[-1]))
        return ""

    monkeypatch.setattr(prepare, "run", run)
    monkeypatch.setattr(prepare.platform, "system", lambda: "Linux")
    monkeypatch.setattr(prepare.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        prepare.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3)
    )
    return args, profile, calls


def test_gemma_plan_selects_actual_model_loader_and_revision_without_processes(
    prepared,
):
    args, profile, calls = prepared
    args.apply = False
    result = prepare.plan(args)
    assert result["model"] == profile.model
    assert result["revision"] == profile.revision
    assert result["model_profile"] == profile.identity()
    assert result["requirements"] == [prepare.LOCK, prepare.CONTROL]
    assert result["training_started"] is False
    assert not calls
    assert not args.root.exists()


def test_default_gemma_snapshot_uses_selected_revision(prepared):
    args, profile, calls = prepared
    args.snapshot = None
    assert prepare.plan(args)["snapshot"] == "/workspace/models/" + profile.revision
    assert not calls


def test_offline_gemma_apply_keeps_existing_hashed_runtime_and_native_rpc(prepared):
    args, profile, calls = prepared
    result = prepare.apply(args)
    assert result["prepared"] is True
    assert result["model"] == profile.model
    install = next(call for call in calls if "--require-hashes" in call)
    assert str(args.code_root / prepare.LOCK) in install
    assert str(args.code_root / prepare.CONTROL) in install
    assert not any(prepare.DOWNLOAD in call for call in calls)
    metadata_call = next(call for call in calls if prepare.GEMMA_METADATA in call)
    assert json.loads(metadata_call[4]) == profile.identity()
    wrapper = (args.root / "rpc-python").read_text()
    assert "HF_HUB_OFFLINE=1" in wrapper
    assert "TRANSFORMERS_OFFLINE=1" in wrapper


def test_online_gemma_download_uses_variant_revision_then_publishes_receipt(prepared):
    args, profile, calls = prepared
    args.offline_model = False
    shutil.rmtree(args.snapshot)
    prepare.apply(args)
    download = next(call for call in calls if prepare.DOWNLOAD in call)
    assert download[-3:-1] == [profile.model, profile.revision]
    assert Path(download[-1]) != args.snapshot
    prepare.snapshot_ready(args.snapshot, profile=profile)
    receipt = json.loads((args.snapshot / prepare.MODEL_RECEIPT).read_text())
    assert set(profile.files) <= set(receipt["files"])
    assert receipt["native_snapshot_metadata"] == dict(profile.files)


@pytest.mark.parametrize("missing", ["processor_config.json", "chat_template.jinja"])
def test_gemma_missing_processor_metadata_fails_before_any_install(prepared, missing):
    args, _, calls = prepared
    (args.snapshot / missing).unlink()
    with pytest.raises(ValueError, match="snapshot_file_invalid"):
        prepare.apply(args)
    assert not any("--require-hashes" in call for call in calls)


def test_gemma_symlink_metadata_fails_before_any_install(prepared):
    args, _, calls = prepared
    original = args.snapshot / "processor_config.json"
    target = args.snapshot / "processor-copy.json"
    original.rename(target)
    original.symlink_to(target)
    with pytest.raises(ValueError, match="snapshot_file_invalid"):
        prepare.apply(args)
    assert not any("--require-hashes" in call for call in calls)


def test_gemma_cross_variant_revision_and_loader_are_rejected(prepared):
    args, profile, calls = prepared
    value = {"schema_version": 1, **profile.identity()}
    value["revision"] = "a" * 40
    args.model_profile.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="model_revision_unpinned"):
        prepare.plan(args)
    value["revision"] = profile.revision
    value["loader"] = (
        LOADER if profile.model == E4B_MODEL else "Gemma4ForConditionalGeneration"
    )
    args.model_profile.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="profile_model_invalid"):
        prepare.plan(args)
    assert not calls


def test_gemma_wrong_snapshot_revision_and_missing_source_fail_without_processes(
    prepared,
):
    args, profile, calls = prepared
    args.snapshot = args.snapshot.parent / prepare.REVISION
    with pytest.raises(ValueError, match="snapshot_revision_mismatch"):
        prepare.plan(args)
    args.snapshot = args.snapshot.parent / profile.revision
    (args.code_root / "venom_core/services/gemma4_operator/training_worker.py").unlink()
    with pytest.raises(ValueError, match="source_missing"):
        prepare.plan(args)
    assert not calls
