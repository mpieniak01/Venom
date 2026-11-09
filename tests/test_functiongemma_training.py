"""CPU doubles verify admission, frozen recipes and full-state checkpoint flow."""

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from venom_core.services.functiongemma import worker
from venom_core.services.functiongemma.profile import Recipe


def test_budget_and_validation():
    assert Recipe().budget(832)["total_updates"] == 156
    assert Recipe().budget(17)["updates_per_epoch"] == 2
    for options in (
        {"method": "qlora"},
        {"context": True},
        {"epochs": 4},
        {"seed": False},
        {"learning_rate": 0},
        {"dropout": float("nan")},
        {"revision": "wrong"},
    ):
        recipe_9 = Recipe(**options)
        with pytest.raises(ValueError):
            recipe_9.identity()
    recipe_1 = Recipe()
    with pytest.raises(ValueError):
        recipe_1.budget(0)
    assert len(Recipe().fingerprint) == 64


def test_fp32_recipe_changes_identity_and_requires_full_training():
    """Bind precision to recipe identity and restrict it to full training."""
    assert "parameter_dtype" not in Recipe().identity()
    recipe = Recipe(parameter_dtype="fp32")
    assert recipe.identity()["parameter_dtype"] == "fp32"
    assert recipe.fingerprint != Recipe().fingerprint
    for invalid in (
        Recipe(parameter_dtype="bf16"),
        Recipe(method="lora", parameter_dtype="fp32"),
    ):
        with pytest.raises(ValueError, match="parameter_dtype"):
            invalid.validate()


def test_environment(monkeypatch):
    monkeypatch.setattr(worker.platform, "python_version", lambda: "3.14.8")
    monkeypatch.setattr(
        worker.importlib.metadata, "version", lambda name: worker.VERSIONS[name]
    )
    assert worker.environment()["gpu_qualified"] is False
    monkeypatch.setattr(worker.platform, "python_version", lambda: "3.12")
    with pytest.raises(ValueError):
        worker.environment()


def request():
    return {"recipe": Recipe().identity(), "stage": "smoke", "gpu_authorized": True}


def test_request(monkeypatch):
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.setenv(key, "1")
    assert worker.validate_request(request()) == Recipe()
    for options in (
        {"stage": "wrong"},
        {"gpu_authorized": False},
        {"stage": "train"},
        {"stage": "resume", "qualification": "proof"},
        {"checkpoint": "unexpected"},
    ):
        request_body_10 = request()
        with pytest.raises(ValueError):
            worker.validate_request({**request_body_10, **options})
    monkeypatch.delenv("HF_HUB_OFFLINE")
    request_body_2 = request()
    with pytest.raises(ValueError):
        worker.validate_request(request_body_2)


def checkpoint(path):
    path.mkdir(parents=True)
    for name in (
        "trainer_state.json",
        "optimizer.pt",
        "scheduler.pt",
        "rng_state.pth",
        "model.safetensors",
    ):
        (path / name).write_text(
            json.dumps({"global_step": 1}) if name == "trainer_state.json" else "state"
        )


def test_seal(tmp_path):
    path = tmp_path / "checkpoint"
    checkpoint(path)
    worker._seal(path, "fp")
    assert worker.verify_checkpoint(path, "fp")["fingerprint"] == "fp"
    (path / "model.safetensors").write_text("tamper")
    with pytest.raises(ValueError):
        worker.verify_checkpoint(path, "fp")
    with pytest.raises(ValueError):
        worker.tree_hashes(tmp_path / "missing")
    (path / "alias").symlink_to(path / "optimizer.pt")
    with pytest.raises(ValueError):
        worker.tree_hashes(path)


def test_missing_resume_state(tmp_path):
    (tmp_path / "model.safetensors").write_text("x")
    with pytest.raises(ValueError, match="resume_state"):
        worker._seal(tmp_path, "fp")


def fake_runtime(monkeypatch, loads=None):
    """Substitute a minimal runtime for testing precision and optimizer state."""
    import sys

    counter = iter(range(100))
    monkeypatch.setattr(
        worker, "parameter_evidence", lambda model: {"p": next(counter)}
    )
    monkeypatch.setattr(worker, "probe_logits", lambda *a: "same_logits")

    cuda = NS(
        is_available=lambda: True,
        is_bf16_supported=lambda: True,
        empty_cache=lambda: None,
        reset_peak_memory_stats=lambda: None,
        max_memory_allocated=lambda: 123,
    )
    torch = NS(
        cuda=cuda, bfloat16="bf16", float32="torch.float32", tensor=lambda value: value
    )
    model = NS(
        config=NS(architectures=["Gemma3ForCausalLM"]),
        named_modules=lambda: [
            (name, None) for name in ("q_proj", "k_proj", "v_proj", "o_proj")
        ],
        parameters=lambda: [
            NS(device=NS(type="cuda"), requires_grad=True, dtype=torch.float32)
        ],
    )

    class Trainer:
        def __init__(self, **kwargs):
            self.args = kwargs["args"]
            self.state = NS(global_step=0)
            moment = NS(dtype=torch.float32)
            self.optimizer = NS(state={0: {"exp_avg": moment, "exp_avg_sq": moment}})

        def train(self, resume_from_checkpoint=None):
            self.state.global_step = getattr(self.args, "max_steps", 3)
            checkpoint(
                Path(self.args.output_dir)
                / ("checkpoint-" + str(self.state.global_step))
            )

    def load_model(*args, **kwargs):
        """Record the model load options for later assertions."""
        if loads is not None:
            loads.append(kwargs["dtype"])
        return model

    transformers = NS(
        AutoModelForCausalLM=NS(from_pretrained=load_model),
        AutoTokenizer=NS(
            from_pretrained=lambda *a, **k: NS(pad_token_id=0, chat_template="native")
        ),
        Trainer=Trainer,
        TrainingArguments=lambda **k: NS(**k),
        set_seed=lambda seed: None,
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(
        sys.modules,
        "peft",
        NS(
            LoraConfig=lambda **k: k,
            get_peft_model=lambda model, config: model,
            PeftModel=NS(from_pretrained=lambda model, *a, **k: model),
        ),
    )
    return model, torch


@pytest.mark.parametrize("method", ["full", "lora"])
def test_smoke_save_reload_resume(tmp_path, monkeypatch, method):
    fake_runtime(monkeypatch)
    recipe = Recipe(method=method)
    result = worker._execute(
        request(),
        recipe,
        {"train": [{}], "validation": [{}]},
        tmp_path,
        tmp_path / "out",
        "fp",
        None,
    )
    assert result["checks"] == {
        "save": True,
        "reload": True,
        "resume": True,
        "weights_updated": True,
    }
    assert result["qualified"] is True
    assert result["activation_allowed"] is False
    worker.verify_checkpoint(Path(result["checkpoint"]), "fp")


def test_full_fp32_training_uses_fp32_on_reload(tmp_path, monkeypatch):
    """Check that the full training checkpoint reloads at the requested precision."""
    loads = []
    fake_runtime(monkeypatch, loads)
    recipe = Recipe(parameter_dtype="fp32")
    result = worker._execute(
        request(),
        recipe,
        {"train": [{}], "validation": [{}]},
        tmp_path,
        tmp_path / "fp32",
        "fingerprint",
        None,
    )
    assert loads == ["torch.float32", "torch.float32"]
    assert result["precision"] == {
        "trainable_parameters": ["torch.float32"],
        "optimizer_moments": ["torch.float32"],
        "autocast": "torch.bfloat16",
    }
    assert result["checks"]["resume"]


def test_fp32_rejects_bf16_moments():
    """Reject optimizer moments that lost the requested FP32 precision."""
    model = NS(parameters=lambda: [NS(requires_grad=True, dtype="torch.float32")])
    optimizer = NS(state={0: {"exp_avg": NS(dtype="torch.bfloat16")}})
    with pytest.raises(RuntimeError, match="optimizer_precision"):
        worker.optimizer_precision(model, optimizer)


def test_training_and_cuda_rejection(tmp_path, monkeypatch):
    model, torch = fake_runtime(monkeypatch)
    result = worker._execute(
        {"stage": "train"},
        Recipe(),
        {"train": [{}], "validation": [{}]},
        tmp_path,
        tmp_path / "out",
        "fp",
        None,
    )
    assert not result["qualified"]
    torch.cuda.is_available = lambda: False
    request_body_3 = request()
    recipe_4 = Recipe()
    with pytest.raises(RuntimeError, match="cuda"):
        worker._execute(
            request_body_3, recipe_4, {}, tmp_path, tmp_path / "bad", "fp", None
        )
    torch.cuda.is_available = lambda: True
    model.config.architectures = ["Other"]
    request_body_5 = request()
    recipe_6 = Recipe()
    with pytest.raises(ValueError, match="architecture"):
        worker._execute(
            request_body_5, recipe_6, {}, tmp_path, tmp_path / "bad", "fp", None
        )


def test_collator_and_arguments():
    batch = worker.collate(
        [
            {"input_ids": [1, 2], "labels": [-100, 2], "attention_mask": [1, 1]},
            {"input_ids": [3], "labels": [3], "attention_mask": [1]},
        ],
        torch=NS(tensor=lambda x: x),
        pad_id=0,
    )
    assert batch["labels"][1] == [3, -100]
    assert (
        worker.trainer_arguments(Recipe(), Path("out"), smoke=False)["report_to"] == []
    )


def test_run_admission_and_binding(tmp_path, monkeypatch):
    import sys

    import venom_core.services.functiongemma.encoding as encoding

    fake_runtime(monkeypatch)
    monkeypatch.setattr(worker, "environment", lambda: {"status": "prepared"})
    monkeypatch.setattr(
        encoding,
        "validate_encoded_release",
        lambda *a, **k: {"train": [{}], "validation": [{}]},
    )
    monkeypatch.setattr(worker, "_execute", lambda *a: {"ok": True})
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.setenv(key, "1")
    snapshot = tmp_path / Recipe().revision
    snapshot.mkdir()
    (snapshot / "model.safetensors").write_text("weights")
    encoded = tmp_path / "encoded.json"
    encoded.write_text(
        json.dumps(
            {
                "tokenizer_template_sha256": __import__("hashlib")
                .sha256(b"native")
                .hexdigest()
            }
        )
    )
    body = {
        **request(),
        "snapshot": str(snapshot),
        "encoded_release": str(encoded),
        "output": str(tmp_path / "out"),
        "run_id": "test",
    }
    with pytest.raises(ValueError, match="shared_admission"):
        worker.run(body)
    monkeypatch.setenv("VENOM_GRANITE_ADMISSION_DB", str(tmp_path / "host.sqlite"))
    from contextlib import nullcontext

    lease = NS(operation=lambda **kw: nullcontext(), release=lambda: None)
    monkeypatch.setitem(
        sys.modules,
        "venom_core.services.runtime_admission",
        NS(RuntimeAdmission=lambda *a, **k: NS(acquire=lambda **kw: lease)),
    )
    assert worker.run(body) == {"ok": True}
    proof = tmp_path / "proof.json"
    proof.write_text(json.dumps({"fingerprint": "wrong", "qualified": True}))
    path_text_7 = str(proof)
    with pytest.raises(ValueError, match="smoke_mismatch"):
        worker.run({**body, "stage": "train", "qualification": path_text_7})
    path_text_8 = str(tmp_path)
    with pytest.raises(ValueError, match="pinned_snapshot"):
        worker.run({**body, "snapshot": path_text_8})


def test_parameter_and_logits_evidence(monkeypatch):
    import sys
    from contextlib import nullcontext

    import venom_core.services.granite_operator.engine as engine

    monkeypatch.setattr(
        engine,
        "tensor_hash",
        lambda named: str([(name, value) for name, value in named]),
    )
    model = NS(
        named_parameters=lambda: [
            ("a", NS(requires_grad=True)),
            ("b", NS(requires_grad=False)),
        ]
    )
    assert set(worker.parameter_evidence(model)) == {"a"}

    class Model:
        def eval(self):
            pass

        def __call__(self, **kwargs):
            return NS(logits=NS(float=lambda: "logits"))

    monkeypatch.setitem(
        sys.modules,
        "torch",
        NS(
            inference_mode=nullcontext,
            autocast=lambda **k: nullcontext(),
            bfloat16="bf16",
            tensor=lambda *a, **k: "tensor",
        ),
    )
    assert (
        worker.probe_logits(Model(), {"input_ids": [1], "attention_mask": [1]})
        == "[('logits', 'logits')]"
    )


def test_pinned_transformers_warmup_contract():
    recipe = Recipe(context=2048)
    full = worker.trainer_arguments(recipe, Path("out"), smoke=False)
    smoke = worker.trainer_arguments(recipe, Path("out"), smoke=True)
    assert "warmup_ratio" not in full
    assert full["warmup_steps"] == 0.05
    assert smoke["warmup_steps"] == 0.0


def test_warm_start_rejects_changed_weights_and_schedules_checkpoints(tmp_path):
    """Bind checkpoint digests and validate the requested milestone interval."""
    from venom_core.services.functiongemma.profile import INITIAL_WEIGHT_FILES
    from venom_core.services.granite_operator.contract import file_digest

    initial = tmp_path / "warm-start"
    initial.mkdir()
    for name in INITIAL_WEIGHT_FILES:
        (initial / name).write_text(name)
    hashes = {name: file_digest(initial / name) for name in INITIAL_WEIGHT_FILES}
    recipe = Recipe(initial_weights=hashes, checkpoint_interval=100, epochs=1)
    assert "initial_weights" not in Recipe().identity()
    assert Recipe(**recipe.identity()) == recipe
    assert recipe.budget(6396)["total_updates"] == 400
    assert worker.resolve_model_source(recipe, tmp_path / "base", tmp_path) == initial
    args = worker.trainer_arguments(recipe, tmp_path, smoke=False)
    assert args["save_strategy"] == "steps"
    assert args["save_steps"] == 100
    (initial / "model.safetensors").write_text("changed")
    with pytest.raises(ValueError, match="initial_weights_changed"):
        worker.resolve_model_source(recipe, tmp_path / "base", tmp_path)
    (initial / "model.safetensors").unlink()
    with pytest.raises(ValueError, match="initial_weights_missing"):
        worker.resolve_model_source(recipe, tmp_path / "base", tmp_path)
    with pytest.raises(ValueError, match="interval_budget_mismatch"):
        recipe.budget(16)


def test_warm_start_uses_checkpoint_weights_and_base_tokenizer(tmp_path, monkeypatch):
    """Load warm weights while keeping the pinned tokenizer source."""
    import sys

    model, _ = fake_runtime(monkeypatch)
    sources = {}

    def load_weights(path, **kwargs):
        """Capture the selected model weights directory."""
        sources["weights"] = path
        return model

    def load_tokenizer(path, **kwargs):
        """Capture the selected tokenizer directory."""
        sources["tokenizer"] = path
        return NS(pad_token_id=0)

    monkeypatch.setattr(
        sys.modules["transformers"].AutoModelForCausalLM,
        "from_pretrained",
        load_weights,
    )
    monkeypatch.setattr(
        sys.modules["transformers"].AutoTokenizer, "from_pretrained", load_tokenizer
    )
    base, initial = tmp_path / "base", tmp_path / "warm-start"
    transformers = sys.modules["transformers"]

    class MilestoneTrainer(transformers.Trainer):
        def train(self, resume_from_checkpoint=None):
            """Capture the parameters sent to the training executor."""
            super().train(resume_from_checkpoint)
            checkpoint(Path(self.args.output_dir) / "checkpoint-1")

    monkeypatch.setattr(transformers, "Trainer", MilestoneTrainer)
    records = {"train": [{}] * 48, "validation": [{}]}
    worker._execute(
        {"stage": "train"},
        Recipe(epochs=1, checkpoint_interval=1),
        records,
        base,
        tmp_path / "output",
        "bound",
        None,
        model_source=initial,
    )
    assert sources == {"weights": initial, "tokenizer": base}
    assert (
        worker.verify_checkpoint(tmp_path / "output/checkpoint-1", "bound")["step"] == 1
    )


def test_retention_targets_bind_teacher_and_encoded_training_anchor():
    """Reject retention targets from another teacher or encoded sample."""
    from copy import deepcopy

    from venom_core.services.functiongemma.profile import INITIAL_WEIGHT_FILES
    from venom_core.services.functiongemma.retention import ACTIONS, targets_for

    weights = dict.fromkeys(INITIAL_WEIGHT_FILES, "a" * 64)
    recipe = Recipe(
        initial_weights=weights, parameter_dtype="fp32", retention_weight=0.5
    )
    recipe.validate()
    targets = {
        "anchor": {
            "sequence_sha256": "encoded-anchor",
            "suffixes": [[token] for token in range(6)],
            "expected": "read",
            "scores": [0, -1, -2, -3, -4, -5],
        }
    }
    document = {
        "records": {
            "train": [
                {
                    "record_id": "anchor",
                    "sequence_sha256": "encoded-anchor",
                    "assistant_token_spans": [{"start": 1}],
                    "input_ids": [9, 0],
                }
            ]
        },
        "retention": {
            "schema_version": 1,
            "actions": list(ACTIONS),
            "teacher_weights": weights,
            "targets": targets,
        },
    }
    assert "retention_weight" not in Recipe().identity()
    assert targets_for(document, Recipe()) == {}
    assert targets_for(document, recipe) == targets
    changed = deepcopy(document)
    changed["retention"]["targets"]["anchor"]["scores"][0] = float("nan")
    with pytest.raises(ValueError, match="anchor_invalid"):
        targets_for(changed, recipe)
    with pytest.raises(ValueError, match="targets_invalid"):
        targets_for({"records": document["records"]}, recipe)


def test_retention_penalty_is_differentiable_and_skipped_in_evaluation():
    """Backpropagate the anchor penalty only during training."""
    torch = pytest.importorskip("torch")
    from venom_core.services.functiongemma.retention import protected_trainer

    class StockTrainer:
        model_accepts_loss_kwargs = True
        current_gradient_accumulation_steps = 4

        def compute_loss(self, model, inputs, return_outputs, num_items_in_batch):
            """Return the stub trainer loss used as the SFT baseline."""
            assert "retention_anchors" not in inputs
            return model.bias.sum() * 0 + 2, {"stock": True}

    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.bias = torch.nn.Parameter(torch.zeros(8))

        def forward(self, input_ids, attention_mask, use_cache, logits_to_keep):
            """Return differentiable logits for the requested token positions."""
            assert not use_cache and attention_mask.shape == input_ids.shape
            return NS(
                logits=self.bias.expand(input_ids.shape[0], len(logits_to_keep), -1)
            )

    targets = {
        "a": {
            "suffixes": [[0], [1, 7], [2], [3], [4], [5]],
            "scores": [3, 0, 0, 0, 0, 0],
        }
    }
    trainer = protected_trainer(StockTrainer, targets, 0.5, 7)()
    model = Model()
    inputs = {"input_ids": torch.tensor([[6, 0]]), "retention_anchors": [("a", [6])]}
    stock = trainer.compute_loss(model, {**inputs, "retention_anchors": []})
    loss = trainer.compute_loss(model, dict(inputs))
    normalized = trainer.compute_loss(model, dict(inputs), num_items_in_batch=4)
    assert stock.item() == 2 and loss.item() > 2
    assert normalized.item() - 2 == pytest.approx((loss.item() - 2) / 4)
    loss.backward()
    assert model.bias.grad[0] < 0
    model.eval()
    evaluated, outputs = trainer.compute_loss(model, dict(inputs), return_outputs=True)
    assert evaluated.item() == 2 and outputs == {"stock": True}


@pytest.mark.parametrize(
    "package, version", [("torch", "2.13.0"), ("transformers", "5.17.0")]
)
def test_new_stack_rejects_old_worker_environment(monkeypatch, package, version):
    """Require a new exact dependency identity before a training or resume run."""
    monkeypatch.setattr(worker.platform, "python_version", lambda: "3.14.8")
    versions = {**worker.VERSIONS, package: version}
    monkeypatch.setattr(worker.importlib.metadata, "version", versions.__getitem__)
    with pytest.raises(ValueError, match="functiongemma_environment_unqualified"):
        worker.environment()


def test_functiongemma_versions_match_canonical_model_policy():
    policy = json.loads(Path("config/dependency-profiles.json").read_text())
    requirements = (
        policy["groups"]["model-runtime"] + policy["groups"]["granite-training"]
    )
    for name, version in worker.VERSIONS.items():
        assert name + "==" + version in requirements
