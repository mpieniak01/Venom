"""Common remote dispatch contracts without a GPU, provider or child execution."""

import hashlib
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from venom_core.services.gemma4_operator import training, training_worker
from venom_core.services.gemma4_operator.profile import (
    BOLT_MODEL,
    BOLT_SNAPSHOT_FILES,
    BOLT_WEIGHT_BYTES,
    E4B_MODEL,
    MODEL,
    MODEL_LOADERS,
    PINNED_REVISIONS,
    GemmaProfile,
)
from venom_core.services.granite_operator import engine
from venom_core.services.granite_operator.contract import (
    TrainingProfile,
    digest,
    file_digest,
    write_json,
)
from venom_core.services.remote_training import artifacts, host, worker, worker_support

GRANITE = "ibm-granite/granite-4.2-3b"
GEMMA_MODELS = (MODEL, E4B_MODEL, BOLT_MODEL)


def fail_granite(*args, **kwargs):
    pytest.fail("Gemma flow incorrectly selected a Granite-only contract")


def _bolt_recipe():
    return training.GemmaTrainingRecipe(
        model=BOLT_MODEL,
        revision=PINNED_REVISIONS[BOLT_MODEL],
        context=512,
        quantization="bf16",
    )


def _bolt_profile_snapshot(snapshot: Path) -> GemmaProfile:
    snapshot.mkdir()
    contents = dict.fromkeys(BOLT_SNAPSHOT_FILES, "{}")
    contents["chat_template.jinja"] = "fixture template"
    contents["config.json"] = json.dumps(
        {
            "architectures": [MODEL_LOADERS[BOLT_MODEL]],
            "text_config": {"max_position_embeddings": 512},
        }
    )
    for name, content in contents.items():
        (snapshot / name).write_text(content)
    return GemmaProfile(
        model=BOLT_MODEL,
        revision=PINNED_REVISIONS[BOLT_MODEL],
        loader=MODEL_LOADERS[BOLT_MODEL],
        context=512,
        enable_thinking=False,
        files={
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in contents.items()
        },
    )


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
@pytest.mark.parametrize("execution", ("local", "remote"))
def test_run_stage_selects_actual_module_with_offline_environment_and_parent_lease(
    tmp_path, monkeypatch, model, execution
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
        "execution": execution,
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
    monkeypatch.setenv("VENOM_GEMMA_LOCAL_NF4", "inherited")
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
    assert kwargs["env"]["VENOM_GEMMA_LOCAL_NF4"] == (
        "1" if execution == "local" else "0"
    )
    assert kwargs["env"]["VENOM_GRANITE_RUN_ID"] == "job-1"
    assert kwargs["env"]["PYTHONPATH"] == host_config["code_root"]
    assert json.loads((result / "smoke-first.request.json").read_text()) == request


def test_local_nf4_preparation_applies_only_to_gemma_12b(monkeypatch):
    monkeypatch.setenv("VENOM_GEMMA_LOCAL_NF4", "1")
    for model in GEMMA_MODELS:
        for precision in ("nf4", "bf16"):
            recipe = training.GemmaTrainingRecipe(model=model, quantization=precision)
            assert training_worker._local_nf4_memory(recipe) == (
                model == MODEL and precision == "nf4"
            )
    monkeypatch.setenv("VENOM_GEMMA_LOCAL_NF4", "0")
    assert not training_worker._local_nf4_memory(training.GemmaTrainingRecipe())


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


def test_bolt_execution_identity_uses_pinned_weight_hashes(tmp_path, monkeypatch):
    snapshot = tmp_path / PINNED_REVISIONS[BOLT_MODEL]
    profile = _bolt_profile_snapshot(snapshot)
    recipe = training.GemmaTrainingRecipe.for_profile(profile)
    hashes = {"model-00001-of-00001.safetensors": "a" * 64}
    monkeypatch.setattr(training, "snapshot_weight_hashes", lambda path, model: hashes)
    monkeypatch.setattr(training, "inspect_dependencies", lambda: {"status": "PASS"})

    identity = training.execution_identity(
        profile,
        recipe,
        {"encoded_release_sha256": "b" * 64},
        snapshot,
    )

    assert identity["weights"] == hashes
    assert identity["model_profile"]["model"] == BOLT_MODEL


def test_bolt_snapshot_rejects_unpinned_weight_shards(tmp_path):
    first = "model-00001-of-00001.safetensors"
    second = "model-frozen-shared-kv.safetensors"
    (tmp_path / first).write_bytes(b"unqualified weights")
    (tmp_path / second).write_bytes(b"unqualified shared weights")
    (tmp_path / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"first": first, "shared": second}})
    )

    with pytest.raises(ValueError, match="bolt_training_shard_hash_mismatch"):
        training.snapshot_weight_hashes(tmp_path, BOLT_MODEL)


def test_bolt_structure_inspection_uses_native_loader_and_meta_tensors(monkeypatch):
    class FakeParameter:
        def __init__(self, requires_grad=False):
            self.device = SimpleNamespace(type="meta")
            self.requires_grad = requires_grad

        def numel(self):
            return 8

    module_names = [
        f"model.language_model.layers.0.self_attn.{name}"
        for name in ("q_proj", "k_proj", "v_proj", "o_proj")
    ]

    class FakeModel:
        def __init__(self, config):
            self.config = config
            self.base_parameter = FakeParameter()

        def named_modules(self):
            return [(name, self) for name in module_names]

        def parameters(self):
            return [self.base_parameter]

    class FakeAdapted:
        def __init__(self, model):
            self.model = model
            self.lora_parameter = FakeParameter(requires_grad=True)

        def parameters(self):
            return [self.model.base_parameter, self.lora_parameter]

        def named_parameters(self):
            return [
                ("base.weight", self.model.base_parameter),
                ("base.lora_A", self.lora_parameter),
            ]

    config = SimpleNamespace(
        architectures=[MODEL_LOADERS[BOLT_MODEL]],
        text_config=SimpleNamespace(num_hidden_layers=1),
    )
    transformers = ModuleType("transformers")
    transformers.AutoConfig = SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: config
    )
    transformers.Gemma4ForConditionalGeneration = FakeModel
    peft = ModuleType("peft")
    peft.LoraConfig = lambda **kwargs: kwargs
    peft.get_peft_model = lambda model, config: FakeAdapted(model)
    accelerate = ModuleType("accelerate")
    accelerate.init_empty_weights = lambda **kwargs: nullcontext()
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "peft", peft)
    monkeypatch.setitem(sys.modules, "accelerate", accelerate)

    result = training_worker.inspect_structure(Path("snapshot"), _bolt_recipe())

    assert result["loader"] == "FakeModel"
    assert result["target_modules"] == sorted(module_names)
    assert result["parameter_count"] == 8
    assert result["model_weights_loaded"] is False
    assert result["meta_lora_rank"] == _bolt_recipe().rank
    assert result["gpu_qualified"] is False


def test_local_nf4_weight_reader_rewrites_only_the_pinned_file_and_restores(
    tmp_path, monkeypatch
):
    modeling_utils = SimpleNamespace(
        safe_open=lambda filename, *args, **kwargs: kwargs["backend"]
    )
    transformers = ModuleType("transformers")
    transformers.modeling_utils = modeling_utils
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    target = tmp_path / "model.safetensors"
    other = tmp_path / "other.safetensors"
    original = modeling_utils.safe_open

    with training_worker._pread_local_weights(tmp_path):
        assert modeling_utils.safe_open(target, backend="mmap") == "pread"
        assert modeling_utils.safe_open(other, backend="mmap") == "mmap"
        assert modeling_utils.safe_open(target, backend="pread") == "pread"
    assert modeling_utils.safe_open is original

    def fail_during_read():
        with training_worker._pread_local_weights(tmp_path):
            raise RuntimeError("restore")

    with pytest.raises(RuntimeError, match="restore"):
        fail_during_read()
    assert modeling_utils.safe_open is original


def test_local_nf4_preparation_freezes_base_and_checks_architecture():
    class FakeBase:
        is_loaded_in_4bit = True
        config = SimpleNamespace(
            text_config=SimpleNamespace(model_type="gemma4_unified_text")
        )

        def __init__(self):
            self.gradient_options = None
            self.requires_grad_value = None

        def requires_grad_(self, value):
            self.requires_grad_value = value

        def gradient_checkpointing_enable(self, **kwargs):
            self.gradient_options = kwargs

    base = FakeBase()
    training_worker._prepare_local_nf4(base, gradient_checkpointing=True)
    assert base.requires_grad_value is False
    assert base.gradient_options == {
        "gradient_checkpointing_kwargs": {"use_reentrant": False}
    }

    without_checkpointing = FakeBase()
    training_worker._prepare_local_nf4(
        without_checkpointing, gradient_checkpointing=False
    )
    assert without_checkpointing.gradient_options is None

    invalid = FakeBase()
    invalid.is_loaded_in_4bit = False
    with pytest.raises(RuntimeError, match="gemma_local_nf4_model_mismatch"):
        training_worker._prepare_local_nf4(invalid, gradient_checkpointing=False)


def test_bolt_session_stops_before_loading_when_gpu_memory_is_too_small(
    tmp_path, monkeypatch
):
    torch = ModuleType("torch")
    torch.manual_seed = lambda seed: None
    torch.cuda = SimpleNamespace(manual_seed_all=lambda seed: None)
    torch.bfloat16 = object()
    peft = ModuleType("peft")
    peft.PeftModel = object
    peft.get_peft_model = lambda *args, **kwargs: None
    peft.prepare_model_for_kbit_training = lambda *args, **kwargs: None
    transformers = ModuleType("transformers")
    transformers.AutoTokenizer = object
    transformers.BitsAndBytesConfig = object
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "peft", peft)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setattr(training_worker, "require_owner", lambda: None)
    monkeypatch.setattr(
        training_worker,
        "probe_runtime",
        lambda: {"gpu_memory": BOLT_WEIGHT_BYTES - 1},
    )
    recipe = _bolt_recipe()

    with pytest.raises(
        RuntimeError, match="bolt_training_gpu_memory_below_weight_size"
    ):
        training_worker.GemmaSession(recipe, tmp_path)


def test_attention_implementation_is_selected_by_model_variant():
    e4b_attention = {
        "": "sdpa",
        "audio_config": "eager",
    }
    assert training_worker._attention_implementation(E4B_MODEL) == e4b_attention
    assert training_worker._attention_implementation(BOLT_MODEL) == e4b_attention
    assert training_worker._attention_implementation(MODEL) == "sdpa"
