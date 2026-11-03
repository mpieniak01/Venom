"""Contract tests run no model, GPU, network, provider or shell operation."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from venom_core.services.gemma4_operator import training
from venom_core.services.gemma4_operator import training_worker as worker
from venom_core.services.gemma4_operator.profile import GemmaProfile
from venom_core.services.granite_operator.contract import file_digest, write_json


@pytest.fixture(params=["12b", "e4b"])
def profile(request) -> GemmaProfile:
    name = (
        "gemma4_operator_profile.json"
        if request.param == "12b"
        else "gemma4_operator_e4b_profile.json"
    )
    return GemmaProfile.load(Path("config") / name)


@pytest.mark.parametrize("precision", ["bf16", "nf4"])
def test_native_recipe_selects_gemma_loader_and_text_targets(profile, precision):
    recipe = training.GemmaTrainingRecipe.for_profile(profile, quantization=precision)
    recipe.validate_profile(profile)
    identity = recipe.identity()
    assert identity["loader"] == profile.loader
    assert identity["revision"] == profile.revision
    assert identity["modality"] == "text"
    assert training.recipe_from_identity(identity) == recipe
    assert training.dependency_spec()["qualification"] == "remote_smoke_required"


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "gemma4:latest"},
        {"revision": "0" * 40},
        {"quantization": "q4_K_M"},
        {"context": True},
        {"rank": False},
        {"dropout": -0.01},
        {"dropout": float("nan")},
        {"learning_rate": True},
        {"gradient_checkpointing": "yes"},
        {"row_order": "sequential"},
    ],
)
def test_recipe_rejects_non_native_or_unsafe_configuration(changes):
    recipe = training.GemmaTrainingRecipe(**changes)
    with pytest.raises(ValueError):
        recipe.validate()


@pytest.mark.parametrize(
    "stage_request",
    [
        {"schema_version": True, "stage": "train", "updates": 125},
        {"schema_version": 1, "stage": "train"},
        {"schema_version": 1, "stage": "train", "updates": True},
        {"schema_version": 1, "stage": "resume", "updates": 1},
        {"schema_version": 1, "stage": "smoke", "updates": 1, "checkpoint": "old"},
        {"schema_version": 1, "stage": "activate", "updates": 0},
        {"schema_version": 1, "stage": "preflight", "updates": 1},
    ],
)
def test_stage_budget_is_explicit_and_never_enables_activation(stage_request):
    with pytest.raises(ValueError):
        training.validate_request(stage_request)


def test_meta_target_mapping_never_selects_vision_or_audio():
    names = [
        "model.language_model.layers.0.self_attn." + name
        for name in ("q_proj", "k_proj", "v_proj", "o_proj")
    ]
    names += ["model.vision_tower.q_proj", "model.audio_tower.q_proj"]
    fake = SimpleNamespace(named_modules=lambda: [(name, None) for name in names])
    assert worker.matched_targets(fake) == sorted(names[:4])


def test_missing_native_projection_is_a_blocker():
    fake = SimpleNamespace(named_modules=lambda: [("model.vision_tower.q_proj", None)])
    with pytest.raises(RuntimeError, match="text_targets_missing"):
        worker.matched_targets(fake)


class FakeSession:
    """Only tests dispatch/state contracts, not GPU qualification."""

    def __init__(self, recipe, snapshot, adapter):
        self.step = 0
        self.target_tokens = 0
        self.logs = []
        self.torch = SimpleNamespace(equal=lambda left, right: left == right)

    def restore(self, adapter, row, fingerprint):
        receipt = training.verified_checkpoint(adapter, fingerprint)
        self.step = receipt["step"]
        return True

    def evaluate(self, rows):
        return {"assistant_nll": 1.0, "target_tokens": 1}

    def train(self, rows, updates, *, families):
        assert families == ["diagnosis"]
        self.step += updates
        self.target_tokens += updates
        self.logs.append({"step": self.step})
        return 0.01

    def checks(self):
        return {"mask": True, "updated_adapter": True, "frozen_base": True}

    def probe(self, row, disable=False):
        return 0 if disable else 1

    def context_backward(self, row):
        return {"tokens": 4096, "supervised_tokens": 1, "loss": 1.0}

    def save(self, path, row, fingerprint):
        path.mkdir()
        for name, value in {
            "adapter_config.json": "{}",
            "adapter_model.safetensors": "fake",
            "training-state.pt": "fake optimizer and RNG",
            "README.md": "PEFT model card",
        }.items():
            (path / name).write_text(value)
        write_json(
            path / "receipt.json",
            {
                "fingerprint": fingerprint,
                "step": self.step,
                "files": {p.name: file_digest(p) for p in path.iterdir()},
            },
        )


@pytest.fixture
def prepared(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    recipe = training.GemmaTrainingRecipe.for_profile(profile)
    document = {"model_profile": profile.identity(), "encoded_release_sha256": "a" * 64}
    manifest = tmp_path / "data-manifest.json"
    write_json(manifest, document)
    row = {
        "problem_group": "diagnosis",
        "input_ids": [1, 2, 3],
        "attention_mask": [1, 1, 1],
        "labels": [-100, -100, 3],
    }
    monkeypatch.setattr(
        worker,
        "load_encoded",
        lambda path, selected: (
            document,
            {"train": [row], "validation": [row]},
        ),
    )
    monkeypatch.setattr(
        worker,
        "execution_identity",
        lambda *args: {
            "model_profile": profile.identity(),
            "environment": {"status": "PASS", "versions": {"fake": "1"}},
        },
    )
    monkeypatch.setattr(
        worker,
        "inspect_structure",
        lambda path: {
            "loader": profile.loader,
            "model_weights_loaded": False,
        },
    )
    request = {
        "stage": "smoke-first",
        "updates": 2,
        "checkpoint": None,
        "profile": recipe.identity(),
        "data_root": str(tmp_path),
        "manifest": str(manifest),
        "snapshot": str(tmp_path / training.REVISION),
        "output": str(tmp_path / "smoke-first"),
        "dataset": "gemma4",
        "qualification": None,
    }

    def hardware():
        return {"gpu": "FAKE", "gpu_memory": 0, "cuda": "fake"}

    def run(body, factory=FakeSession):
        return worker.run(
            body,
            session_factory=factory,
            runtime_probe=hardware,
            owner_check=lambda: None,
        )

    return request, run


def test_existing_coordinator_request_normalizes_without_changing_manifest(prepared):
    request, _ = prepared
    normalized = worker.normalize_request(request)
    assert normalized["stage"] == "smoke"
    assert normalized["encoded_release"] == request["manifest"]
    assert normalized["recipe"]["quantization"] == "nf4"


def test_edited_target_identity_is_rejected(prepared):
    request, _ = prepared
    altered = copy.deepcopy(request)
    altered["profile"]["target_modules"] = "all-linear"
    with pytest.raises(ValueError, match="profile_mismatch"):
        worker.normalize_request(altered)


def test_atomic_smoke_resume_train_and_seal_reuses_existing_receipts(
    prepared, tmp_path
):
    request, run = prepared
    first = run(request)
    resumed = {
        **request,
        "stage": "smoke-resume",
        "updates": 1,
        "checkpoint": first["checkpoint"],
        "output": str(tmp_path / "smoke-resume"),
    }
    second = run(resumed)
    artifacts = {
        "smoke-first/metrics.json": file_digest(tmp_path / "smoke-first/metrics.json"),
        "smoke-resume/metrics.json": file_digest(
            tmp_path / "smoke-resume/metrics.json"
        ),
    }
    proof = training.qualification(second, first, artifacts)
    assert proof["status"] == "PASS"
    assert proof["tool_loop_qualified"] is False
    assert proof["activation_allowed"] is False
    proof_path = tmp_path / "qualification.json"
    write_json(proof_path, proof)
    trained = run(
        {
            **request,
            "stage": "train-first",
            "updates": 7,
            "qualification": str(proof_path),
            "output": str(tmp_path / "train-first"),
        }
    )
    assert trained["initial_step"] == 0
    assert trained["global_step"] == 7
    assert not (tmp_path / "train-first/.checkpoint-pending").exists()
    later = run(
        {
            **request,
            "stage": "train-resume",
            "updates": 3,
            "checkpoint": trained["checkpoint"],
            "qualification": str(proof_path),
            "output": str(tmp_path / "train-resume"),
        }
    )
    assert later["initial_step"] == 7
    assert later["global_step"] == 10
    seal = run(
        {
            **request,
            "stage": "seal",
            "updates": 0,
            "checkpoint": later["checkpoint"],
            "output": str(tmp_path / "seal"),
        }
    )
    assert seal["checkpoint_receipt"]["step"] == 10
    assert seal["activation_allowed"] is False
    assert seal["evaluation_required"] is True


def test_training_without_remote_smoke_never_constructs_model(prepared, tmp_path):
    request, run = prepared
    body = {
        **request,
        "stage": "train-first",
        "updates": 1,
        "output": str(tmp_path / "train-no-smoke"),
    }
    constructed = []

    def forbidden(*args):
        constructed.append(True)
        raise AssertionError("model must not be loaded")

    with pytest.raises((KeyError, ValueError)):
        run(body, forbidden)
    assert constructed == []
    assert (
        json.loads((tmp_path / "train-no-smoke/status.json").read_text())["state"]
        == "failed"
    )


def test_training_failure_preserves_stage_and_does_not_mark_success(prepared, tmp_path):
    request, run = prepared

    class Failing(FakeSession):
        def train(self, rows, updates, *, families):
            raise RuntimeError("simulated")

    with pytest.raises(RuntimeError, match="simulated"):
        run(request, Failing)
    output = Path(request["output"])
    assert json.loads((output / "status.json").read_text())["state"] == "failed"
    assert not (output / "checkpoint").exists()


def test_checkpoint_tampering_blocks_before_peft_load(prepared):
    request, run = prepared
    result = run(request)
    checkpoint = Path(result["checkpoint"])
    (checkpoint / "adapter_model.safetensors").write_text("tampered")
    fingerprint = result["fingerprint"]
    with pytest.raises(ValueError, match="hash_mismatch"):
        training.verified_checkpoint(checkpoint, fingerprint)


def test_checkpoint_unlisted_payload_is_rejected(prepared):
    request, run = prepared
    result = run(request)
    checkpoint = Path(result["checkpoint"])
    (checkpoint / "extra.py").write_text("unlisted")
    fingerprint = result["fingerprint"]
    with pytest.raises(ValueError, match="file_set_changed"):
        training.verified_checkpoint(checkpoint, fingerprint)


def test_failed_or_missing_qualification_is_not_training_proof():
    document = {
        "kind": "gemma4_training_qualification",
        "status": "PASS",
        "fingerprint": "a" * 64,
        "checks": {},
    }
    fingerprint = document["fingerprint"]
    with pytest.raises(ValueError, match="remote_smoke_required"):
        training.require_qualification(document, fingerprint)


def test_preflight_is_preparation_and_never_constructs_model(prepared, tmp_path):
    request, run = prepared
    body = {
        **request,
        "stage": "preflight",
        "updates": 0,
        "output": str(tmp_path / "preflight"),
    }

    def forbidden(*args):
        raise AssertionError("preflight must not load a model")

    result = run(body, forbidden)
    assert result["status"] == "PREPARED"
    assert result["model_loaded"] is False
    assert result["gpu_qualified"] is False
    assert result["activation_allowed"] is False


@pytest.mark.parametrize(
    "owner,quarantine,cancelled,pid_offset,expected",
    [
        ("gemma-training", 0, 0, 0, True),
        ("granite-training", 0, 0, 0, False),
        ("gemma-training", 1, 0, 0, False),
        ("gemma-training", 0, 1, 0, False),
        ("gemma-training", 0, 0, 1, False),
    ],
)
def test_worker_checks_actual_parent_gemma_admission(
    monkeypatch, tmp_path, owner, quarantine, cancelled, pid_offset, expected
):
    import os
    import sqlite3

    database = tmp_path / "admission.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE lease(pid INTEGER,owner TEXT,engine TEXT,run_id TEXT,"
            "quarantine INTEGER,cancelled INTEGER)"
        )
        connection.execute(
            "INSERT INTO lease VALUES(?,?,?,?,?,?)",
            (os.getppid() + pid_offset, owner, owner, "run1", quarantine, cancelled),
        )
    monkeypatch.setenv("VENOM_GRANITE_ADMISSION_DB", str(database))
    monkeypatch.setenv("VENOM_GRANITE_RUN_ID", "run1")
    if expected:
        worker.require_owner()
    else:
        with pytest.raises(RuntimeError, match="reservation_missing"):
            worker.require_owner()


def test_missing_qualification_fingerprint_cannot_match_itself():
    proof = {
        "kind": "gemma4_training_qualification",
        "status": "PASS",
        "fingerprint": None,
    }
    with pytest.raises(ValueError, match="remote_smoke_required"):
        training.require_qualification(proof, None)


def test_incomplete_native_weight_index_is_blocked_before_gpu(tmp_path):
    (tmp_path / "model-00001-of-00002.safetensors").write_bytes(b"first")
    write_json(
        tmp_path / "model.safetensors.index.json",
        {
            "weight_map": {
                "first.weight": "model-00001-of-00002.safetensors",
                "second.weight": "model-00002-of-00002.safetensors",
            },
        },
    )
    with pytest.raises(ValueError, match="weights_incomplete"):
        training.snapshot_weights(tmp_path)


def test_extra_or_unindexed_weight_shard_is_not_a_complete_base(tmp_path):
    (tmp_path / "random.safetensors").write_bytes(b"not a base")
    with pytest.raises(ValueError, match="weights_index_missing"):
        training.snapshot_weights(tmp_path)


def test_native_weight_index_cannot_escape_snapshot(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"fake")
    write_json(
        tmp_path / "model.safetensors.index.json",
        {
            "weight_map": {"first.weight": "../other.safetensors"},
        },
    )
    with pytest.raises(ValueError, match="weights_incomplete"):
        training.snapshot_weights(tmp_path)


def test_complete_native_weight_index_is_supported(tmp_path):
    weight = tmp_path / "model-00001-of-00001.safetensors"
    weight.write_bytes(b"fake")
    write_json(
        tmp_path / "model.safetensors.index.json",
        {
            "weight_map": {"first.weight": weight.name},
        },
    )
    assert training.snapshot_weights(tmp_path) == [weight]


def test_combined_smoke_requires_nonempty_sealed_artifacts(prepared, tmp_path):
    request, run = prepared
    first = run(request)
    second = run(
        {
            **request,
            "stage": "smoke-resume",
            "updates": 1,
            "checkpoint": first["checkpoint"],
            "output": str(tmp_path / "smoke-resume"),
        }
    )
    receipt = training.qualification(second, first, {})
    assert receipt["status"] == "FAIL"
    fingerprint = second["fingerprint"]
    with pytest.raises(ValueError):
        training.require_qualification(receipt, fingerprint)
    assert not (tmp_path / "smoke-resume/qualification.json").exists()


def test_cross_variant_checkpoint_is_rejected(prepared):
    request, run = prepared
    result = run(request)
    checkpoint = Path(result["checkpoint"])
    other_identity = {"model_profile": "other-Gemma-variant"}
    other_fingerprint = training.identity_fingerprint(other_identity, {"gpu": "FAKE"})
    with pytest.raises(ValueError, match="identity_mismatch"):
        training.verified_checkpoint(checkpoint, other_fingerprint)


def test_recipe_cannot_accept_other_variants_profile(profile):
    other = GemmaProfile.load(
        Path("config")
        / (
            "gemma4_operator_e4b_profile.json"
            if profile.model == training.MODEL
            else "gemma4_operator_profile.json"
        )
    )
    recipe = training.GemmaTrainingRecipe.for_profile(profile)
    with pytest.raises(ValueError, match="profile_mismatch"):
        recipe.validate_profile(other)


def _smoke_receipt(request, run, tmp_path):
    first = run(request)
    resumed = run(
        {
            **request,
            "stage": "smoke-resume",
            "updates": 1,
            "checkpoint": first["checkpoint"],
            "output": str(tmp_path / "smoke-resume"),
        }
    )
    artifacts = {
        "smoke-first/metrics.json": file_digest(tmp_path / "smoke-first/metrics.json"),
        "smoke-resume/metrics.json": file_digest(
            tmp_path / "smoke-resume/metrics.json"
        ),
    }
    return training.qualification(resumed, first, artifacts)


def _reseal_smoke_metrics(receipt, tmp_path):
    for name, directory in (("first", "smoke-first"), ("resumed", "smoke-resume")):
        path = tmp_path / directory / "metrics.json"
        write_json(path, receipt["smoke_metrics"][name])
        receipt["artifacts"][directory + "/metrics.json"] = file_digest(path)


def test_receipt_checks_cannot_override_sealed_failed_stage(prepared, tmp_path):
    request, run = prepared
    receipt = _smoke_receipt(request, run, tmp_path)
    receipt["smoke_metrics"]["first"]["checks"]["frozen_base"] = False
    _reseal_smoke_metrics(receipt, tmp_path)
    fingerprint = receipt["fingerprint"]
    with pytest.raises(ValueError, match="checks_inconsistent"):
        training.require_qualification(receipt, fingerprint)


def test_training_proof_is_bound_to_current_validated_mask(prepared, tmp_path):
    request, run = prepared
    receipt = _smoke_receipt(request, run, tmp_path)
    for metrics in receipt["smoke_metrics"].values():
        metrics["mask_evidence"]["sequences"]["train"] += 1
    _reseal_smoke_metrics(receipt, tmp_path)
    proof_path = tmp_path / "qualification.json"
    write_json(proof_path, receipt)
    body = {
        **request,
        "stage": "train-first",
        "updates": 1,
        "qualification": str(proof_path),
        "output": str(tmp_path / "unmatched-mask"),
    }

    def forbidden(*args):
        raise AssertionError("mismatched proof must not construct a model")

    with pytest.raises(ValueError, match="qualification_mask_changed"):
        run(body, forbidden)


@pytest.mark.parametrize("device", ["cpu", "meta"])
def test_gemma_runtime_never_accepts_parameter_offload(device):
    from types import SimpleNamespace

    model = SimpleNamespace(
        named_parameters=lambda: [
            ("model.weight", SimpleNamespace(device=SimpleNamespace(type=device)))
        ],
        hf_device_map={"": 0},
    )
    with pytest.raises(RuntimeError, match="cuda_placement_required"):
        worker.require_cuda_placement(model)


@pytest.mark.parametrize("placement", ["cpu", "disk", "meta", "cuda:disk", False])
def test_gemma_runtime_rejects_device_map_offload_even_with_cuda_parameters(placement):
    from types import SimpleNamespace

    model = SimpleNamespace(
        named_parameters=lambda: [
            ("model.weight", SimpleNamespace(device=SimpleNamespace(type="cuda")))
        ],
        hf_device_map={"model": placement},
    )
    with pytest.raises(RuntimeError, match="offload_forbidden"):
        worker.require_cuda_placement(model)


def test_gemma_runtime_reports_gpu_required_and_no_cpu_fallback():
    from types import SimpleNamespace

    model = SimpleNamespace(
        named_parameters=lambda: [
            ("model.weight", SimpleNamespace(device=SimpleNamespace(type="cuda")))
        ],
        hf_device_map={"model": "cuda:0"},
    )
    assert worker.require_cuda_placement(model) == {
        "gpu_required": True,
        "cpu_fallback": False,
        "disk_offload": False,
        "parameter_tensors_on_cuda": 1,
    }


def test_collected_checkpoint_preserves_peft_card_and_full_resume_receipt(
    prepared, tmp_path
):
    import shutil

    from venom_core.services.remote_training.artifacts import _files

    request, run = prepared
    result = run(request)
    source = Path(request["output"])
    selected = _files(source, include_checkpoint=True)
    assert "checkpoint/README.md" in selected
    downloaded = tmp_path / "downloaded"
    for name in selected:
        destination = downloaded / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    receipt = training.verified_checkpoint(
        downloaded / "checkpoint", result["fingerprint"]
    )
    assert "README.md" in receipt["files"]
    session = FakeSession(None, None, None)
    assert session.restore(downloaded / "checkpoint", {}, result["fingerprint"])
    assert session.step == result["global_step"]


def test_checkpoint_collection_only_allows_root_peft_card_markdown(tmp_path):
    from venom_core.services.remote_training.artifacts import _files

    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    write_json(checkpoint / "receipt.json", {})
    (checkpoint / "README.md").write_text("PEFT card")
    (checkpoint / "private-notes.md").write_text("excluded")
    (checkpoint / "nested").mkdir()
    (checkpoint / "nested/README.md").write_text("excluded")
    selected = _files(tmp_path, include_checkpoint=True)
    assert "checkpoint/README.md" in selected
    assert "checkpoint/private-notes.md" not in selected
    assert "checkpoint/nested/README.md" not in selected


@pytest.fixture
def native_provider(monkeypatch):
    """A remote-library double exercises actual loader admission and placement."""
    import sys

    from venom_core.services.granite_operator import engine

    state = SimpleNamespace(
        cuda_available=True,
        base_device="cuda",
        unexpected_trainable=False,
        loaders=[],
        lora=[],
        prepared=[],
        restored=[],
        optimizers=[],
        owners=[],
    )

    class Base:
        def __init__(self):
            self.parameter = SimpleNamespace(
                requires_grad=True,
                device=SimpleNamespace(type=state.base_device),
            )
            self.config = SimpleNamespace(use_cache=True)
            self.hf_device_map = {"": 0}
            self.checkpointing = []

        def named_modules(self):
            return [
                ("model.language_model.layers.0.self_attn." + name, None)
                for name in ("q_proj", "k_proj", "v_proj", "o_proj")
            ]

        def named_parameters(self):
            return [("base.weight", self.parameter)]

        def requires_grad_(self, enabled):
            self.parameter.requires_grad = enabled

        def gradient_checkpointing_enable(self, **options):
            self.checkpointing.append(options)

        def enable_input_require_grads(self):
            self.input_gradients_enabled = True

    class Adapter:
        def __init__(self, base):
            self.base = base
            self.hf_device_map = base.hf_device_map
            self.adapter_parameter = SimpleNamespace(
                requires_grad=True,
                device=SimpleNamespace(type="cuda"),
            )

        def named_parameters(self):
            parameters = [
                *self.base.named_parameters(),
                ("text.lora_A.weight", self.adapter_parameter),
            ]
            if state.unexpected_trainable:
                parameters.append(
                    (
                        "surprise.weight",
                        SimpleNamespace(
                            requires_grad=True,
                            device=SimpleNamespace(type="cuda"),
                        ),
                    )
                )
            return parameters

        def parameters(self):
            return [parameter for _, parameter in self.named_parameters()]

    def loader_for(name):
        class Loader:
            @staticmethod
            def from_pretrained(snapshot, **options):
                state.loaders.append((name, snapshot, options))
                return Base()

        return Loader

    def make_lora(**options):
        config = SimpleNamespace(**options)
        state.lora.append(config)
        return config

    def prepare(base, **options):
        state.prepared.append(options)
        base.requires_grad_(False)
        return base

    def attach(base, config):
        return Adapter(base)

    def restore(base, path, **options):
        state.restored.append((path, options))
        return Adapter(base)

    def optimizer(parameters, **options):
        state.optimizers.append((parameters, options))
        return SimpleNamespace()

    fake_torch = SimpleNamespace(
        bfloat16="bf16",
        manual_seed=lambda seed: None,
        cuda=SimpleNamespace(
            is_available=lambda: state.cuda_available,
            is_bf16_supported=lambda: True,
            get_device_name=lambda index: "FAKE GPU",
            get_device_properties=lambda index: SimpleNamespace(
                total_memory=48 * 1024**3
            ),
            manual_seed_all=lambda seed: None,
        ),
        version=SimpleNamespace(cuda="fake"),
        optim=SimpleNamespace(AdamW=optimizer),
    )
    fake_transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(
            from_pretrained=lambda *args, **kwargs: SimpleNamespace(pad_token_id=0)
        ),
        BitsAndBytesConfig=lambda **options: SimpleNamespace(**options),
        Gemma4UnifiedForConditionalGeneration=loader_for(
            "Gemma4UnifiedForConditionalGeneration"
        ),
        Gemma4ForConditionalGeneration=loader_for("Gemma4ForConditionalGeneration"),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(
        sys.modules,
        "peft",
        SimpleNamespace(
            LoraConfig=make_lora,
            get_peft_model=attach,
            prepare_model_for_kbit_training=prepare,
            PeftModel=SimpleNamespace(from_pretrained=restore),
        ),
    )
    monkeypatch.setattr(worker, "require_owner", lambda: state.owners.append(True))
    monkeypatch.setattr(
        worker, "tensor_hash", lambda parameters: "fake frozen-base hash"
    )
    monkeypatch.setattr(engine, "tensor_hash", lambda parameters: "fake adapter hash")
    return state


@pytest.mark.parametrize("precision", ["nf4", "bf16"])
def test_actual_session_uses_selected_loader_precision_and_gpu_only(
    profile, native_provider, tmp_path, precision
):
    recipe = training.GemmaTrainingRecipe.for_profile(
        profile,
        quantization=precision,
        rank=32,
        alpha=64,
        learning_rate=0.00001,
    )
    session = worker.GemmaSession(recipe, tmp_path / recipe.revision)
    loader, snapshot, options = native_provider.loaders[0]
    assert loader == profile.loader
    assert snapshot.name == profile.revision
    assert options["device_map"] == {"": 0}
    assert options["local_files_only"] is True
    assert options["trust_remote_code"] is False
    assert options["dtype"] == "bf16"
    assert session.profile.quantization == precision
    assert native_provider.owners == [True]
    assert session.placement["gpu_required"] is True
    assert session.placement["cpu_fallback"] is False
    assert native_provider.lora[0].r == 32
    assert native_provider.lora[0].lora_alpha == 64
    assert native_provider.optimizers[0][1]["lr"] == 0.00001
    if precision == "nf4":
        quantization = options["quantization_config"]
        assert quantization.bnb_4bit_quant_type == "nf4"
        assert quantization.bnb_4bit_compute_dtype == "bf16"
        assert native_provider.prepared[0]["use_gradient_checkpointing"] is True
    else:
        assert "quantization_config" not in options
        assert native_provider.prepared == []
        assert session.model.base.checkpointing == [
            {"gradient_checkpointing_kwargs": {"use_reentrant": False}}
        ]


def test_native_session_rejects_unavailable_gpu_before_loader(
    profile, native_provider, tmp_path
):
    recipe = training.GemmaTrainingRecipe.for_profile(profile)
    native_provider.cuda_available = False
    snapshot = tmp_path / recipe.revision
    with pytest.raises(RuntimeError, match="cuda_bf16_required"):
        worker.GemmaSession(recipe, snapshot)
    assert native_provider.loaders == []
    assert native_provider.optimizers == []


def test_native_session_does_not_trust_provider_cpu_placement(
    profile, native_provider, tmp_path
):
    recipe = training.GemmaTrainingRecipe.for_profile(profile)
    native_provider.base_device = "cpu"
    snapshot = tmp_path / recipe.revision
    with pytest.raises(RuntimeError, match="cuda_placement_required"):
        worker.GemmaSession(recipe, snapshot)
    assert native_provider.lora == []
    assert native_provider.optimizers == []


def test_native_session_rejects_unexpected_trainable_base(
    profile, native_provider, tmp_path
):
    recipe = training.GemmaTrainingRecipe.for_profile(profile)
    native_provider.unexpected_trainable = True
    snapshot = tmp_path / recipe.revision
    with pytest.raises(RuntimeError, match="unexpected_trainable_base"):
        worker.GemmaSession(recipe, snapshot)
    assert native_provider.optimizers == []


def test_loading_native_adapter_does_not_fake_optimizer_resume(
    profile, native_provider, tmp_path
):
    recipe = training.GemmaTrainingRecipe.for_profile(profile)
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    write_json(
        checkpoint / "adapter_config.json",
        {
            "target_modules": training.target_modules_for(recipe.model),
        },
    )
    session = worker.GemmaSession(recipe, tmp_path / recipe.revision, checkpoint)
    assert native_provider.restored == [(checkpoint, {"is_trainable": True})]
    assert session.step == 0
    assert session.target_tokens == 0
