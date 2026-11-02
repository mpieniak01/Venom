"""CPU material and matched-evaluation checks; no models, GPU or provider access."""

import copy

import pytest

from venom_core.services.gemma4_operator.evaluation import compare_trials
from venom_core.services.gemma4_operator.material import (
    digest,
    prepare_material,
    supervised_turn_indices,
    verify_experience,
)


def material_row(
    ident="task-1", split="train", group="incident-a", prompt="Inspect logs"
):
    def call(ident, name, args):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": ident,
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }
            ],
        }

    return {
        "record_id": ident,
        "problem_group": group,
        "language": "pl",
        "split": split,
        "training_allowed": split == "train",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "Terminal",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "Finish",
                    "parameters": {
                        "type": "object",
                        "properties": {"status": {"type": "string"}},
                        "required": ["status"],
                        "additionalProperties": False,
                    },
                },
            },
        ],
        "messages": [
            {"role": "user", "content": prompt},
            call("wrong", "Terminal", {"command": "wrong --path"}),
            {
                "role": "tool",
                "name": "Terminal",
                "tool_call_id": "wrong",
                "content": "not found",
            },
            call("right", "Terminal", {"command": "read logs"}),
            {
                "role": "tool",
                "name": "Terminal",
                "tool_call_id": "right",
                "content": "healthy",
            },
            call("finish", "Finish", {"status": "success"}),
        ],
        "supervised_assistant_indices": [3, 5],
        "context_only_assistant_indices": [1],
    }


def test_preparation_preserves_wrong_context_and_does_not_claim_tokenization():
    row = material_row()
    original = copy.deepcopy(row)
    result = prepare_material({"train": [row]})
    assert row == original
    prepared = result["records"]["train"][0]
    assert prepared["messages"] == original["messages"]
    assert prepared["supervised_assistant_indices"] == [3, 5]
    assert prepared["context_only_assistant_indices"] == [1]
    manifest = result["manifest"]
    assert manifest["source_sha256"] == digest({"train": [original]})
    assert manifest["tokenization_status"] == "pending_remote_qualification"
    assert manifest["training_ready"] is False
    assert manifest["activation_authorized"] is False
    assert manifest["splits"]["train"]["supervised_turns"] == 2


def test_no_selector_can_supervise_all_assistant_turns_only_without_exclusions():
    row = material_row()
    row.pop("supervised_assistant_indices")
    row.pop("context_only_assistant_indices")
    assert supervised_turn_indices(row) == [1, 3, 5]
    row["context_only_assistant_indices"] = [1]
    with pytest.raises(ValueError, match="explicit_targets_required"):
        supervised_turn_indices(row)


@pytest.mark.parametrize(
    "selected,context",
    [
        ([], []),
        ([True], []),
        ([3, 3], []),
        ([0], []),
        ([3], [3]),
        ([99], []),
        ([3], [False]),
        ([3], [1, 1]),
        ("all", []),
        ([3], "none"),
    ],
)
def test_invalid_supervision_never_becomes_positive_labels(selected, context):
    row = material_row()
    row["supervised_assistant_indices"] = selected
    row["context_only_assistant_indices"] = context
    with pytest.raises(ValueError, match="gemma_material_"):
        prepare_material({"train": [row]})


def test_derives_all_unsupervised_context_indices():
    row = material_row()
    row.pop("context_only_assistant_indices")
    row["supervised_assistant_indices"] = [5]
    prepared = prepare_material({"train": [row]})["records"]["train"][0]
    assert prepared["context_only_assistant_indices"] == [1, 3]


@pytest.mark.parametrize("split", ["validation", "holdout"])
def test_nontraining_records_cannot_be_train_allowed(split):
    row = material_row(split=split)
    row["training_allowed"] = True
    with pytest.raises(ValueError, match="split_not_allowed"):
        prepare_material({split: [row]})
    row["training_allowed"] = False
    assert prepare_material({split: [row]})["manifest"]["training_ready"] is False


def test_translation_and_changed_answer_cannot_escape_group_split():
    train = material_row()
    validation = material_row(
        "task-en", "validation", "incident-a", "Read system state"
    )
    validation["language"] = "en"
    with pytest.raises(ValueError, match="group_leakage"):
        prepare_material({"train": [train], "validation": [validation]})


def test_normalized_user_prefix_cannot_cross_splits():
    train = material_row(prompt="Inspect JOB 123")
    validation = material_row("other", "validation", "incident-b", "  inspect job 999 ")
    with pytest.raises(ValueError, match="prompt_leakage"):
        prepare_material({"train": [train], "validation": [validation]})


def test_exact_duplicates_and_ids_are_rejected():
    row = material_row()
    duplicate = copy.deepcopy(row)
    duplicate["record_id"] = "other"
    with pytest.raises(ValueError, match="duplicate_conversation"):
        prepare_material({"train": [row, duplicate]})
    duplicate["messages"][0]["content"] = "Different prompt"
    duplicate["record_id"] = row["record_id"]
    with pytest.raises(ValueError, match="duplicate_record_id"):
        prepare_material({"train": [row, duplicate]})


@pytest.mark.parametrize(
    "mutation,error",
    [
        (
            lambda r: r["messages"][1]["tool_calls"][0]["function"].update(
                name="Unknown"
            ),
            "call_invalid",
        ),
        (
            lambda r: r["messages"][1]["tool_calls"][0]["function"].update(
                arguments="read"
            ),
            "must_be_object",
        ),
        (
            lambda r: r["messages"][1]["tool_calls"][0]["function"].update(
                arguments={"command": 42}
            ),
            "arguments_invalid",
        ),
        (
            lambda r: r["messages"][2].update(tool_call_id="orphan"),
            "orphan_tool_result",
        ),
        (lambda r: r["messages"][2].update(role="user"), "missing_tool_result"),
        (
            lambda r: r["messages"][3]["tool_calls"][0].update(id="wrong"),
            "call_invalid",
        ),
        (lambda r: r["messages"][2].update(content=None), "tool_result_invalid"),
        (lambda r: r["messages"][1].update(content=[]), "text_only"),
        (lambda r: r["messages"][0].update(content=None), "message_content_invalid"),
        (
            lambda r: r["tools"].append(copy.deepcopy(r["tools"][0])),
            "tool_name_invalid",
        ),
        (
            lambda r: r["tools"][0]["function"]["parameters"].update(type="unknown"),
            "tool_schema_invalid",
        ),
    ],
)
def test_invalid_conversations_are_rejected(mutation, error):
    row = material_row()
    mutation(row)
    with pytest.raises(ValueError, match=error):
        prepare_material({"train": [row]})


def test_external_schema_references_are_rejected_without_network():
    row = material_row()
    row["tools"][0]["function"]["parameters"]["properties"]["command"] = {
        "$ref": "https://untrusted.invalid/schema"
    }
    with pytest.raises(ValueError, match="external_schema_reference"):
        prepare_material({"train": [row]})


def test_experience_receipt_binds_actual_trajectory_and_human_review():
    row = material_row()
    row["source_kind"] = "experience"
    assert not verify_experience(row)
    with pytest.raises(ValueError, match="experience_not_verified"):
        prepare_material({"train": [row]})
    row["experience"] = {
        "training_consent": True,
        "redacted": True,
        "review_status": "approved",
        "environment_revision": "fixture-v1",
        "verification": {
            "status": "passed",
            "verifier": "state-verifier-v1",
            "evidence_sha256": "e" * 64,
            "trajectory_sha256": digest(
                {"messages": row["messages"], "tools": row["tools"]}
            ),
        },
    }
    assert verify_experience(row)
    prepare_material({"train": [row]})
    row["messages"][3]["tool_calls"][0]["function"]["arguments"]["command"] = "changed"
    assert not verify_experience(row)


@pytest.mark.parametrize(
    "field,value",
    [
        ("training_consent", False),
        ("redacted", False),
        ("review_status", "model-approved"),
        ("environment_revision", ""),
    ],
)
def test_experience_without_trusted_eligibility_is_rejected(field, value):
    row = material_row()
    row["experience"] = {
        "training_consent": True,
        "redacted": True,
        "review_status": "approved",
        "environment_revision": "v1",
        "verification": {
            "status": "passed",
            "verifier": "test",
            "evidence_sha256": "a" * 64,
            "trajectory_sha256": digest(
                {"messages": row["messages"], "tools": row["tools"]}
            ),
        },
    }
    row["experience"][field] = value
    assert not verify_experience(row)


@pytest.mark.parametrize("value", [{}, {"test": []}, {"train": []}])
def test_empty_or_unknown_splits_fail(value):
    with pytest.raises(ValueError, match="gemma_material_"):
        prepare_material(value)


def identities():
    common = {
        "model": "google/gemma-4-12B-it",
        "revision": "1" * 40,
        "benchmark_sha256": "9" * 64,
        "requested_precision": "nf4",
        "effective_precision": "nf4",
        "runtime_backend": "transformers",
        "runtime_version": "qualified",
        "context": 2048,
        "max_new_tokens": 192,
        "seed": 17,
        "concurrency": 4,
        "tools_sha256": "a" * 64,
        "evaluator_sha256": "b" * 64,
        "tokenizer_sha256": "c" * 64,
        "template_sha256": "d" * 64,
    }
    return {
        "base": common.copy(),
        "adapter": common | {"adapter_sha256": "f" * 64},
    }


def trial(case, arm, success=True, seconds=10, active=5):
    return {
        "case_id": case,
        "problem_group": "group-" + case,
        "family": "diagnostics",
        "language": "pl",
        "arm": arm,
        "task_seconds": seconds,
        "active_task_seconds": active,
        "timed_out": False,
        "oracle": {
            "success": success,
            "scope_violations": [],
            "success_without_oracle_confirmation": False,
            "incorrect_success_status": False,
        },
    }


def test_comparison_uses_shared_correct_cases_and_retains_failed_denominator():
    rows = [
        trial("a", "base"),
        trial("a", "adapter", seconds=4, active=2),
        trial("b", "base", False, 1, 1),
        trial("b", "adapter", seconds=3, active=1),
    ]
    original = copy.deepcopy(rows)
    result = compare_trials(rows, identities=identities())
    assert rows == original
    assert result["arms"]["base"]["success_rate"] == 0.5
    assert result["arms"]["adapter"]["success_rate"] == 1
    common = result["common_correct"]
    assert common["case_ids"] == ["a"]
    assert common["timings"]["base"]["task_p50_seconds"] == 10
    assert common["timings"]["adapter"]["task_p50_seconds"] == 4
    assert result["qualification"] == "diagnostic_only"
    assert not result["activation_authorized"]
    assert not result["promotion_authorized"]
    assert result["comparison_complete"] is True


@pytest.mark.parametrize(
    "field",
    [
        "effective_precision",
        "runtime_version",
        "tools_sha256",
        "evaluator_sha256",
        "context",
        "concurrency",
        "revision",
    ],
)
def test_unmatched_runtime_or_precision_cannot_be_ranked(field):
    identity = identities()
    if field == "effective_precision":
        identity["adapter"]["requested_precision"] = "bf16"
        identity["adapter"][field] = "bf16"
    elif field.endswith("sha256"):
        identity["adapter"][field] = "e" * 64
    elif field in {"context", "concurrency"}:
        identity["adapter"][field] *= 2
    else:
        identity["adapter"][field] = "2" * 40 if field == "revision" else "other"
    with pytest.raises(ValueError, match="unmatched_configuration"):
        compare_trials([trial("a", "base"), trial("a", "adapter")], identities=identity)


def test_requested_precision_is_not_evidence_of_effective_precision():
    identity = identities()
    identity["adapter"]["requested_precision"] = "bf16"
    with pytest.raises(ValueError, match="precision_mismatch"):
        compare_trials([trial("a", "base"), trial("a", "adapter")], identities=identity)


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda r: r.update(timed_out=True), None),
        (lambda r: r.update(failure_kind="model"), None),
        (lambda r: r["oracle"].update(scope_violations=["protected"]), None),
        (lambda r: r["oracle"].update(success_without_oracle_confirmation=True), None),
        (lambda r: r["oracle"].update(incorrect_success_status=True), None),
    ],
)
def test_model_claimed_success_is_not_enough(mutation, error):
    row = trial("a", "adapter")
    mutation(row)
    result = compare_trials([trial("a", "base"), row], identities=identities())
    assert result["arms"]["adapter"]["successes"] == 0
    assert result["common_correct"]["count"] == 0
    assert result["common_correct"]["timings"]["adapter"]["task_p50_seconds"] is None


def test_infrastructure_error_remains_visible_and_unqualified():
    row = trial("a", "adapter", False)
    row["failure_kind"] = "infrastructure"
    result = compare_trials([trial("a", "base"), row], identities=identities())
    assert result["comparison_complete"] is False
    assert result["arms"]["adapter"]["infrastructure_errors"] == 1
    assert result["arms"]["adapter"]["trials"] == 1


@pytest.mark.parametrize(
    "rows,error",
    [
        ([trial("a", "base")], "incomplete_pairs"),
        ([trial("a", "base"), trial("a", "base")], "duplicate_trial"),
        ([], "trials_required"),
    ],
)
def test_incomplete_or_duplicate_trials_fail(rows, error):
    with pytest.raises(ValueError, match=error):
        compare_trials(rows, identities=identities())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, None])
def test_invalid_timings_cannot_make_a_candidate_fast(value):
    row = trial("a", "adapter")
    row["task_seconds"] = value
    with pytest.raises(ValueError, match="timing_invalid"):
        compare_trials([trial("a", "base"), row], identities=identities())


def test_pair_identity_must_refer_to_the_same_task():
    row = trial("a", "adapter")
    row["problem_group"] = "other"
    with pytest.raises(ValueError, match="case_identity_mismatch"):
        compare_trials([trial("a", "base"), row], identities=identities())


@pytest.mark.parametrize(
    "field,value",
    [
        ("context", True),
        ("seed", -1),
        ("tools_sha256", "broken"),
        ("runtime_version", ""),
        ("adapter_sha256", None),
    ],
)
def test_malformed_identity_fails_before_comparison(field, value):
    identity = identities()
    identity["adapter"][field] = value
    with pytest.raises(ValueError, match="gemma_evaluation_"):
        compare_trials([trial("a", "base"), trial("a", "adapter")], identities=identity)


def test_benchmark_identity_must_match_actual_cases_and_verifier_manifest():
    identity = identities()
    identity["adapter"]["benchmark_sha256"] = "8" * 64
    with pytest.raises(ValueError, match="unmatched_configuration"):
        compare_trials([trial("a", "base"), trial("a", "adapter")], identities=identity)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("revision", "main", "model_or_revision_invalid"),
        ("model", "other/model", "model_or_revision_invalid"),
        ("effective_precision", "fake", "precision_unsupported"),
    ],
)
def test_unpinned_or_unknown_model_configuration_is_not_comparable(field, value, error):
    identity = identities()
    identity["adapter"][field] = value
    with pytest.raises(ValueError, match=error):
        compare_trials([trial("a", "base"), trial("a", "adapter")], identities=identity)


def test_non_ascii_tool_name_does_not_create_unparseable_training_data():
    row = material_row()
    row["tools"][0]["function"]["name"] = "narzędzie"
    with pytest.raises(ValueError, match="tool_name_invalid"):
        prepare_material({"train": [row]})


def test_unhashable_tool_result_id_has_a_structured_rejection():
    row = material_row()
    row["messages"][2]["tool_call_id"] = []
    with pytest.raises(ValueError, match="orphan_tool_result"):
        prepare_material({"train": [row]})


def test_unrecognized_source_kind_does_not_bypass_experience_gate():
    row = material_row()
    row["source_kind"] = "experince"
    with pytest.raises(ValueError, match="source_kind_invalid"):
        prepare_material({"train": [row]})


@pytest.mark.parametrize("reference", ["#/$defs/missing", "#"])
def test_unresolved_or_recursive_local_schema_is_structurally_rejected(reference):
    row = material_row()
    parameters = row["tools"][0]["function"]["parameters"]
    if reference == "#":
        parameters["$ref"] = reference
    else:
        parameters["properties"]["command"] = {"$ref": reference}
    with pytest.raises(ValueError, match="arguments_invalid"):
        prepare_material({"train": [row]})
