"""Common remote dispatch contracts without a GPU, provider or child execution."""

import json
from pathlib import Path

import pytest

from venom_core.services.gemma4_operator import training
from venom_core.services.gemma4_operator.profile import E4B_MODEL, MODEL
from venom_core.services.granite_operator import engine
from venom_core.services.granite_operator.contract import (
    TrainingProfile,
    digest,
    file_digest,
    write_json,
)
from venom_core.services.remote_training import artifacts, host, worker, worker_support

GRANITE = "ibm-granite/granite-4.2-3b"
GEMMA_MODELS = (MODEL, E4B_MODEL)


def fail_granite(*args, **kwargs):
    pytest.fail("Gemma flow incorrectly selected a Granite-only contract")


def smoke_evidence(root):
    checks = {
        name: True
        for name in (
            "mask",
            "frozen_base",
            "updated_adapter",
            "reload",
            "resume",
            "adapter_effect",
            "context_backward",
        )
    }
    evidence = {
        "basis": "validated_native_token_spans",
        "encoded_release_sha256": "b" * 64,
    }
    first = {
        "stage": "smoke",
        "initial_step": 0,
        "global_step": 16,
        "additional_updates": 16,
        "fingerprint": "a" * 64,
        "checks": checks,
        "mask_evidence": evidence,
        "checkpoint": "checkpoint",
    }
    resumed = {
        **first,
        "stage": "smoke-resume",
        "initial_step": 16,
        "global_step": 20,
        "additional_updates": 4,
    }
    hashes = {}
    for name, document in (
        ("stages/smoke-first/metrics.json", first),
        ("stages/smoke-resume/metrics.json", resumed),
    ):
        path = root / name
        write_json(path, document)
        hashes[name] = file_digest(path)
    return first, resumed, hashes


@pytest.mark.parametrize("model", GEMMA_MODELS)
def test_gemma_common_smoke_uses_real_gemma_receipt_and_validator(
    tmp_path, monkeypatch, model
):
    first, resumed, hashes = smoke_evidence(tmp_path)
    monkeypatch.setattr(worker, "qualification", fail_granite)
    monkeypatch.setattr(worker, "require_qualification", fail_granite)
    receipt = worker._stage_qualification({"model": model}, resumed, first, hashes)
    assert receipt["kind"] == "gemma4_training_qualification"
    assert receipt["status"] == "PASS"
    assert receipt["tool_loop_qualified"] is False
    worker._require_stage_qualification(
        {"model": model}, receipt, resumed["fingerprint"]
    )
    bad = {**receipt, "kind": "granite_training_qualification"}
    with pytest.raises(ValueError, match="gemma_training_remote_smoke_required"):
        worker._require_stage_qualification(
            {"model": model}, bad, resumed["fingerprint"]
        )


def test_granite_common_smoke_keeps_legacy_qualification(monkeypatch):
    calls = []
    sentinel = {"legacy": True}
    monkeypatch.setattr(
        worker, "qualification", lambda *args: calls.append(args) or sentinel
    )
    monkeypatch.setattr(
        worker, "require_qualification", lambda *args: calls.append(args)
    )
    monkeypatch.setattr(
        training,
        "qualification",
        lambda *args: pytest.fail("Granite selected Gemma qualification"),
    )
    monkeypatch.setattr(
        training,
        "require_qualification",
        lambda *args: pytest.fail("Granite selected Gemma validator"),
    )
    result = worker._stage_qualification(
        {"model": GRANITE}, {"final": 1}, {"first": 1}, {"hash": 1}
    )
    assert result is sentinel
    worker._require_stage_qualification({"model": GRANITE}, sentinel, "fingerprint")
    assert calls == [
        ({"final": 1}, {"first": 1}, {"hash": 1}),
        (sentinel, "fingerprint"),
    ]


@pytest.mark.parametrize("model", GEMMA_MODELS)
def test_proof_reuse_checks_real_gemma_artifacts_and_rejects_changed_model(
    tmp_path, monkeypatch, model
):
    result = tmp_path / "result"
    first, resumed, hashes = smoke_evidence(result)
    receipt = training.qualification(resumed, first, hashes)
    write_json(result / "qualification.json", receipt)
    write_json(result / "status.json", {"state": "succeeded"})
    write_json(
        tmp_path / "qualification-proof.json",
        {"binding": digest(model), "qualification": "result/qualification.json"},
    )
    monkeypatch.setattr(
        worker, "binding", lambda host, identity: digest(identity["model"])
    )
    monkeypatch.setattr(worker, "require_qualification", fail_granite)
    assert (
        worker.proof_for(tmp_path, {}, {"model": model})
        == result / "qualification.json"
    )
    other = E4B_MODEL if model == MODEL else MODEL
    with pytest.raises(ValueError, match="new_host_qualification_required"):
        worker.proof_for(tmp_path, {}, {"model": other})
    (result / "stages/smoke-first/metrics.json").write_text("{}")
    with pytest.raises(ValueError, match="qualification_changed"):
        worker.proof_for(tmp_path, {}, {"model": model})


@pytest.mark.parametrize("model", (*GEMMA_MODELS, GRANITE))
def test_run_stage_selects_actual_module_with_offline_environment_and_parent_lease(
    tmp_path, monkeypatch, model
):
    result = tmp_path / "result"
    (result / "logs").mkdir(parents=True)
    output = result / "stages/smoke-first"
    output.mkdir(parents=True)
    metrics = {"stage": "smoke", "model": model}
    write_json(output / "metrics.json", metrics)
    host_config = {
        "worker_python": "/qualified/bin/python",
        "admission_db": "/operator/admission.sqlite3",
        "code_root": "/reviewed/source",
    }
    request = {
        "stage": "smoke-first",
        "profile": {"model": model},
        "output": str(output),
    }
    calls = []

    class Child:
        def __init__(self, argv, **kwargs):
            self.args = argv
            calls.append((argv, kwargs))

        def wait(self, timeout):
            return 0

    monkeypatch.setenv("REMOTE_TRAINING_GPU_LOCK_FD", "23")
    monkeypatch.setattr(worker.subprocess, "Popen", Child)
    children = []
    actual = worker.run_stage(
        host_config, request, result, run_id="job-1", timeout=10, children=children
    )
    assert actual == metrics
    assert len(children) == 1
    argv, kwargs = calls[0]
    expected = (
        "venom_core.services.granite_operator.worker"
        if model == GRANITE
        else "venom_core.services.gemma4_operator.training_worker"
    )
    assert argv == [
        "setpriv",
        "--pdeathsig",
        "TERM",
        "--",
        host_config["worker_python"],
        "-m",
        expected,
        str(result / "smoke-first.request.json"),
    ]
    assert kwargs["pass_fds"] == (23,)
    assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
    assert kwargs["env"]["TRANSFORMERS_OFFLINE"] == "1"
    assert kwargs["env"]["VENOM_GRANITE_RUN_ID"] == "job-1"
    assert kwargs["env"]["PYTHONPATH"] == host_config["code_root"]
    assert json.loads((result / "smoke-first.request.json").read_text()) == request


@pytest.mark.parametrize("model", GEMMA_MODELS)
def test_gemma_preflight_delegates_before_any_granite_encoder(
    tmp_path, monkeypatch, model
):
    calls = []
    recipe, document = object(), {"kind": "gemma4_encoded_release"}

    def actual(host, source, identity):
        calls.append((host, source, identity))
        return recipe, document

    monkeypatch.setattr(training, "remote_preflight", actual)
    monkeypatch.setattr(worker_support, "TrainingProfile", fail_granite)
    monkeypatch.setattr(worker_support, "load_dataset", fail_granite)
    identity = {"model": model}
    config = {"host_id": "test-host"}
    assert worker_support.preflight(config, tmp_path, identity) == (recipe, document)
    assert calls == [(config, tmp_path, identity)]


def test_granite_preflight_keeps_legacy_dataset_and_native_encoder(
    tmp_path, monkeypatch
):
    import transformers

    profile = TrainingProfile()
    source = Path(worker_support.__file__).resolve().parents[3]
    input_root = tmp_path / "input"
    input_root.mkdir()
    document = {"datasets": {"domain": {}, "hf": {}}}
    write_json(input_root / "profile.json", profile.identity())
    write_json(input_root / "data-manifest.json", document)
    snapshot = tmp_path / profile.revision
    calls = []
    encoded = [{"labels": [-100, 1]}]
    monkeypatch.setattr(training, "remote_preflight", fail_granite)
    monkeypatch.setattr(
        worker_support, "tokenizer_identity", lambda path: ("a" * 64, "b" * 64)
    )
    monkeypatch.setattr(worker_support, "code_identity", lambda root: "c" * 64)
    monkeypatch.setattr(worker_support, "dependencies_identity", lambda root: "d" * 64)

    def dataset(root, manifest, family):
        calls.append(family)
        return [{"family": family}], [{"family": family}]

    monkeypatch.setattr(worker_support, "load_dataset", dataset)
    token = object()

    def load(path, **kwargs):
        assert path == snapshot
        assert kwargs == {"local_files_only": True}
        return token

    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", load)

    def encode(rows, tokenizer, observed_profile):
        assert len(rows) == 4
        assert tokenizer is token
        assert observed_profile == profile
        return encoded

    monkeypatch.setattr(engine, "encoded_rows", encode)
    identity = {
        "model": profile.model,
        "revision": profile.revision,
        "tokenizer_sha256": "a" * 64,
        "template_sha256": "b" * 64,
        "profile_sha256": digest(profile.identity()),
        "data_sha256": digest(document),
        "code_sha256": "c" * 64,
        "dependencies_sha256": "d" * 64,
        "encoding_sha256": digest(encoded),
    }
    actual, observed = worker_support.preflight(
        {"code_root": str(source), "snapshot": str(snapshot)}, input_root, identity
    )
    assert actual == profile
    assert observed == document
    assert calls == ["domain", "hf"]


def test_code_identity_preserves_legacy_digest_and_binds_both_gemma_engine_packages(
    tmp_path,
):
    granite = tmp_path / "venom_core/services/granite_operator"
    gemma = tmp_path / "venom_core/services/gemma4_operator"
    granite.mkdir(parents=True)
    gemma.mkdir(parents=True)
    (granite / "engine.py").write_text("legacy engine")
    (gemma / "training.py").write_text("Gemma implementation")
    expected = digest({"engine.py": file_digest(granite / "engine.py")})
    assert host.code_identity(tmp_path) == expected
    assert host.code_identity(tmp_path, model=GRANITE) == expected
    before = {
        model: host.code_identity(tmp_path, model=model) for model in GEMMA_MODELS
    }
    (gemma / "training.py").write_text("changed Gemma implementation")
    assert host.code_identity(tmp_path) == expected
    assert all(
        host.code_identity(tmp_path, model=model) != before[model]
        for model in GEMMA_MODELS
    )
    changed = host.code_identity(tmp_path, model=MODEL)
    (granite / "engine.py").write_text("changed shared engine")
    assert host.code_identity(tmp_path, model=MODEL) != changed
    assert host.code_identity(tmp_path) != expected


@pytest.mark.parametrize("model", GEMMA_MODELS)
def test_known_gemma_model_needs_its_engine_package(tmp_path, model):
    with pytest.raises(ValueError, match="gemma_code_missing"):
        host.code_identity(tmp_path, model=model)


def test_dependencies_bind_shared_exact_closure_for_each_supported_model(tmp_path):
    lock = tmp_path / "requirements/locks/granite-operator-training-linux-py314.txt"
    lock.parent.mkdir(parents=True)
    lock.write_text("exact training closure")
    control = tmp_path / "requirements-remote-training-control.txt"
    control.write_text("exact control closure")
    expected = digest({"training": file_digest(lock), "control": file_digest(control)})
    for model in (*GEMMA_MODELS, GRANITE, None):
        assert host.dependencies_identity(tmp_path, model=model) == expected
    unsupported = "unregistered/model"
    with pytest.raises(ValueError, match="dependency_model_unsupported"):
        host.dependencies_identity(tmp_path, model=unsupported)


def test_collector_accepts_realistic_encoded_manifest_size_but_retains_other_limits(
    tmp_path,
):
    value = {"kind": "gemma4_encoded_release", "fixture_payload": "x" * (8 * 1024**2)}
    write_json(tmp_path / "data-manifest.json", value)
    errors = []
    assert artifacts._document(tmp_path, "data-manifest.json", errors) == value
    assert not errors
    (tmp_path / "data-manifest.json").rename(tmp_path / "metrics.json")
    assert artifacts._document(tmp_path, "metrics.json", errors) == {}
    assert errors == ["invalid_metadata:metrics.json"]


@pytest.mark.parametrize("model", GEMMA_MODELS)
def test_gemma_code_identity_rejects_missing_shared_engine(tmp_path, model):
    (tmp_path / "venom_core/services/gemma4_operator").mkdir(parents=True)
    with pytest.raises(ValueError, match="shared_code_missing"):
        host.code_identity(tmp_path, model=model)


def test_result_inspection_accepts_large_encoded_manifest(tmp_path):
    """Accept an encoded manifest above the ordinary metadata size limit."""
    from venom_core.services.remote_training.artifacts import _document

    path = tmp_path / "data-manifest.json"
    with path.open("wb") as stream:
        stream.write(b'{"data":"')
        stream.write(b"x" * (65 * 1024**2))
        stream.write(b'"}')
    errors = []
    result = _document(tmp_path, path.name, errors)
    assert len(result["data"]) == 65 * 1024**2
    assert errors == []
