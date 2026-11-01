"""Material acceptance rejects bad supervision and non-progressing trajectories."""

import copy
import json

import pytest

from scripts.granite_operator.validate_material import check_receipt
from tests.test_granite_operator_contract import row


def example():
    sample = row()
    result = {"stdout": "", "stderr": "not found", "exit_code": 1}
    sample["messages"][3]["content"] = json.dumps(result)
    sample["supervised_assistant_indices"] = [4]
    sample["context_only_assistant_indices"] = [2]
    receipt = {
        "steps": [
            {
                "command": "cat note",
                "assistant_index": 2,
                "result": result,
                "before_state": "state-1",
                "context_only": True,
            }
        ],
        "oracle": {"passed": True},
        "finish": sample["messages"][4]["tool_calls"][0]["function"]["arguments"],
    }
    return sample, receipt


def test_failed_prefix_is_accepted_only_as_masked_context():
    sample, receipt = example()
    assert check_receipt(sample, receipt) == {
        "commands": 1,
        "context_only_assistants": 1,
    }
    sample["supervised_assistant_indices"] = [2, 4]
    with pytest.raises(ValueError, match="bad_prefix_is_supervised"):
        check_receipt(sample, receipt)


def test_fabricated_observation_or_final_claim_is_rejected():
    sample, receipt = example()
    sample["messages"][3]["content"] = json.dumps(
        {"stdout": "invented", "stderr": "", "exit_code": 0}
    )
    with pytest.raises(ValueError, match="fabricated"):
        check_receipt(sample, receipt)
    sample, receipt = example()
    receipt["finish"] = {"status": "success", "summary": "invented"}
    with pytest.raises(ValueError, match="finish_not_grounded"):
        check_receipt(sample, receipt)


def test_repeated_action_requires_changed_workspace():
    sample, receipt = example()
    sample["messages"][4:4] = copy.deepcopy(sample["messages"][2:4])
    sample["supervised_assistant_indices"] = [4, 6]
    other = copy.deepcopy(receipt["steps"][0])
    other.update(assistant_index=4, context_only=False)
    receipt["steps"].append(other)
    with pytest.raises(ValueError, match="repeated_action_without_change"):
        check_receipt(sample, receipt)
    other["before_state"] = "state-2"
    assert check_receipt(sample, receipt)["commands"] == 2


def test_repeated_flags_and_receipt_corruption_fail():
    sample, receipt = example()
    sample["messages"][2]["tool_calls"][0]["function"]["arguments"]["command"] = (
        "pytest -q -q"
    )
    with pytest.raises(ValueError, match="repeated_command_flags"):
        check_receipt(sample, receipt)
    sample, receipt = example()
    receipt["steps"][0]["command"] = "different"
    with pytest.raises(ValueError, match="receipt_mismatch"):
        check_receipt(sample, receipt)


def test_ungrounded_oracle_and_context_metadata_fail():
    sample, receipt = example()
    receipt["oracle"]["passed"] = False
    with pytest.raises(ValueError, match="oracle_invalid"):
        check_receipt(sample, receipt)
    sample, receipt = example()
    sample["context_only_assistant_indices"] = []
    with pytest.raises(ValueError, match="context_metadata"):
        check_receipt(sample, receipt)


def test_language_specific_finish_and_required_final_call():
    sample, receipt = example()
    sample["language"] = "pl"
    receipt["finishes"] = {"pl": receipt.pop("finish")}
    assert check_receipt(sample, receipt)["commands"] == 1
    sample["messages"][-1]["tool_calls"][0]["function"]["name"] = "Terminal"
    with pytest.raises(ValueError, match="final_finish_required"):
        check_receipt(sample, receipt)


def test_unmasked_good_actions_are_required():
    sample, receipt = example()
    receipt["steps"][0]["context_only"] = False
    sample["context_only_assistant_indices"] = []
    with pytest.raises(ValueError, match="correct_assistant_masked"):
        check_receipt(sample, receipt)
    sample["supervised_assistant_indices"] = [2, 4]
    assert check_receipt(sample, receipt)["commands"] == 1


def test_extra_or_missing_execution_receipts_are_rejected():
    sample, receipt = example()
    receipt["steps"].append(copy.deepcopy(receipt["steps"][0]))
    with pytest.raises(ValueError, match="receipt_or_oracle_invalid"):
        check_receipt(sample, receipt)
    receipt["steps"] = []
    with pytest.raises(ValueError, match="receipt_mismatch"):
        check_receipt(sample, receipt)


class NativeTokenizer:
    def apply_chat_template(self, messages, *, add_generation_prompt, **_):
        rendered = ""
        for message in messages:
            rendered += "<role=" + message["role"] + ">"
            for call in message.get("tool_calls", []):
                function = call["function"]
                rendered += "<tool_call><function=" + function["name"] + ">"
                for key, value in function["arguments"].items():
                    rendered += "<parameter=" + key + ">" + value + "</parameter>"
                rendered += "</function></tool_call>"
        return rendered + ("<role=assistant>" if add_generation_prompt else "")


def test_native_arguments_round_trip_without_flattening():
    from scripts.granite_operator.validate_material import check_native_calls

    sample, _ = example()
    assert check_native_calls(sample, NativeTokenizer()) == 2

    class Corrupt(NativeTokenizer):
        def apply_chat_template(self, *args, **kwargs):
            text = super().apply_chat_template(*args, **kwargs)
            return text.replace("cat note", "cat invented")

    with pytest.raises(ValueError, match="native_call_roundtrip_invalid"):
        check_native_calls(sample, Corrupt())

    class NonPrefix(NativeTokenizer):
        def apply_chat_template(self, *args, **kwargs):
            text = super().apply_chat_template(*args, **kwargs)
            return text + ("broken" if kwargs["add_generation_prompt"] else "")

    with pytest.raises(ValueError, match="native_prefix_invalid"):
        check_native_calls(sample, NonPrefix())


def test_cpu_intake_checks_manifest_before_tokenizer_and_never_loads_model(
    tmp_path, monkeypatch
):
    import sys
    from types import SimpleNamespace

    pytest.importorskip("torch")
    from scripts.granite_operator import validate_material as material
    from venom_core.services.granite_operator.contract import file_digest, write_json

    receipts = []
    samples = []
    for index in range(9):
        sample, receipt = example()
        split = "train" if index < 8 else "validation"
        sample.update(
            record_id=str(index),
            problem_group="group-" + str(index),
            fixture_id=str(index),
            family="family-" + str(index),
            split=split,
            training_allowed=split == "train",
        )
        receipt["fixture_id"] = str(index)
        samples.append(sample)
        receipts.append(receipt)
    manifest = {"datasets": {}}
    for dataset in ("domain", "hf"):
        for split in ("train", "validation"):
            path = tmp_path / dataset / (split + ".jsonl")
            path.parent.mkdir(exist_ok=True)
            selected = [row for row in samples if row["split"] == split]
            path.write_text("".join(json.dumps(row) + "\n" for row in selected))
            manifest["datasets"][dataset + "/" + split + ".jsonl"] = {
                "sha256": file_digest(path),
                "rows": len(selected),
            }
    receipt_path = tmp_path / "receipts.jsonl"
    receipt_path.write_text("".join(json.dumps(row) + "\n" for row in receipts))
    manifest["execution_receipts"] = {
        "path": receipt_path.name,
        "rows": len(receipts),
        "sha256": file_digest(receipt_path),
    }
    manifest_path = tmp_path / "pilot-manifest.json"
    write_json(manifest_path, manifest)
    loaded = []
    tokenizer = NativeTokenizer()
    tokenizer.pad_token_id = 0
    tokenizer.convert_tokens_to_ids = lambda _: 99

    def local_tokenizer(path, *, local_files_only):
        assert local_files_only is True
        loaded.append(path)
        return tokenizer

    # This module intentionally exposes no AutoModel class.
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=local_tokenizer),
        ),
    )
    monkeypatch.setattr(
        material,
        "encode",
        lambda *args: {
            "input_ids": [99, 5],
            "attention_mask": [1, 1],
            "labels": [99, -100],
        },
    )
    result = material.inspect(tmp_path, manifest_path, tmp_path / "snapshot")
    assert result["status"] == "PASS_DATA_INTAKE_ONLY"
    assert result["domain_train"] == 8 and result["domain_validation"] == 1
    assert result["context_only_assistant_occurrences"] == 9
    assert result["native_tool_calls_roundtripped"] == 18
    assert result["cpu_batch_shape"] == [4, 2]
    assert all(
        result[key] is False
        for key in (
            "training_started",
            "model_loaded",
            "optimizer_created",
            "gpu_used",
        )
    )

    loaded.clear()
    manifest["execution_receipts"]["sha256"] = "tampered"
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="receipt_hash_changed"):
        material.inspect(tmp_path, manifest_path, tmp_path / "snapshot")
    assert not loaded
    manifest["execution_receipts"]["sha256"] = file_digest(receipt_path)
    manifest["execution_receipts"]["rows"] = 500
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="receipt_count_changed"):
        material.inspect(tmp_path, manifest_path, tmp_path / "snapshot")
