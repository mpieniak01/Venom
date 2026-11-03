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
        with pytest.raises(ValueError):
            Recipe(**options).identity()
    with pytest.raises(ValueError):
        Recipe().budget(0)
    assert len(Recipe().fingerprint) == 64


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
        with pytest.raises(ValueError):
            worker.validate_request({**request(), **options})
    monkeypatch.delenv("HF_HUB_OFFLINE")
    with pytest.raises(ValueError):
        worker.validate_request(request())


def checkpoint(path):
    path.mkdir(parents=True)
    for name in (
        "trainer_state.json",
        "optimizer.pt",
        "scheduler.pt",
        "rng_state.pth",
        "model.safetensors",
    ):
        (path / name).write_text("state")


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


def fake_runtime(monkeypatch):
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
    torch = NS(cuda=cuda, bfloat16="bf16", tensor=lambda value: value)
    model = NS(
        config=NS(architectures=["Gemma3ForCausalLM"]),
        named_modules=lambda: [
            (name, None) for name in ("q_proj", "k_proj", "v_proj", "o_proj")
        ],
        parameters=lambda: [NS(device=NS(type="cuda"))],
    )

    class Trainer:
        def __init__(self, **kwargs):
            self.args = kwargs["args"]
            self.state = NS(global_step=0)

        def train(self, resume_from_checkpoint=None):
            self.state.global_step = getattr(self.args, "max_steps", 3)
            checkpoint(
                Path(self.args.output_dir)
                / ("checkpoint-" + str(self.state.global_step))
            )

    transformers = NS(
        AutoModelForCausalLM=NS(from_pretrained=lambda *a, **k: model),
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
    with pytest.raises(RuntimeError, match="cuda"):
        worker._execute(request(), Recipe(), {}, tmp_path, tmp_path / "bad", "fp", None)
    torch.cuda.is_available = lambda: True
    model.config.architectures = ["Other"]
    with pytest.raises(ValueError, match="architecture"):
        worker._execute(request(), Recipe(), {}, tmp_path, tmp_path / "bad", "fp", None)


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
    with pytest.raises(ValueError, match="smoke_mismatch"):
        worker.run({**body, "stage": "train", "qualification": str(proof)})
    with pytest.raises(ValueError, match="pinned_snapshot"):
        worker.run({**body, "snapshot": str(tmp_path)})


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
            return NS(logits="logits")

    monkeypatch.setitem(
        sys.modules,
        "torch",
        NS(inference_mode=nullcontext, tensor=lambda *a, **k: "tensor"),
    )
    assert (
        worker.probe_logits(Model(), {"input_ids": [1], "attention_mask": [1]})
        == "[('logits', 'logits')]"
    )
