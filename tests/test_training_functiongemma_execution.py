"""Same FunctionGemma bundle and evidence contracts for local and SSH sessions."""

import json
from pathlib import Path

import pytest

from venom_core.services.functiongemma import execution
from venom_core.services.functiongemma import worker as native
from venom_core.services.functiongemma.profile import Recipe
from venom_core.services.granite_operator.contract import write_json
from venom_core.services.remote_training import (
    artifacts,
    host,
    job,
    milestones,
    worker,
    worker_support,
)

MODEL = Recipe().model


def setup_inputs(tmp_path, monkeypatch):
    snapshot = tmp_path / Recipe().revision
    snapshot.mkdir()
    (snapshot / "tokenizer_config.json").write_text(
        json.dumps({"chat_template": "native"})
    )
    recipe = Recipe(context=2048)
    document = {"encoded_release_sha256": "e" * 64, "records": {"train": [{}] * 1408}}
    monkeypatch.setattr(
        execution, "validate_encoded_release", lambda *a, **k: document["records"]
    )
    monkeypatch.setattr(execution, "code_identity", lambda *a, **k: "c" * 64)
    monkeypatch.setattr(execution, "dependencies_identity", lambda *a, **k: "d" * 64)
    manifest = tmp_path / "encoded.json"
    write_json(manifest, document)
    return snapshot, recipe, document, manifest


def test_pack_and_native_preflight(tmp_path, monkeypatch):
    snapshot, recipe, document, manifest = setup_inputs(tmp_path, monkeypatch)
    bundle = tmp_path / "input.zip"
    result = execution.pack(
        manifest,
        recipe.identity(),
        snapshot,
        bundle,
        run_id="fg-full",
        updates=264,
        max_seconds=3600,
    )
    assert result["identity"]["limits"]["max_updates"] == 264
    assert set(result["files"]) == {"profile.json", "data-manifest.json"}
    write_json(tmp_path / "profile.json", recipe.identity())
    write_json(tmp_path / "data-manifest.json", document)
    configured = {
        "snapshot": str(snapshot),
        "code_root": str(Path(execution.__file__).resolve().parents[3]),
    }
    assert execution.preflight(configured, tmp_path, result["identity"])[0] == recipe
    with pytest.raises(ValueError, match="identity_mismatch"):
        execution.preflight(
            configured, tmp_path, {**result["identity"], "data_sha256": "a" * 64}
        )
    recipe_identity_1 = recipe.identity()
    with pytest.raises(ValueError, match="epoch_budget"):
        execution.pack(
            manifest,
            recipe_identity_1,
            snapshot,
            bundle,
            run_id="fg",
            updates=256,
            max_seconds=1,
        )
    monkeypatch.setattr(execution, "pack", lambda *a, **k: {"native": True})
    write_json(tmp_path / "profile.json", recipe.identity())
    assert job.prepare(
        tmp_path,
        manifest,
        tmp_path / "profile.json",
        snapshot,
        bundle,
        run_id="fg",
        updates=264,
    ) == {"native": True}


def proof(tmp_path):
    checkpoint = tmp_path / "checkpoint-2"
    checkpoint.mkdir()
    for name in (
        "optimizer.pt",
        "scheduler.pt",
        "rng_state.pth",
        "model.safetensors",
        "config.json",
    ):
        (checkpoint / name).write_text("{}")
    write_json(checkpoint / "trainer_state.json", {"global_step": 2})
    native._seal(checkpoint, "fp")
    return {
        "fingerprint": "fp",
        "qualified": True,
        "checkpoint": str(checkpoint),
        "checks": {
            key: True for key in ("save", "reload", "resume", "weights_updated")
        },
    }


def test_qualification_dispatch(tmp_path):
    metrics = proof(tmp_path)
    receipt = {
        **metrics,
        "status": "PASS",
        "kind": "functiongemma_training_qualification",
    }
    worker._require_stage_qualification({"model": MODEL}, receipt, "fp")
    with pytest.raises(ValueError, match="smoke_required"):
        execution.require_proof({**receipt, "qualified": False}, "fp")
    assert artifacts.required_files({"model": MODEL, "training_method": "full"})[
        -2:
    ] == ("model.safetensors", "config.json")
    assert "adapter_model.safetensors" in artifacts.required_files(
        {"model": MODEL, "training_method": "lora"}
    )


@pytest.mark.parametrize("method", ["full", "lora"])
def test_coordinate_smoke_and_train(tmp_path, monkeypatch, method):
    run = tmp_path / "runs" / "fg"
    result = run / "attempts/0001/result"
    (result / "stages/smoke").mkdir(parents=True)
    configured = {"host_id": "host", "snapshot": str(tmp_path / "snapshot")}
    identity = {"model": MODEL}
    req = {"stage": "smoke", "run_id": "fg", "manifest": {"identity": identity}}

    def stage_call(body):
        metrics = proof(result / "stages/smoke")
        if method == "lora":
            p = Path(metrics["checkpoint"])
            (p / "adapter_model.safetensors").write_text("adapter")
            (p / "adapter_config.json").write_text("{}")
            native._seal(p, "fp")
        return metrics

    out = execution.coordinate(
        req,
        configured,
        run,
        result,
        Recipe(method=method),
        "binding",
        stage_call=stage_call,
        proof_loader=lambda *a: None,
    )
    assert out["status"] == "PASS"
    assert (run / "qualification-proof.json").is_file()
    assert (result / "checkpoint/receipt.json").is_file()
    receipt = json.loads((result / "qualification.json").read_text())
    assert receipt["status"] == "PASS"
    second = run / "attempts/0002/result"
    second.mkdir(parents=True)

    def train_call(body):
        assert body["qualification"] == str(result / "qualification.json")
        folder = second / "stages/train"
        folder.mkdir(parents=True)
        return proof(folder)

    assert (
        execution.coordinate(
            {**req, "stage": "train"},
            configured,
            run,
            second,
            Recipe(method=method),
            "binding",
            stage_call=train_call,
            proof_loader=lambda *a: result / "qualification.json",
        )["status"]
        == "PASS"
    )


def test_epoch_and_smoke_resume_rejections(tmp_path):
    req = {"stage": "smoke", "until_update": 128}
    recipe_2 = Recipe()
    with pytest.raises(ValueError, match="epoch_budget"):
        execution.coordinate(
            req,
            {},
            tmp_path,
            tmp_path,
            recipe_2,
            "fp",
            stage_call=None,
            proof_loader=None,
        )
    req = {"stage": "smoke", "checkpoint": "checkpoint"}
    recipe_3 = Recipe()
    with pytest.raises(ValueError, match="retry_smoke"):
        execution.coordinate(
            req,
            {},
            tmp_path,
            tmp_path,
            recipe_3,
            "fp",
            stage_call=None,
            proof_loader=None,
        )


def test_dispatch_and_code_identity(tmp_path, monkeypatch):
    assert host.is_functiongemma_model(MODEL)
    for package in ("granite_operator", "functiongemma", "gemma4_operator"):
        directory = tmp_path / "venom_core/services" / package
        directory.mkdir(parents=True)
        (directory / "worker.py").write_text(package)
    first = host.code_identity(tmp_path, model=MODEL)
    (tmp_path / "venom_core/services/functiongemma/worker.py").write_text("changed")
    assert host.code_identity(tmp_path, model=MODEL) != first
    # FunctionGemma imports the shared parser, material helpers and schemas.
    for name in ("protocol.py", "material.py", "schemas.py"):
        shared = tmp_path / "venom_core/services/gemma4_operator" / name
        shared.write_text("original")
        before = host.code_identity(tmp_path, model=MODEL)
        shared.write_text("changed")
        assert host.code_identity(tmp_path, model=MODEL) != before

    monkeypatch.setattr(execution, "preflight", lambda *a: ("recipe", "document"))
    assert worker_support.preflight({}, tmp_path, {"model": MODEL}) == (
        "recipe",
        "document",
    )


def test_full_step_over_legacy_limit(tmp_path):
    attempt = tmp_path / "attempt"
    receipt = attempt / "result/checkpoint/receipt.json"
    write_json(receipt, {"model": MODEL, "step": 264})
    assert (
        milestones._checkpoint_evidence(attempt, tmp_path)["completed_updates"] == 264
    )
    write_json(receipt, {"step": 264})
    with pytest.raises(ValueError, match="step_invalid"):
        milestones._checkpoint_evidence(attempt, tmp_path)


def test_full_model_collection_is_complete_without_adapter(tmp_path, monkeypatch):
    snapshot, recipe, document, manifest = setup_inputs(tmp_path, monkeypatch)
    identity = execution.identity_for(
        recipe, document, snapshot, tmp_path, max_seconds=3600
    )
    result = tmp_path / "result"
    result.mkdir()
    docs = {
        "identity.json": identity,
        "profile.json": recipe.identity(),
        "data-manifest.json": document,
        "metrics.json": {"checks": "passed"},
        "environment.json": {"qualified": True},
        "qualification.json": {"status": "PASS"},
        "config.json": {"architectures": ["Gemma3ForCausalLM"]},
        "status.json": {"state": "succeeded", "run_id": "fg", "exit_code": 0},
        "supervisor.json": {
            "status": "succeeded",
            "run_id": "fg",
            "attempt": 1,
            "exit_code": 0,
        },
    }
    for name, value in docs.items():
        write_json(result / name, value)
    (result / "logs").mkdir()
    (result / "logs/training.log").write_text("native full SFT")
    (result / "model.safetensors").write_bytes(b"model")
    receipt = artifacts.inspect_artifacts(result, identity, "fg")
    assert receipt["complete"], receipt
    bundle = tmp_path / "result.zip"
    artifacts.create_result_bundle(result, bundle, run_id="fg", identity=identity)
    assert artifacts.verify_result_bundle(
        bundle, expected_identity=identity, expected_run_id="fg"
    )["complete"]
    from venom_core.services.remote_training import importer

    monkeypatch.setattr(
        importer, "_current", lambda root: ({"identity": identity}, {"complete": True})
    )
    with pytest.raises(ValueError, match="evaluation_required"):
        importer.finalize_import(result, tmp_path / "registry", lambda *a: None)


def test_native_child_launch_uses_fixed_worker(tmp_path, monkeypatch):
    result = tmp_path / "result"
    (result / "logs").mkdir(parents=True)
    output = result / "stages/smoke"
    write_json(output / "metrics.json", {"qualified": True})
    monkeypatch.setenv("REMOTE_TRAINING_GPU_LOCK_FD", "7")
    calls = []

    class Child:
        def __enter__(self):
            return self

    monkeypatch.setattr(
        worker.subprocess,
        "Popen",
        lambda argv, **kwargs: calls.append((argv, kwargs)) or Child(),
    )
    monkeypatch.setattr(worker, "_wait_stage", lambda *a: 0)
    metrics = worker.run_stage(
        {
            "admission_db": str(tmp_path / "ledger"),
            "code_root": str(tmp_path),
            "worker_python": "/qualified/python",
        },
        {"stage": "smoke", "profile": {"model": MODEL}, "output": str(output)},
        result,
        run_id="fg",
        timeout=30,
        children=[],
    )
    assert metrics["qualified"]
    assert "venom_core.services.functiongemma.worker" in calls[0][0]
    assert calls[0][1]["env"]["VENOM_GRANITE_RUN_ID"] == "fg"


def test_coordinator_forces_offline_in_both_execution_targets(tmp_path, monkeypatch):
    from venom_core.services.remote_training import supervisor

    monkeypatch.setattr(
        supervisor,
        "load_host",
        lambda root: {"code_root": str(tmp_path), "worker_python": "/qualified/python"},
    )
    argv, environment = supervisor.worker_launch(tmp_path, tmp_path / "request.json", 7)
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert "venom_core.services.remote_training.worker" in argv


def test_preflight_binds_warm_weights_to_input_profile(tmp_path, monkeypatch):
    """Reject a warm-start directory that differs from the sealed recipe."""
    from dataclasses import replace

    from venom_core.services.functiongemma.profile import INITIAL_WEIGHT_FILES
    from venom_core.services.granite_operator.contract import file_digest

    snapshot, recipe, document, _ = setup_inputs(tmp_path, monkeypatch)
    data = tmp_path / "input"
    data.mkdir()
    weights = tmp_path / "warm-start"
    weights.mkdir()
    for name in INITIAL_WEIGHT_FILES:
        (weights / name).write_text(name)
    recipe = replace(
        recipe,
        initial_weights={
            name: file_digest(weights / name) for name in INITIAL_WEIGHT_FILES
        },
    )
    write_json(data / "profile.json", recipe.identity())
    write_json(data / "data-manifest.json", document)
    root = Path(execution.__file__).resolve().parents[3]
    host_config = {"snapshot": str(snapshot), "code_root": str(root)}
    identity = execution.identity_for(
        recipe, document, snapshot, root, max_seconds=1200
    )
    assert execution.preflight(host_config, data, identity)[0] == recipe
    (weights / "config.json").write_text("changed")
    with pytest.raises(ValueError, match="initial_weights_changed"):
        execution.preflight(host_config, data, identity)
