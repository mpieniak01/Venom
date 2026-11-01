"""Contract regressions for offline Granite operator data and smoke admission."""

import copy
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from venom_core.services.granite_operator.contract import (
    TrainingProfile,
    digest,
    file_digest,
    inside,
    load_dataset,
    require_qualification,
    validate_conversation,
    write_json,
)
from venom_core.services.granite_operator.encoding import _ids, encode


def row(split="train"):
    return {
        "record_id": split,
        "problem_group": "family-" + split,
        "split": split,
        "training_allowed": split == "train",
        "tools": [
            {"function": {"name": "Terminal", "parameters": {"type": "object"}}},
            {"function": {"name": "Finish", "parameters": {"type": "object"}}},
        ],
        "messages": [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "read"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "Terminal",
                            "arguments": {"command": "cat note"},
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "name": "Terminal",
                "tool_call_id": "c1",
                "content": "ACTUAL_OBSERVATION",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "done",
                        "function": {
                            "name": "Finish",
                            "arguments": {"status": "success", "summary": "DONE"},
                        },
                    }
                ],
            },
        ],
    }


class CharacterTokenizer:
    """A deterministic tokenizer makes label targets directly inspectable as text."""

    def __init__(self):
        self.last = ""

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt, **_):
        text = ""
        for m in messages:
            text += "<" + m["role"] + ">"
            text += m.get("content", "") + json.dumps(
                m.get("tool_calls", []), sort_keys=True
            )
            text += "</" + m["role"] + ">"
        if add_generation_prompt:
            text += "<assistant>"
        self.last = text
        return (
            {"input_ids": [ord(c) for c in text], "attention_mask": [1] * len(text)}
            if tokenize
            else text
        )

    def __call__(self, text, **_):
        return {
            "input_ids": [ord(c) for c in text],
            "offset_mapping": [(i, i + 1) for i in range(len(text))],
        }


def test_native_mask_trains_calls_but_not_observations():
    sample = row()
    tokens = encode(sample, CharacterTokenizer(), 4096)
    target = "".join(chr(x) for x in tokens["labels"] if x != -100)
    assert "Terminal" in target
    assert "cat note" in target
    assert "Finish" in target
    assert "DONE" in target
    assert "ACTUAL_OBSERVATION" not in target
    assert "rules" not in target
    assert len(tokens["labels"]) == len(tokens["input_ids"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"model": "other"},
        {"revision": "bad"},
        {"quantization": "int8"},
        {"context": 0},
        {"context": 4097},
        {"rank": 65},
        {"accumulation": 33},
        {"seed": True},
        {"learning_rate": float("nan")},
        {"learning_rate": 0},
        {"dropout": 1},
        {"dropout": float("inf")},
    ],
)
def test_invalid_profiles_fail_before_model_load(kwargs):
    _case_value_0 = TrainingProfile()
    _case_value_1 = replace(_case_value_0, **kwargs)
    with pytest.raises(ValueError):
        _case_value_1.validate()


def test_profile_identity_is_stable():
    profile = TrainingProfile()
    assert profile.identity()["revision"]
    assert digest(profile.identity()) == digest(copy.deepcopy(profile.identity()))


def test_atomic_json_roundtrip_and_nonfinite_rejection(tmp_path):
    target = tmp_path / "nested" / "state.json"
    write_json(target, {"step": 16})
    assert json.loads(target.read_text()) == {"step": 16}
    assert not target.with_suffix(".json.tmp").exists()
    _case_value_2 = float("nan")
    with pytest.raises(ValueError):
        write_json(target, {"loss": _case_value_2})


def test_data_paths_cannot_escape_or_be_symlinks(tmp_path):
    safe = tmp_path / "data"
    safe.mkdir()
    p = safe / "one"
    p.write_text("x")
    assert inside(safe, "one") == p
    for bad in ("../else", str(p)):
        with pytest.raises(ValueError):
            inside(safe, bad)
    link = safe / "link"
    link.symlink_to(p)
    with pytest.raises(ValueError):
        inside(safe, "link")
    with pytest.raises(ValueError):
        inside(safe, ".")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(training_allowed=False),
        lambda r: r.update(problem_group="venom-maintenance-v1:old"),
        lambda r: r.update(problem_group=""),
        lambda r: r.update(messages=None),
        lambda r: r["tools"].append(r["tools"][0]),
        lambda r: r["tools"][0]["function"].update(name="invalid name"),
        lambda r: r["messages"][0].update(role="invalid"),
        lambda r: r["messages"][3].update(tool_call_id="unknown"),
        lambda r: r["messages"][3].update(content={}),
        lambda r: r["messages"].pop(3),
        lambda r: r["messages"][2]["tool_calls"][0]["function"].update(name="unknown"),
        lambda r: r["messages"][2]["tool_calls"][0]["function"].update(arguments="{}"),
        lambda r: r["messages"][-1]["tool_calls"][0].update(id="c1"),
        lambda r: r["messages"].pop(),
    ],
)
def test_invalid_structured_records_are_rejected(mutation):
    sample = row()
    mutation(sample)
    with pytest.raises((ValueError, TypeError)):
        validate_conversation(sample, "train")


def test_valid_record_and_clarification():
    sample = row()
    validate_conversation(sample, "train")
    sample["messages"] = [sample["messages"][1], sample["messages"][-1]]
    validate_conversation(sample, "train")


def prepare_files(tmp_path, leak=False):
    manifest = {"datasets": {}}
    for split in ("train", "validation"):
        sample = row(split)
        if leak:
            sample["problem_group"] = "shared"
        target = tmp_path / "domain" / (split + ".jsonl")
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(sample) + "\n")
        manifest["datasets"]["domain/" + split + ".jsonl"] = {
            "rows": 1,
            "sha256": file_digest(target),
        }
    return manifest


def test_dataset_receipts_and_leakage(tmp_path):
    manifest = prepare_files(tmp_path)
    train, val = load_dataset(tmp_path, manifest, "domain")
    assert len(train) == len(val) == 1
    with pytest.raises(ValueError):
        load_dataset(tmp_path, manifest, "other")
    manifest["datasets"]["domain/train.jsonl"]["rows"] = 2
    with pytest.raises(ValueError):
        load_dataset(tmp_path, manifest, "domain")
    manifest = prepare_files(tmp_path, leak=True)
    with pytest.raises(ValueError, match="leakage"):
        load_dataset(tmp_path, manifest, "domain")


def test_tampered_dataset_hash(tmp_path):
    manifest = prepare_files(tmp_path)
    (tmp_path / "domain/train.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="hash"):
        load_dataset(tmp_path, manifest, "domain")


def test_smoke_receipt_is_mandatory_and_bound_to_configuration():
    checks = {
        k: True
        for k in (
            "mask",
            "updated_adapter",
            "frozen_base",
            "reload",
            "resume",
            "long_context",
            "tool_loop",
        )
    }
    receipt = {"status": "PASS", "fingerprint": "a", "checks": checks}
    require_qualification(receipt, "a")
    for bad in ({}, {**receipt, "status": "FAIL"}, {**receipt, "fingerprint": "b"}):
        with pytest.raises(ValueError, match="smoke_required"):
            require_qualification(bad, "a")
    for bad in ({}, {**checks, "reload": False}, {**checks, "mask": 1}):
        with pytest.raises(ValueError, match="incomplete"):
            require_qualification({**receipt, "checks": bad}, "a")


def test_encoding_rejects_truncation_and_empty_targets():
    _case_value_3 = row()
    _case_value_4 = CharacterTokenizer()
    with pytest.raises(ValueError, match="context"):
        encode(_case_value_3, _case_value_4, 4)
    sample = row()
    sample["messages"] = [sample["messages"][0], sample["messages"][1]]
    _case_value_5 = CharacterTokenizer()
    with pytest.raises(ValueError, match="empty"):
        encode(sample, _case_value_5, 4096)


def test_encoding_rejects_non_prefix_or_changed_tokenization():
    class Changed(CharacterTokenizer):
        def apply_chat_template(self, *args, **kwargs):
            result = super().apply_chat_template(*args, **kwargs)
            return (
                result + "bad"
                if not kwargs["tokenize"] and kwargs["add_generation_prompt"]
                else result
            )

    _case_value_6 = row()
    _case_value_7 = Changed()
    with pytest.raises(ValueError, match="non_prefix"):
        encode(_case_value_6, _case_value_7, 4096)

    class Different(CharacterTokenizer):
        def apply_chat_template(self, *args, **kwargs):
            result = super().apply_chat_template(*args, **kwargs)
            if kwargs["tokenize"]:
                result["input_ids"] = [0]
            return result

    _case_value_8 = row()
    _case_value_9 = Different()
    with pytest.raises(ValueError, match="mismatch"):
        encode(_case_value_8, _case_value_9, 4096)


def test_encoding_dict_and_single_batch_ids():
    assert _ids({"input_ids": [[1, 2]]}) == [1, 2]
    assert _ids([3, 4]) == [3, 4]
    with pytest.raises(ValueError):
        _ids({"input_ids": [[1], [2]]})


@pytest.mark.parametrize(
    "relative",
    [
        "data/training/example/raw/source.jsonl",
        "data/training/example/recipes/prepare_domain.py",
        "data/training/example/hf/train.jsonl",
        "data/training/example/domain/fixtures/task/.git/config",
        "data/training/example/runs/partial/metrics.json",
        "data/training/example/runs/checkpoint/adapter_model.safetensors",
        "data/training/example/private_git_history/recovery.bundle",
        "data/datasets/example/train.parquet",
        "data/experiments/run/result.json",
        "data/academy/run/checkpoint/model.bin",
        "artifacts/training/run/loss.csv",
        "artifacts/datasets/source/data.arrow",
        "datasets/source/train.jsonl",
        "training-data/source.json",
        "training-runs/run/partial.json",
        "training-results/run/summary.json",
        "checkpoints/run/model.pt",
        "adapters/local/adapter_model.safetensors",
        "wandb/run/log.json",
        "mlruns/local/metrics/loss",
        "lightning_logs/version_0/events",
        "config/granite_operator/datasets.json",
        "config/granite_operator/hf-review.json",
        "config/granite_operator/pilot-results.json",
    ],
)
def test_complete_artifact_trees_are_ignored(relative):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.excludesFile=/dev/null",
            "check-ignore",
            "--no-index",
            "--verbose",
            relative,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith(".gitignore:")


@pytest.mark.parametrize(
    "relative",
    [
        "config/granite_operator_profile.json",
        "scripts/granite_operator/prepare_hf.py",
        "venom_core/services/granite_operator/engine.py",
        "docs/PL/GRANITE_OPERATOR_EXPERIMENT.md",
    ],
)
def test_generic_recipe_code_and_documentation_remain_visible(relative):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.excludesFile=/dev/null",
            "check-ignore",
            "--no-index",
            relative,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr


def test_recovery_prefix_is_context_not_a_positive_training_target():
    sample = row()
    sample["supervised_assistant_indices"] = [4]
    validate_conversation(sample, "train")
    encoded = encode(sample, CharacterTokenizer(), 4096)
    targets = "".join(chr(x) for x in encoded["labels"] if x != -100)
    full = "".join(chr(x) for x in encoded["input_ids"])
    assert "cat note" in full
    assert "ACTUAL_OBSERVATION" in full
    assert "Terminal" not in targets
    assert "cat note" not in targets
    assert "Finish" in targets
    assert "DONE" in targets


@pytest.mark.parametrize(
    "indices", [[], [2], [2, 2, 4], [True, 4], [3, 4], [-1, 4], [99, 4], "all"]
)
def test_bad_supervision_policy_fails_before_encoding(indices):
    sample = row()
    sample["supervised_assistant_indices"] = indices
    with pytest.raises(ValueError, match="supervision_indices"):
        validate_conversation(sample, "train")
    _case_value_10 = CharacterTokenizer()
    with pytest.raises(ValueError, match="supervision_indices"):
        encode(sample, _case_value_10, 4096)


def test_dataset_selection_preserves_validation_and_rejects_unknown():
    from venom_core.services.granite_operator.contract import select_dataset

    domain = ([{"id": "d-train"}], [{"id": "d-validation"}])
    hf = ([{"id": "h-train"}], [{"id": "h-validation"}])
    assert select_dataset(domain, hf, "domain") is domain
    assert select_dataset(domain, hf, "hf") is hf
    assert select_dataset(domain, hf, "mixed") == (domain[0] + hf[0], domain[1] + hf[1])
    with pytest.raises(ValueError, match="dataset_unknown"):
        select_dataset(domain, hf, "invalid")


def test_mixed_short_budget_sees_both_sources_without_changing_resume_order():
    from venom_core.services.granite_operator.contract import select_dataset

    domain = ([{"id": "d" + str(i)} for i in range(8)], [{"id": "dv"}])
    hf = ([{"id": "h" + str(i)} for i in range(2)], [{"id": "hv"}])
    train, validation = select_dataset(domain, hf, "mixed")
    assert [row["id"] for row in train[:4]] == ["d0", "h0", "d1", "h1"]
    assert len(train) == 10
    assert len({row["id"] for row in train}) == 10
    assert train == select_dataset(domain, hf, "mixed")[0]
    assert validation == domain[1] + hf[1]


def test_final_training_stage_supports_first_only_and_resumed_runs(tmp_path):
    from venom_core.services.granite_operator.contract import final_training_stage

    with pytest.raises(ValueError, match="stage_missing"):
        final_training_stage(tmp_path)
    first = tmp_path / "train-first"
    first.mkdir()
    assert final_training_stage(tmp_path) == first
    resumed = tmp_path / "train-resume"
    resumed.mkdir()
    assert final_training_stage(tmp_path) == resumed


@pytest.mark.parametrize("position", [2, 4])
def test_missing_tool_identity_is_always_orphaned(position):
    sample = row()
    sample["messages"].insert(position, {"role": "tool", "content": "unmatched"})
    with pytest.raises(ValueError, match="orphan_tool_response"):
        validate_conversation(sample, "train")


def test_snapshot_metadata_detects_tokenizer_and_generation_changes(tmp_path):
    from venom_core.services.granite_operator.contract import snapshot_metadata

    first = snapshot_metadata(tmp_path)
    (tmp_path / "tokenizer.json").write_text("{}")
    second = snapshot_metadata(tmp_path)
    assert second != first
    (tmp_path / "generation_config.json").write_text("{}")
    third = snapshot_metadata(tmp_path)
    assert third != second
    (tmp_path / "tokenizer.json").write_text('{"changed":true}')
    assert snapshot_metadata(tmp_path) != third


def test_json_writer_treats_path_shaped_content_as_data_and_does_not_follow_fixed_temp_symlink(
    tmp_path,
):
    target = tmp_path / "result.json"
    outside = tmp_path / "outside.txt"
    outside.write_text("unchanged")
    target.with_suffix(".json.tmp").symlink_to(outside)
    payload = {"path": "../../outside.txt"}
    write_json(target, payload)
    assert json.loads(target.read_text()) == payload
    assert outside.read_text() == "unchanged"
    invalid = {"loss": float("nan")}
    with pytest.raises(ValueError):
        write_json(target, invalid)
    assert json.loads(target.read_text()) == payload
    assert not list(tmp_path.glob("result.json.*.tmp"))
