"""FunctionGemma adapter for the shared local/SSH session lifecycle."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from venom_core.services.granite_operator.contract import (
    digest,
    file_digest,
    inside,
    write_json,
)
from venom_core.services.remote_training.bundles import create_bundle, validate_identity
from venom_core.services.remote_training.host import (
    code_identity,
    dependencies_identity,
    tokenizer_identity,
)
from venom_core.services.remote_training.paths import operator_path

from .encoding import validate_encoded_release
from .profile import Recipe
from .retention import targets_for

PROFILE_FILE = "profile.json"
DATA_MANIFEST_FILE = "data-manifest.json"
QUALIFICATION_FILE = "qualification.json"


def identity_for(recipe, document, snapshot, code_root, *, max_seconds):
    tokenizer_sha, template_sha = tokenizer_identity(snapshot)
    return {
        "model": recipe.model,
        "revision": recipe.revision,
        "training_method": recipe.method,
        "tokenizer_sha256": tokenizer_sha,
        "template_sha256": template_sha,
        "profile_sha256": digest(recipe.identity()),
        "data_sha256": digest(document),
        "code_sha256": code_identity(code_root, model=recipe.model),
        "dependencies_sha256": dependencies_identity(code_root, model=recipe.model),
        "encoding_sha256": document["encoded_release_sha256"],
        "dataset": "domain",
        "limits": {
            "max_updates": recipe.budget(len(document["records"]["train"]))[
                "total_updates"
            ],
            "max_seconds": max_seconds,
        },
    }


def pack(manifest, profile, snapshot, output, *, run_id, updates, max_seconds):
    recipe = Recipe(**profile)
    recipe.validate()
    document = json.loads(manifest.read_text())
    records = validate_encoded_release(document, context=recipe.context)
    targets_for(document, recipe)
    total = recipe.budget(len(records["train"]))["total_updates"]
    if updates != total or total > 4096:
        raise ValueError("remote_training_functiongemma_epoch_budget_mismatch")
    if snapshot.name != recipe.revision:
        raise ValueError("remote_training_snapshot_revision_mismatch")
    code_root = Path(__file__).resolve().parents[3]
    identity = identity_for(
        recipe, document, snapshot, code_root, max_seconds=max_seconds
    )
    validate_identity(identity)
    with tempfile.TemporaryDirectory(prefix="functiongemma-input-") as tmp:
        staging = Path(tmp)
        write_json(staging / PROFILE_FILE, recipe.identity())
        write_json(staging / DATA_MANIFEST_FILE, document)
        return create_bundle(
            staging,
            [PROFILE_FILE, DATA_MANIFEST_FILE],
            output,
            run_id=run_id,
            identity=identity,
        )


def preflight(host, input_root, identity):
    recipe = Recipe(**json.loads((input_root / PROFILE_FILE).read_text()))
    recipe.validate()
    document = json.loads((input_root / DATA_MANIFEST_FILE).read_text())
    validate_encoded_release(document, context=recipe.context)
    targets_for(document, recipe)
    if Path(__file__).resolve().parents[3] != Path(host["code_root"]).resolve():
        raise ValueError("remote_training_imported_code_mismatch")
    snapshot = Path(host["snapshot"])
    if snapshot.name != recipe.revision:
        raise ValueError("remote_training_snapshot_revision_mismatch")
    actual = identity_for(
        recipe,
        document,
        snapshot,
        Path(host["code_root"]),
        max_seconds=identity["limits"]["max_seconds"],
    )
    if actual != identity:
        raise ValueError("remote_training_identity_mismatch")
    if recipe.initial_weights is not None:
        from .worker import resolve_model_source

        resolve_model_source(recipe, snapshot, input_root.parent)
    return recipe, document


def require_proof(receipt, fingerprint):
    if (
        receipt.get("kind") != "functiongemma_training_qualification"
        or receipt.get("fingerprint") != fingerprint
        or receipt.get("qualified") is not True
        or receipt.get("status") != "PASS"
        or any(
            receipt.get("checks", {}).get(key) is not True
            for key in ("save", "reload", "resume", "weights_updated")
        )
    ):
        raise ValueError("remote_training_functiongemma_smoke_required")
    from .worker import verify_checkpoint

    verify_checkpoint(operator_path(receipt["checkpoint"]), fingerprint)


def coordinate(
    request,
    host,
    run_root,
    result,
    recipe,
    host_binding,
    *,
    stage_call,
    proof_loader,
):
    """Run the same bounded child for both targets, retaining host-owned receipts."""
    stage = request["stage"]
    if request.get("until_update") is not None:
        raise ValueError("remote_training_functiongemma_uses_epoch_budget")
    if stage == "smoke":
        if request.get("checkpoint"):
            raise ValueError("remote_training_functiongemma_retry_smoke_from_base")
        proof = None
    else:
        proof = proof_loader(run_root, host, request["manifest"]["identity"])
    body = {
        "stage": _worker_stage(request),
        "profile": recipe.identity(),
        "recipe": recipe.identity(),
        "gpu_authorized": True,
        "run_id": request["run_id"],
        "snapshot": host["snapshot"],
        "encoded_release": str(run_root / "input" / DATA_MANIFEST_FILE),
        "output": str(result / "stages" / stage),
        "qualification": str(proof) if proof else None,
    }
    if request.get("checkpoint"):
        body["checkpoint"] = str(operator_path(inside(run_root, request["checkpoint"])))
    final = stage_call(body)
    checkpoint = operator_path(final["checkpoint"])
    if not checkpoint.is_relative_to(result / "stages"):
        raise ValueError("remote_training_functiongemma_checkpoint_outside_attempt")
    shutil.copytree(checkpoint, result / "checkpoint")
    _store_qualification(stage, final, result, run_root, host_binding, proof)
    _copy_weight_export(result, recipe.method)
    write_json(result / "metrics.json", final)
    write_json(
        result / "environment.json",
        {
            "host_binding": host_binding,
            "host_id": host["host_id"],
            "qualified": True,
            "activation_allowed": False,
        },
    )
    write_json(
        result / "status.json",
        {"state": "succeeded", "run_id": request["run_id"], "exit_code": 0},
    )
    return {"status": "PASS", "result": str(result)}


def _worker_stage(request):
    if request["stage"] == "smoke":
        return "smoke"
    if request.get("checkpoint"):
        return "resume"
    return "train"


def _store_qualification(stage, final, result, run_root, host_binding, proof):
    if stage == "smoke":
        receipt = {
            **final,
            "status": "PASS",
            "kind": "functiongemma_training_qualification",
            "binding": host_binding,
            "artifacts": {
                str(p.relative_to(result)): file_digest(p)
                for p in (result / "stages").rglob("*")
                if p.is_file()
            },
        }
        require_proof(receipt, final["fingerprint"])
        write_json(result / QUALIFICATION_FILE, receipt)
        write_json(
            run_root / "qualification-proof.json",
            {
                "binding": host_binding,
                "qualification": str(
                    (result / QUALIFICATION_FILE).relative_to(run_root)
                ),
            },
        )
    else:
        shutil.copyfile(proof, result / QUALIFICATION_FILE)


def _copy_weight_export(result, method):
    source = result / "checkpoint"
    names = (
        ("model.safetensors", "config.json", "generation_config.json")
        if method == "full"
        else ("adapter_model.safetensors", "adapter_config.json")
    )
    for name in names:
        if (source / name).is_file():
            shutil.copyfile(source / name, result / name)
