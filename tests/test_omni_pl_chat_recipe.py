"""Offline contracts for the isolated, configurable Omni worker."""

import json
import re
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.academy import omni_pl_chat_evaluate as evaluator
from scripts.academy.omni_pl_chat_data import read_jsonl, sha256
from scripts.academy.omni_pl_chat_evaluate import (
    blind_mapping,
    validate_dev_cases,
    verify_adapter,
)
from scripts.academy.omni_pl_chat_p1 import (
    CHECKPOINT_FILES,
    _checkpoint_hashes,
    _module_inventory,
    _resume_checkpoint,
    _token_trainer_type,
    _write_json,
)
from scripts.academy.omni_pl_chat_recipe import (
    LANGUAGE_TARGET_MODULES,
    P13_LANGUAGE_SELECTOR,
    load_recipe,
    validate_recipe,
)


def test_recipe_overrides_keep_defaults_and_canonicalize_targets(tmp_path):
    path = tmp_path / "recipe.json"
    path.write_text(
        json.dumps(
            {
                "rank": 8,
                "target_modules": ["v_proj", "q_proj"],
                "steps": 5,
                "learning_rate": 0.0001,
                "gradient_accumulation_steps": 4,
            }
        ),
        encoding="utf-8",
    )
    recipe = load_recipe(path)
    assert recipe["rank"] == 8
    assert recipe["alpha"] == 8
    assert recipe["loss_mode"] == "model_default"
    assert recipe["gradient_checkpointing"] is False
    assert recipe["gpu_allocator_reserve_mib"] == 1000
    assert recipe["gpu_step_min_free_mib"] == 600
    assert recipe["target_modules"] == ["q_proj", "v_proj"]
    assert recipe["steps"] == 5
    assert recipe["gradient_accumulation_steps"] == 4
    assert recipe["learning_rate"] == 0.0001


def test_wider_language_targets_canonicalize_without_recipe_changes():
    control = validate_recipe({})
    wide = validate_recipe({"target_modules": list(reversed(LANGUAGE_TARGET_MODULES))})
    assert wide.pop("target_modules") == list(LANGUAGE_TARGET_MODULES)
    assert control.pop("target_modules") == ["q_proj", "v_proj"]
    assert wide == control


def test_gradient_checkpointing_is_explicit_and_boolean():
    enabled = validate_recipe({"gradient_checkpointing": True})
    assert enabled["gradient_checkpointing"] is True
    with pytest.raises(ValueError, match="gradient_checkpointing must be a boolean"):
        validate_recipe({"gradient_checkpointing": "true"})


def test_gpu_headroom_is_bounded_and_step_limit_stays_below_reserve():
    widened = validate_recipe(
        {"gpu_allocator_reserve_mib": 768, "gpu_step_min_free_mib": 384}
    )
    assert (widened["gpu_allocator_reserve_mib"], widened["gpu_step_min_free_mib"]) == (
        768,
        384,
    )
    with pytest.raises(ValueError, match="gpu_allocator_reserve_mib"):
        validate_recipe({"gpu_allocator_reserve_mib": 0})
    with pytest.raises(ValueError, match="GPU step minimum"):
        validate_recipe(
            {"gpu_allocator_reserve_mib": 768, "gpu_step_min_free_mib": 768}
        )


def test_token_loss_accumulation_matches_one_pooled_batch():
    import torch
    from torch import nn

    from scripts.academy.omni_pl_chat_p1 import _collate

    class TinyOmni(nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = nn.Parameter(torch.tensor(0.25))

        def forward(self, input_ids, attention_mask, labels):
            prediction = self.weight * input_ids[:, :-1].float()
            target = labels[:, 1:].clamp_min(0).float()
            mask = labels[:, 1:] != -100
            text_loss = ((prediction - target).square() * mask).sum() / mask.sum()
            return SimpleNamespace(loss=text_loss, text_loss=text_loss, audio_loss=None)

    rows = [
        {"input_ids": [0, 2, 3], "labels": [-100, 1, 2], "attention_mask": [1] * 3},
        {
            "input_ids": [0, 4, 5, 6],
            "labels": [-100, 3, 4, 5],
            "attention_mask": [1] * 4,
        },
    ]
    batches = [_collate([row], 0) for row in rows]
    model = TinyOmni()

    class TrainerBase:
        def __init__(self):
            self.args = SimpleNamespace(world_size=1, n_gpu=0)

    trainer = _token_trainer_type(TrainerBase)()
    total = trainer._get_num_items_in_batch(batches, torch.device("cpu"))
    assert int(total) == 5
    assert trainer.loss_is_scaled_for_ga
    for batch in batches:
        trainer.compute_loss(model, batch, num_items_in_batch=total).backward()
    actual_gradient = model.weight.grad.detach().clone()

    reference_model = TinyOmni()
    pooled = _collate(rows, 0)
    reference_model(**pooled).loss.backward()
    torch.testing.assert_close(actual_gradient.cpu(), reference_model.weight.grad)


def test_language_inventory_excludes_other_modalities():
    from torch import nn

    model = nn.Module()
    model.model = nn.Module()
    model.model.language_model = nn.Module()
    model.model.language_model.layers = nn.ModuleList([nn.Module()])
    model.model.language_model.layers[0].q_proj = nn.Linear(2, 3)
    model.model.language_model.layers[0].w1 = nn.Linear(3, 4)
    model.model.vision_model = nn.Module()
    model.model.vision_model.q_proj = nn.Linear(2, 3)

    inventory = _module_inventory(
        model, re.compile(r"model\.language_model\..*\.(q_proj|w1)")
    )
    assert [
        (item["name"], item["group"], item["weight_shape"]) for item in inventory
    ] == [
        ("model.language_model.layers.0.q_proj", "attention", [3, 2]),
        ("model.language_model.layers.0.w1", "mlp", [4, 3]),
    ]
    assert sum(item["weight_parameters"] for item in inventory) == 18


@pytest.mark.parametrize(
    "recipe",
    [
        {"target_modules": ["q_proj", "lm_head"]},
        {"target_modules": [".*"]},
        {"target_modules": P13_LANGUAGE_SELECTOR},
        {"target_modules": ["q_proj", "q_proj"]},
        {"loss_mode": "unknown"},
        {"rank": True},
        {"rank": 65},
        {"learning_rate": float("nan")},
        {"save_every": 9},
        {"warmup_steps": 8},
        {"seed": -1},
        {"train_sha256": "not a digest"},
        {"max_supervised_tokens": 0},
        {"gradient_accumulation_steps": 100},
        {"lr_scheduler_type": "custom"},
        {"output_dir": "/somewhere"},
    ],
)
def test_invalid_recipe_fails_before_model_loading(recipe):
    with pytest.raises(ValueError):
        validate_recipe(recipe)


def _checkpoint(root: Path, step: int) -> Path:
    path = root / f"checkpoint-{step}"
    path.mkdir()
    for name in CHECKPOINT_FILES:
        (path / name).write_text("fixture", encoding="utf-8")
    (path / "trainer_state.json").write_text(
        json.dumps({"global_step": step}), encoding="utf-8"
    )
    _write_json(path / "hashes.json", _checkpoint_hashes(path))
    return path


def test_resume_uses_latest_sealed_step_and_rejects_tampering(tmp_path):
    _checkpoint(tmp_path, 2)
    current = _checkpoint(tmp_path, 4)
    (tmp_path / "checkpoint-6").mkdir()
    assert _resume_checkpoint(tmp_path, 8) == current
    with pytest.raises(ValueError, match="step budget"):
        _resume_checkpoint(tmp_path, 3)
    with pytest.raises(ValueError, match="step budget"):
        _resume_checkpoint(tmp_path, 4)
    (current / "optimizer.pt").write_bytes(b"changed")
    with pytest.raises(ValueError, match="saved receipt"):
        _resume_checkpoint(tmp_path, 8)


def test_pruned_optimizer_keeps_adapter_evaluable_but_blocks_resume(tmp_path):
    path = _checkpoint(tmp_path, 2)
    (path / "optimizer.pt").unlink()
    assert verify_adapter(path)["adapter_model.safetensors"] == sha256(
        path / "adapter_model.safetensors"
    )
    with pytest.raises(ValueError, match="missing verified training state"):
        _resume_checkpoint(tmp_path, 8)
    (path / "adapter_model.safetensors").write_bytes(b"changed")
    with pytest.raises(ValueError, match="saved receipt"):
        verify_adapter(path)


def test_receipt_cannot_be_partially_published_or_replaced(tmp_path):
    path = tmp_path / "receipt.json"
    with pytest.raises(ValueError):
        _write_json(path, {"score": float("nan")})
    assert not path.exists()
    _write_json(path, {"score": 1})
    with pytest.raises(FileExistsError):
        _write_json(path, {"score": 2})
    assert json.loads(path.read_text()) == {"score": 1}
    assert list(tmp_path.iterdir()) == [path]


def _dev_case():
    return {
        "record_id": "dev-1",
        "group_id": "dev-group-1",
        "language": "pl",
        "split": "dev",
        "task": "natural",
        "messages": [{"role": "user", "content": "Podaj nazwę miesiąca."}],
        "criteria": [
            {"id": "answer", "kind": "content", "description": "Nazwa miesiąca."},
        ],
    }


def test_evaluation_requires_dev_and_a_defined_content_rubric():
    case = _dev_case()
    validate_dev_cases([case])
    overlong = {**case, "task": "a" * 129}
    with pytest.raises(ValueError, match="requires a task name"):
        validate_dev_cases([overlong])
    with pytest.raises(ValueError, match="only the dev split"):
        validate_dev_cases([{**case, "split": "pilot"}])
    with pytest.raises(ValueError, match="requires a content criterion"):
        validate_dev_cases(
            [
                {
                    **case,
                    "criteria": [
                        {"id": "format", "kind": "format", "description": "Text"}
                    ],
                }
            ]
        )
    with pytest.raises(ValueError, match="invalid rubric criterion"):
        validate_dev_cases([{**case, "criteria": case["criteria"] * 2}])


def test_blinding_requires_comparable_distinct_variants():
    cases = [_dev_case()]
    variants = ["base", "checkpoint-2"]
    mapping = blind_mapping(cases, variants)
    assert mapping == blind_mapping(cases, variants)
    assert set(mapping["dev-1"]) == {"A", "B"}
    assert set(mapping["dev-1"].values()) == set(variants)
    for labels in (
        ["checkpoint-1", "checkpoint-2"],
        ["base", "base"],
        ["base", "../x"],
    ):
        with pytest.raises(ValueError, match="distinct checkpoint labels"):
            blind_mapping(cases, labels)


def test_generation_resumes_only_missing_predictions_and_blinds_complete_result(
    tmp_path, monkeypatch
):
    import sys

    first = _dev_case()
    second = {**first, "record_id": "dev-2", "group_id": "dev-group-2"}
    cases = [first, second]
    variants = ["base", "checkpoint-2"]
    mapping = blind_mapping(cases, variants)
    identity = {"dev": "dev-hash", "base": "base-hash", "adapter": "adapter-hash"}
    progress = evaluator.GenerationProgress(tmp_path, identity, mapping)
    backbone = SimpleNamespace(can_use_lfm3_conv=lambda: True)
    base = SimpleNamespace(
        model=SimpleNamespace(language_model=object()),
        generation_config=SimpleNamespace(eos_token_id=99),
        config=SimpleNamespace(text_end_token_id=100),
    )
    model = Mock()
    model.disable_adapter.side_effect = nullcontext
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext)
    )
    monkeypatch.setattr(evaluator, "import_module", lambda _: backbone)
    cached = {"response": {"text": "cached", "finish": "stop", "error": None}}
    fresh = {"response": {"text": "fresh", "finish": "stop", "error": None}}
    interrupted = Mock(side_effect=[cached, TimeoutError])
    monkeypatch.setattr(evaluator, "_predict", interrupted)
    with pytest.raises(TimeoutError):
        evaluator._generate(progress, base, model, None, cases, variants)
    assert not (tmp_path / "blind.jsonl").exists()

    resumed = evaluator.GenerationProgress(tmp_path, identity, mapping)
    assert resumed.reused == 1
    assert resumed.missing(cases, "base") == [second]
    predict = Mock(return_value=fresh)
    monkeypatch.setattr(evaluator, "_predict", predict)
    evaluator._generate(resumed, base, model, None, cases, variants)
    assert predict.call_count == 3
    resumed.publish(tmp_path, cases, variants)

    raw = read_jsonl(tmp_path / "raw.jsonl")
    assert [(row["case"], row["model"]) for row in raw] == [
        (case["record_id"], tag) for tag in variants for case in cases
    ]
    assert raw[0]["response"] == cached["response"]
    blind = read_jsonl(tmp_path / "blind.jsonl")
    assert [row["case"] for row in blind] == cases
    for row in blind:
        assert set(row) == {"case", "answers"}
        assert sorted(row["answers"]) == ["A", "B"]


def test_generation_progress_requires_same_identity_and_valid_seal(tmp_path):
    cases = [_dev_case()]
    mapping = blind_mapping(cases, ["base", "checkpoint-2"])
    identity = {"dev": "dev-hash", "protocol": "protocol-hash"}
    progress = evaluator.GenerationProgress(tmp_path, identity, mapping)
    progress.save(("dev-1", "base"), {"response": {"text": "original"}})
    changed = evaluator.GenerationProgress(
        tmp_path, {**identity, "protocol": "changed"}, mapping
    )
    assert changed.reused == 0
    assert changed.missing(cases, "base") == cases

    receipt = next(progress.directory.glob("*.json"))
    data = json.loads(receipt.read_text())
    data["row"]["response"]["text"] = "altered"
    receipt.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from its seal"):
        evaluator.GenerationProgress(tmp_path, identity, mapping)
