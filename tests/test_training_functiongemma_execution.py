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
    with pytest.raises(ValueError, match="epoch_budget"):
        execution.pack(
            manifest,
            recipe.identity(),
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
        {},
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
            {},
            "binding",
            stage_call=train_call,
            proof_loader=lambda *a: result / "qualification.json",
        )["status"]
        == "PASS"
    )


def test_epoch_and_smoke_resume_rejections(tmp_path):
    req = {"stage": "smoke", "until_update": 128}
    with pytest.raises(ValueError, match="epoch_budget"):
        execution.coordinate(
            req,
            {},
            tmp_path,
            tmp_path,
            Recipe(),
            {},
            "fp",
            stage_call=None,
            proof_loader=None,
        )
    req = {"stage": "smoke", "checkpoint": "checkpoint"}
    with pytest.raises(ValueError, match="retry_smoke"):
        execution.coordinate(
            req,
            {},
            tmp_path,
            tmp_path,
            Recipe(),
            {},
            "fp",
            stage_call=None,
            proof_loader=None,
        )


def test_dispatch_and_code_identity(tmp_path, monkeypatch):
    assert host.is_functiongemma_model(MODEL)
    for package in ("granite_operator", "functiongemma"):
        directory = tmp_path / "venom_core/services" / package
        directory.mkdir(parents=True)
        (directory / "worker.py").write_text(package)
    first = host.code_identity(tmp_path, model=MODEL)
    (tmp_path / "venom_core/services/functiongemma/worker.py").write_text("changed")
    assert host.code_identity(tmp_path, model=MODEL) != first
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
