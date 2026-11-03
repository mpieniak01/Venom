"""Decision expansion preserves provenance, exclusions and split isolation."""

import copy

import pytest

from venom_core.services.functiongemma.dataset import export_decisions, validate_release


def row(split="train"):
    tool = {
        "type": "function",
        "function": {
            "name": "FileSkill-read_file",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
    }
    call = {
        "id": "one",
        "type": "function",
        "function": {"name": "FileSkill-read_file", "arguments": {"file_path": "a"}},
    }
    return {
        "record_id": split + "-row",
        "problem_group": split + "-group",
        "language": "pl",
        "split": split,
        "training_allowed": split == "train",
        "tools": [tool],
        "messages": [
            {"role": "user", "content": "Read a"},
            {"role": "assistant", "tool_calls": [call]},
            {
                "role": "tool",
                "tool_call_id": "one",
                "name": "FileSkill-read_file",
                "content": "real result",
            },
            {"role": "assistant", "content": "Which next file?"},
        ],
        "supervised_assistant_indices": [3],
        "context_only_assistant_indices": [1],
    }


def test_export_preserves_context_and_does_not_supervise_bad_prefix():
    sources = {"train": [row()], "validation": [row("validation")]}
    old = copy.deepcopy(sources)
    release = export_decisions(sources)
    decision = validate_release(release)["train"][0]
    assert decision["messages"][2]["content"] == "real result"
    assert decision["supervised_assistant_indices"] == [3]
    assert decision["context_only_assistant_indices"] == [1]
    assert decision["source_record_id"] == "train-row"
    assert sources == old


def test_group_leakage_rejected_before_expansion():
    sources = {"train": [row()], "validation": [row("validation")]}
    sources["validation"][0]["problem_group"] = "train-group"
    with pytest.raises(ValueError, match="group_leakage"):
        export_decisions(sources)


def test_no_training_consent_skipped_and_terminal_prefix_not_rewritten():
    denied = row()
    denied["training_allowed"] = False
    sources = {"train": [denied], "validation": [row("validation")]}
    assert export_decisions(sources)["records"]["train"] == []
    unsupported = row()
    unsupported["tools"][0]["function"]["name"] = "Terminal"
    unsupported["messages"][1]["tool_calls"][0]["function"]["name"] = "Terminal"
    unsupported["messages"][2]["name"] = "Terminal"
    sources["train"] = [unsupported]
    assert export_decisions(sources)["manifest"]["skipped"] == {"no_fileskill_tools": 1}


def test_release_tampering_rejected():
    release = export_decisions({"train": [row()], "validation": []})
    release["records"]["train"][0]["messages"][0]["content"] = "tampered"
    with pytest.raises(ValueError, match="hash_mismatch"):
        validate_release(release)


@pytest.mark.parametrize(
    "change", ["duplicate_id", "bad_split", "bad_flag", "bad_target"]
)
def test_invalid_metadata_rejected(change):
    sources = {"train": [row()], "validation": [row("validation")]}
    if change == "duplicate_id":
        sources["validation"][0]["record_id"] = sources["train"][0]["record_id"]
    elif change == "bad_split":
        sources["validation"][0]["split"] = "train"
    elif change == "bad_flag":
        sources["validation"][0]["training_allowed"] = True
    else:
        sources["validation"][0]["supervised_assistant_indices"] = [2]
    with pytest.raises(ValueError):
        export_decisions(sources)


def test_selected_file_calls_expand_with_same_group_and_preserved_observation():
    source = row()
    source["supervised_assistant_indices"] = [1, 3]
    source["context_only_assistant_indices"] = []
    release = export_decisions({"train": [source], "validation": [row("validation")]})
    records = validate_release(release)["train"]
    assert len(records) == 2
    assert {r["problem_group"] for r in records} == {"train-group"}
    assert records[0]["supervised_assistant_indices"] == [1]
    assert records[1]["messages"][2]["content"] == "real result"


def test_resealed_export_cannot_expand_tool_scope():
    from venom_core.services.gemma4_operator.material import digest

    release = export_decisions({"train": [row()], "validation": [row("validation")]})
    release["records"]["train"][0]["tools"][0]["function"]["name"] = "Terminal"
    release["records_sha256"] = digest(release["records"])
    release["release_sha256"] = digest(
        {k: v for k, v in release.items() if k != "release_sha256"}
    )
    with pytest.raises(ValueError, match="tool_scope_invalid"):
        validate_release(release)
