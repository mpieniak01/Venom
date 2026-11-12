"""Offline contracts for the isolated, configurable Omni worker."""

import json
from pathlib import Path

import pytest

from scripts.academy.omni_pl_chat_data import sha256
from scripts.academy.omni_pl_chat_evaluate import (
    blind_mapping,
    validate_dev_cases,
    verify_adapter,
)
from scripts.academy.omni_pl_chat_p1 import (
    CHECKPOINT_FILES,
    _checkpoint_hashes,
    _resume_checkpoint,
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


@pytest.mark.parametrize(
    "recipe",
    [
        {"target_modules": ["q_proj", "lm_head"]},
        {"target_modules": [".*"]},
        {"target_modules": P13_LANGUAGE_SELECTOR},
        {"target_modules": ["q_proj", "q_proj"]},
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
