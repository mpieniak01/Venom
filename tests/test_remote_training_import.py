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


@pytest.mark.parametrize("operation", ["registry", "academy", "import"])
def test_registration_sinks_validate_run_id_before_io(tmp_path, operation):
    from venom_core.services.remote_training import importer

    destination = tmp_path / "registry"
    with pytest.raises(ValueError, match="run_id_invalid"):
        if operation == "registry":
            importer._register(destination, {"run_id": "../escaped"})
        elif operation == "academy":
            importer._academy_register(
                tmp_path, destination, {"run_id": "../escaped"}, {}
            )
        else:
            import_result(
                tmp_path / "absent.zip",
                tmp_path / "quarantine",
                destination,
                {},
                "../escaped",
            )
    assert not destination.exists()
    assert not (tmp_path / "quarantine").exists()
    assert not (tmp_path / "escaped.json").exists()


@pytest.mark.parametrize("parameter", ["registry", "quarantine", "academy"])
def test_import_rejects_symlink_ancestors_before_reload(tmp_path, package, parameter):
    archive, identity, _ = package
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)

    def unexpected(*_args):
        pytest.fail("unsafe output path must fail before model reload")

    registry, quarantine = tmp_path / "registry", tmp_path / "quarantine"
    academy = None
    if parameter == "registry":
        registry = alias / "registry"
    elif parameter == "quarantine":
        quarantine = alias / "quarantine"
    else:
        academy = alias / "models"
    with pytest.raises(ValueError):
        import_result(
            archive,
            quarantine,
            registry,
            identity,
            "run01",
            unexpected,
            academy_models=academy,
        )
    assert not (tmp_path / "registry").exists()
    assert not (tmp_path / "quarantine").exists()
    assert not (tmp_path / "models").exists()


@pytest.fixture
def experiment_result(tmp_path, package):
    from venom_core.services.granite_operator.contract import (
        MODEL,
        REVISION,
        write_json,
    )

    _, identity, evidence = package
    identity.update(model=MODEL, revision=REVISION)
    write_json(evidence / "identity.json", identity)
    write_json(evidence / "metrics.json", {"global_step": 125})
    write_json(evidence / "checkpoint/receipt.json", {"step": 125})
    archive = tmp_path / "candidate.zip"
    create_result_bundle(
        evidence, archive, run_id="run01", identity=identity, include_checkpoint=True
    )
    return archive, evidence


def test_select_one_adapter_checks_bytes_and_does_not_activate(
    experiment_result, tmp_path
):
    from venom_core.services.granite_operator.contract import write_json
    from venom_core.services.remote_training import experiments as ex

    archive, root = experiment_result
    record = ex.select_result(archive, root, sha256(archive), 125)
    assert record["step"] == 125
    assert record["activation_state"] == "selected_pending_local_reload"
    assert not record["local_reload_verified"]
    selection = tmp_path / "selected.json"
    write_json(selection, record)
    assert ex.selected(selection) == record
    with pytest.raises(ValueError, match="checkpoint_mismatch"):
        ex.select_result(archive, root, sha256(archive), 126)
    with pytest.raises(ValueError, match="archive_or_step"):
        ex.select_result(archive, root, "a" * 64, 125)
    with pytest.raises(ValueError, match="archive_or_step"):
        ex.select_result(archive, root, sha256(archive), True)
    record["activation_state"] = "active"
    write_json(selection, record)
    with pytest.raises(ValueError, match="selection_changed"):
        ex.selected(selection)
    (root / "adapter_model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="payload_changed"):
        ex.select_result(archive, root, sha256(archive), 125)


@pytest.mark.parametrize("change", ["failed", "model", "revision"])
def test_select_rejects_failed_or_wrong_base(experiment_result, tmp_path, change):
    from venom_core.services.granite_operator.contract import write_json
    from venom_core.services.remote_training import experiments as ex

    _, root = experiment_result
    identity = json.loads((root / "identity.json").read_text())
    if change == "failed":
        write_json(
            root / "status.json", {"state": "failed", "run_id": "run01", "exit_code": 1}
        )
    else:
        identity[change] = "other/model" if change == "model" else "a" * 40
        write_json(root / "identity.json", identity)
    archive = tmp_path / "rejected.zip"
    create_result_bundle(
        root, archive, run_id="run01", identity=identity, include_checkpoint=True
    )
    with pytest.raises(ValueError, match="incomplete|revision_invalid"):
        ex.select_result(archive, root, sha256(archive), 125)


def test_matched_profiles_reject_precision_and_control_drift(tmp_path):
    from venom_core.services.granite_operator.contract import write_json
    from venom_core.services.remote_training import experiments as ex

    pair = ex.profiles(ex.REPO / "config")
    assert pair["qlora"].quantization == "nf4"
    assert pair["lora"].quantization == "bf16"
    assert pair["lora"].row_order == "family_epoch_v1"
    config = tmp_path / "config"
    for method, profile in pair.items():
        write_json(config / f"granite_operator_{method}.json", profile.identity())
    raw = pair["lora"].identity()
    raw["rank"] += 1
    write_json(config / "granite_operator_lora.json", raw)
    with pytest.raises(ValueError, match="controls_mismatch"):
        ex.profiles(config)
    raw["quantization"] = "nf4"
    write_json(config / "granite_operator_lora.json", raw)
    with pytest.raises(ValueError, match="method_precision"):
        ex.profiles(config)


@pytest.fixture
def prepared_pair(tmp_path, monkeypatch):
    from venom_core.services.granite_operator.contract import write_json
    from venom_core.services.remote_training import experiments as ex

    selection = tmp_path / "selected.json"
    write_json(selection, {"step": 125})
    monkeypatch.setattr(ex, "selected", lambda path: {"step": 125})
    manifest = tmp_path / "data.json"
    write_json(manifest, {"datasets": {"domain/train.jsonl": {"rows": 640}}})
    calls = []

    def pack(source, data, profile, snapshot, output, **options):
        method = output.parent.name
        calls.append(method)
        output.write_bytes(method.encode())
        identity = dict.fromkeys(
            (
                "data_sha256",
                "encoding_sha256",
                "code_sha256",
                "dependencies_sha256",
                "tokenizer_sha256",
                "template_sha256",
            ),
            "a" * 64,
        )
        identity["profile_sha256"] = sha256(profile)
        return {"identity": identity}

    monkeypatch.setattr(ex, "prepare", pack)
    options = dict(
        source=tmp_path,
        manifest=manifest,
        snapshot=tmp_path,
        output=tmp_path / "suite",
        selection=selection,
        run_prefix="g04-ab",
    )
    return ex, options, calls


def test_prepare_pair_is_independent_idempotent_and_final_only(prepared_pair):
    ex, options, calls = prepared_pair
    result = ex.prepare_pair(**options)
    assert calls == ["qlora", "lora"]
    assert result["milestones"] == [250]
    assert result["epochs"] == 1.5625
    assert not result["publish_intermediate_adapters"]
    assert (
        result["jobs"]["qlora"]["identity"]["profile_sha256"]
        != result["jobs"]["lora"]["identity"]["profile_sha256"]
    )
    assert ex.prepare_pair(**options) == result
    assert result["training_execution"] == "sequential_on_one_host"
    assert result["common_host_requirements"]["gpu_vram_gb"] == 24
    for method in ("qlora", "lora"):
        folder = options["output"] / method
        assert (folder / "READY.json").is_file()
        commands = json.loads((folder / "operator-commands.json").read_text())
        assert commands["train"][-2:] == ["--until-update", "250"]
        assert "destroy" not in commands
    with pytest.raises(ValueError, match="prepared_output_changed"):
        ex.prepare_pair(**{**options, "updates": 200})


def test_failed_second_experiment_preserves_first_ready_job(prepared_pair, monkeypatch):
    ex, options, _ = prepared_pair
    original = ex.prepare

    def failing(*args, **kwargs):
        if args[4].parent.name == "lora":
            raise RuntimeError("failed second preparation")
        return original(*args, **kwargs)

    monkeypatch.setattr(ex, "prepare", failing)
    with pytest.raises(RuntimeError, match="second preparation"):
        ex.prepare_pair(**options)
    assert (options["output"] / "qlora/READY.json").is_file()
    assert not (options["output"] / "suite.json").exists()
    monkeypatch.setattr(ex, "prepare", original)
    assert ex.prepare_pair(**options)["status"] == "CPU_PREPARED_GPU_SMOKE_REQUIRED"


def test_pair_rejects_encoding_drift_and_bad_counts(prepared_pair, monkeypatch):
    ex, options, _ = prepared_pair
    original = ex.prepare

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[4].parent.name == "lora":
            result["identity"]["encoding_sha256"] = "b" * 64
        return result

    monkeypatch.setattr(ex, "prepare", changed)
    with pytest.raises(ValueError, match="input_controls_mismatch"):
        ex.prepare_pair(**options)
    options["manifest"].write_text('{"datasets":{"domain/train.jsonl":{"rows":0}}}')
    with pytest.raises(ValueError, match="count_invalid"):
        ex.prepare_pair(**options)


def test_experiment_metadata_rejects_invalid_documents(tmp_path):
    from venom_core.services.remote_training import experiments as ex

    path = tmp_path / "value.json"
    path.write_text("[]")
    with pytest.raises(ValueError, match="metadata_invalid"):
        ex._read(path)
    path.write_bytes(b" " * (8 * 1024**2 + 1))
    with pytest.raises(ValueError, match="metadata_too_large"):
        ex._read(path)


def test_evaluation_commands_use_shared_precision_and_explicit_width(
    experiment_result, tmp_path, monkeypatch
):
    from scripts.granite_operator import comparison_support
    from venom_core.services.remote_training import experiments as ex

    _, root = experiment_result
    monkeypatch.setattr(
        comparison_support,
        "load_frozen",
        lambda p: ({"qualification": {"status": "PASS"}}, [{}]),
    )
    command = ex.evaluation_commands(
        root,
        tmp_path / "host",
        [tmp_path / "cases.json"],
        tmp_path / "eval",
        expected_step=125,
    )["commands"][0]
    assert command[command.index("--inference-precision") + 1] == "nf4"
    assert command[command.index("--concurrency") + 1] == "4"
    assert "--adaptive" in command
    local = ex.evaluation_commands(
        root,
        tmp_path / "host",
        [tmp_path / "cases.json"],
        tmp_path / "eval",
        expected_step=125,
        precision="bf16",
        placement="local",
    )["commands"][0]
    assert local[local.index("--concurrency") + 1] == "1"
    assert "--no-adaptive" in local
    with pytest.raises(ValueError, match="options_invalid"):
        ex.evaluation_commands(root, tmp_path, [], tmp_path, expected_step=125)
    monkeypatch.setattr(comparison_support, "load_frozen", lambda p: ({}, []))
    with pytest.raises(ValueError, match="cases_unqualified"):
        ex.evaluation_commands(root, tmp_path, [tmp_path], tmp_path, expected_step=125)
    (root / "status.json").write_text(
        '{"state":"failed", "run_id":"run01", "exit_code":1}'
    )
    with pytest.raises(ValueError, match="result_incomplete"):
        ex.evaluation_commands(root, tmp_path, [tmp_path], tmp_path, expected_step=125)

    (root / "status.json").write_text(
        '{"state":"succeeded", "run_id":"run01", "exit_code":0}'
    )
    with pytest.raises(ValueError, match="checkpoint_mismatch"):
        ex.evaluation_commands(root, tmp_path, [tmp_path], tmp_path, expected_step=250)


def test_experiment_cli_select_prepare_and_evaluation(
    tmp_path, experiment_result, monkeypatch, capsys
):
    from venom_core.services.remote_training import experiments as ex

    archive, root = experiment_result
    selection = tmp_path / "selected.json"
    arguments = [
        "select",
        "--archive",
        str(archive),
        "--adapter-root",
        str(root),
        "--sha256",
        sha256(archive),
        "--step",
        "125",
        "--output",
        str(selection),
    ]
    assert ex.main(arguments) == ex.main(arguments) == 0
    assert json.loads(selection.read_text())["step"] == 125
    capsys.readouterr()
    monkeypatch.setattr(ex, "prepare_pair", lambda *a, **kw: {"prepared": True})
    args = ["prepare", "--run-prefix", "g04-ab"]
    for name in ["source", "manifest", "snapshot", "output", "selection"]:
        args.extend(["--" + name, str(tmp_path)])
    assert ex.main(args) == 0
    monkeypatch.setattr(ex, "evaluation_commands", lambda *a, **kw: {"commands": []})
    args = ["evaluation-commands"]
    for name in ["result", "host", "cases", "output"]:
        args.extend(["--" + name, str(tmp_path)])
    assert ex.main(args) == 0


def test_experiment_select_validates_destination_before_creating_directories(
    tmp_path, experiment_result
):
    from venom_core.services.remote_training import experiments as ex

    archive, root = experiment_result
    destination = tmp_path / ".ssh" / "new" / "selected.json"
    with pytest.raises(ValueError, match="sensitive"):
        ex.main(
            [
                "select",
                "--archive",
                str(archive),
                "--adapter-root",
                str(root),
                "--sha256",
                sha256(archive),
                "--step",
                "125",
                "--output",
                str(destination),
            ]
        )
    assert not destination.parent.exists()
