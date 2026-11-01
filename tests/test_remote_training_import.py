"""Quarantined import requires live trusted local verification, not a remote receipt."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

from venom_core.services.remote_training.artifacts import (
    REQUIRED_FILES,
    create_result_bundle,
)
from venom_core.services.remote_training.bundles import canonical, sha256
from venom_core.services.remote_training.importer import finalize_import, import_result


@pytest.fixture
def package(tmp_path):
    identity = {"model": "test/model", "revision": "a" * 40}
    for kind in ("tokenizer", "template", "profile", "data", "code", "dependencies"):
        identity[kind + "_sha256"] = "b" * 64
    evidence = tmp_path / "evidence"
    for name in REQUIRED_FILES:
        path = evidence / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            b"adapter-bytes" if path.suffix == ".safetensors" else b'{"available":true}'
        )
    for name, document in {
        "identity.json": identity,
        "qualification.json": {"status": "PASS"},
        "supervisor.json": {
            "run_id": "run01",
            "attempt": 1,
            "status": "succeeded",
            "exit_code": 0,
        },
        "status.json": {"state": "succeeded", "run_id": "run01", "exit_code": 0},
    }.items():
        (evidence / name).write_text(json.dumps(document))
    archive = tmp_path / "output.zip"
    create_result_bundle(evidence, archive, run_id="run01", identity=identity)
    return archive, identity, evidence


def passed_reload(root, identity):
    return {
        "status": "PASS",
        "runtime_verified": True,
        "identity_sha256": hashlib.sha256(canonical(identity)).hexdigest(),
        "adapter_sha256": sha256(root / "adapter_model.safetensors"),
    }


def test_import_waits_for_actual_reload(tmp_path, package):
    archive, identity, _ = package
    registry = tmp_path / "registry"
    receipt = import_result(
        archive, tmp_path / "quarantine", registry, identity, "run01"
    )
    assert receipt["import_status"] == "pending_local_reload"
    assert receipt["local_reload_required"]
    assert not receipt["registered"]
    assert not receipt["activation_authorized"]
    assert not registry.exists()
    assert (
        Path(receipt["quarantine_path"]).joinpath("adapter_model.safetensors").is_file()
    )


def test_live_reload_registers_immutable_metadata_without_activation(tmp_path, package):
    archive, identity, _ = package
    observed = []

    def verifier(root, actual_identity):
        observed.append((root, actual_identity))
        return {
            **passed_reload(root, actual_identity),
            "password": uuid.uuid4().hex,
        }

    registry = tmp_path / "registry"
    for _ in range(2):
        receipt = import_result(
            archive, tmp_path / "quarantine", registry, identity, "run01", verifier
        )
        assert receipt["import_status"] == "registered"
        assert not receipt["local_reload_required"]
    assert len(observed) == 2
    record = json.loads((registry / "run01.json").read_text())
    assert record["model"] == identity["model"]
    assert record["revision"] == identity["revision"]
    assert not record["activation_authorized"]
    assert not record["local_resume_authorized"]
    assert "password" not in (registry / "run01.json").read_text()
    assert not receipt["destroy_authorized"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "FAIL"),
        ("runtime_verified", "true"),
        ("identity_sha256", "c" * 64),
        ("adapter_sha256", "c" * 64),
    ],
)
def test_false_or_replayed_verification_is_not_registered(
    tmp_path, package, field, value
):
    archive, identity, _ = package

    def verifier(root, actual_identity):
        return {**passed_reload(root, actual_identity), field: value}

    registry = tmp_path / "registry"
    with pytest.raises(ValueError, match="local_reload_failed"):
        import_result(
            archive, tmp_path / "quarantine", registry, identity, "run01", verifier
        )
    assert not registry.exists()


def test_json_remote_receipt_is_not_a_verifier(tmp_path, package):
    archive, identity, _ = package
    registry = tmp_path / "registry"
    receipt = import_result(
        archive, tmp_path / "quarantine", registry, identity, "run01"
    )
    with pytest.raises(ValueError, match="local_reload_required"):
        finalize_import(Path(receipt["quarantine_path"]), registry, {"status": "PASS"})
    assert not registry.exists()


def test_model_or_tokenizer_mismatch_fails_before_reload(tmp_path, package):
    archive, identity, _ = package

    def unexpected(*_args):
        pytest.fail("mismatched artifact must never trigger inference")

    for key in ("model", "tokenizer_sha256"):
        changed = {**identity, key: "other/model" if key == "model" else "c" * 64}
        with pytest.raises(ValueError, match="identity_mismatch"):
            import_result(
                archive,
                tmp_path / "quarantine",
                tmp_path / "registry",
                changed,
                "run01",
                unexpected,
            )


def test_changed_adapter_during_reload_fails(tmp_path, package):
    archive, identity, _ = package

    def swapped(root, actual_identity):
        proof = passed_reload(root, actual_identity)
        (root / "adapter_model.safetensors").write_bytes(b"swapped")
        return proof

    registry = tmp_path / "registry"
    with pytest.raises(ValueError, match="payload_changed"):
        import_result(
            archive, tmp_path / "quarantine", registry, identity, "run01", swapped
        )
    assert not registry.exists()


def test_failed_run_collects_evidence_without_calling_reload(tmp_path, package):
    _, identity, evidence = package
    (evidence / "adapter_model.safetensors").unlink()
    (evidence / "status.json").write_text(
        json.dumps({"state": "failed", "run_id": "run01", "exit_code": 1})
    )
    archive = tmp_path / "failed.zip"
    create_result_bundle(evidence, archive, run_id="run01", identity=identity)

    def unexpected(*_args):
        pytest.fail("incomplete run must not reload")

    registry = tmp_path / "registry"
    receipt = import_result(
        archive, tmp_path / "quarantine", registry, identity, "run01", unexpected
    )
    assert receipt["import_status"] == "incomplete"
    assert not receipt["registered"]
    assert not registry.exists()
    assert Path(receipt["quarantine_path"]).joinpath("logs/training.log").is_file()


def test_foreign_resume_state_is_never_rewritten_or_loaded(tmp_path, package):
    _, identity, evidence = package
    (evidence / "checkpoint").mkdir()
    foreign = b"foreign-runtime-fingerprint:UNCHANGED"
    (evidence / "checkpoint/training-state.pt").write_bytes(foreign)
    archive = tmp_path / "resume.zip"
    create_result_bundle(
        evidence, archive, run_id="run01", identity=identity, include_checkpoint=True
    )
    receipt = import_result(
        archive,
        tmp_path / "quarantine",
        tmp_path / "registry",
        identity,
        "run01",
        passed_reload,
    )
    assert (
        Path(receipt["quarantine_path"])
        .joinpath("checkpoint/training-state.pt")
        .read_bytes()
        == foreign
    )
    assert not receipt["local_resume_authorized"]


def test_conflicting_registry_is_not_overwritten(tmp_path, package):
    archive, identity, _ = package
    registry = tmp_path / "registry"
    registry.mkdir()
    existing = registry / "run01.json"
    existing.write_text('{"model":"different"}')
    with pytest.raises(ValueError, match="registry_conflict"):
        import_result(
            archive, tmp_path / "quarantine", registry, identity, "run01", passed_reload
        )
    assert existing.read_text() == '{"model":"different"}'


def test_academy_registration_uses_existing_metadata_contract(tmp_path, package):
    from types import SimpleNamespace

    from venom_core.services.academy.adapter_management_service import list_adapters

    archive, identity, _ = package
    academy = tmp_path / "models"
    settings = SimpleNamespace(ACADEMY_MODELS_DIR=str(academy))
    for _ in range(2):
        receipt = import_result(
            archive,
            tmp_path / "quarantine",
            tmp_path / "registry",
            identity,
            "run01",
            passed_reload,
            academy_models=academy,
        )
        assert receipt["academy_registered"]
    adapters = list_adapters(mgr=None, settings_obj=settings)
    assert len(adapters) == 1
    assert adapters[0].adapter_id == "run01"
    assert adapters[0].base_model == identity["model"]
    assert adapters[0].metadata_status == "canonical"
    metadata = json.loads((academy / "run01/metadata.json").read_text())
    assert metadata["source_flow"] == "remote_training"
    assert metadata["base_model_revision"] == identity["revision"]
    assert "chat_signature" not in metadata
    assert (academy / "run01/adapter/adapter_model.safetensors").is_file()
    assert not receipt["activation_authorized"]


def test_academy_copy_is_not_made_before_local_reload(tmp_path, package):
    archive, identity, _ = package
    academy = tmp_path / "models"
    receipt = import_result(
        archive,
        tmp_path / "quarantine",
        tmp_path / "registry",
        identity,
        "run01",
        academy_models=academy,
    )
    assert receipt["import_status"] == "pending_local_reload"
    assert not academy.exists()


def test_existing_academy_adapter_is_not_overwritten(tmp_path, package):
    archive, identity, _ = package
    academy = tmp_path / "models"
    previous = academy / "run01"
    previous.mkdir(parents=True)
    (previous / "metadata.json").write_text('{"existing":"preserve"}')
    with pytest.raises(ValueError, match="academy_conflict"):
        import_result(
            archive,
            tmp_path / "quarantine",
            tmp_path / "registry",
            identity,
            "run01",
            passed_reload,
            academy_models=academy,
        )
    assert (previous / "metadata.json").read_text() == '{"existing":"preserve"}'


def test_partial_then_complete_import_preserves_both_bundles(tmp_path, package):
    complete, identity, evidence = package
    (evidence / "adapter_model.safetensors").unlink()
    partial = tmp_path / "partial.zip"
    create_result_bundle(evidence, partial, run_id="run01", identity=identity)
    quarantine, registry = tmp_path / "quarantine", tmp_path / "registry"
    first = import_result(partial, quarantine, registry, identity, "run01")
    second = import_result(
        complete, quarantine, registry, identity, "run01", passed_reload
    )
    retry = import_result(
        complete, quarantine, registry, identity, "run01", passed_reload
    )
    assert first["import_status"] == "incomplete"
    assert second["registered"]
    assert first["quarantine_path"] != second["quarantine_path"]
    assert retry["quarantine_path"] == second["quarantine_path"]
    assert Path(first["quarantine_path"]).joinpath("status.json").is_file()
