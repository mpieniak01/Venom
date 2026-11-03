"""Experience collection requires an actual trace and separately supplied proofs."""

import copy
import hashlib
import json

import pytest

from venom_core.services.gemma4_operator.experience import build_experience
from venom_core.services.gemma4_operator.material import digest, verify_experience

TASK_ID = "cf60c67f-bc57-4ce4-aac3-b0f05032b5bc"


def sample():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "inspect",
                "parameters": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}},
                    "required": ["service"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    messages = [
        {"role": "user", "content": "Inspect web"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "inspect-web",
                    "function": {"name": "inspect", "arguments": {"service": "web"}},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "inspect-web",
            "name": "inspect",
            "content": "running",
        },
        {"role": "assistant", "content": "Web is running."},
    ]
    trace = {
        "schema_version": 1,
        "task_id": TASK_ID,
        "execution_status": "completed",
        "capture_complete": True,
        "messages": messages,
        "tools": tools,
        "experience_export": "requires_review",
        "supervised_assistant_indices": [1, 3],
        "context_only_assistant_indices": [],
    }
    task = {
        "id": TASK_ID,
        "status": "COMPLETED",
        "content": "Inspect web",
        "result": "Web is running.",
        "context_history": {"gemma4_operator": trace},
    }
    trajectory = {"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)}
    trajectory_hash = digest(trajectory)
    proof = {
        "schema_version": 1,
        "task_id": TASK_ID,
        "trajectory_sha256": trajectory_hash,
        "kind": "independent_replay",
        "status": "passed",
        "verifier": "sandbox/replay",
        "checks": [{"name": "service_status_matches_observation", "passed": True}],
    }
    evidence = json.dumps(proof).encode()
    receipt = {
        "schema_version": 1,
        "task_id": TASK_ID,
        "source_task_sha256": digest(task),
        "training_consent": True,
        "environment_revision": "a" * 40,
        "record_id": "experience-web",
        "problem_group": "web-incident-1",
        "language": "pl",
        "redaction": {
            "status": "reviewed",
            "source_trajectory_sha256": trajectory_hash,
            "trajectory": trajectory,
        },
        "review": {
            "status": "approved",
            "reviewer": "operator",
            "trajectory_sha256": trajectory_hash,
            "selected_assistant_indices": [1, 3],
        },
        "verification": {
            "status": "passed",
            "verifier": "sandbox/replay",
            "trajectory_sha256": trajectory_hash,
            "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        },
    }
    return task, receipt, evidence


def bind_evidence(receipt, proof):
    evidence = json.dumps(proof).encode()
    receipt["verification"]["evidence_sha256"] = hashlib.sha256(evidence).hexdigest()
    return evidence


def test_complete_receipt_exports_bound_canonical_record():
    task, receipt, evidence = sample()
    report = build_experience(task, receipt, evidence)
    assert report["status"] == "ELIGIBLE"
    assert report["eligible"] is True
    assert report["reasons"] == []
    assert report["record"]["source_kind"] == "experience"
    assert report["record"]["training_allowed"] is True
    assert verify_experience(report["record"])
    assert (
        report["record"]["experience"]["verification"]["evidence_sha256"]
        == hashlib.sha256(evidence).hexdigest()
    )
    assert "training_allowed" not in task["context_history"]["gemma4_operator"]
    assert report["qualification"] == "supplied_receipts_only"
    assert report["activation_authorized"] is False
    assert report["training_started"] is False


def test_legacy_learning_success_is_not_a_canonical_trace():
    task = {
        "id": TASK_ID,
        "status": "COMPLETED",
        "success": True,
        "content": "private prompt",
    }
    report = build_experience(task)
    assert report["eligible"] is False
    assert report["stage"] == "RAW"
    assert "record" not in report
    assert "private prompt" not in json.dumps(report)


@pytest.mark.parametrize(
    "kind",
    [
        "failed_task",
        "failed_trace",
        "timeout",
        "ambiguous",
        "pending",
        "missing_result",
    ],
)
def test_incomplete_or_ambiguous_execution_is_not_eligible(kind):
    task, receipt, evidence = sample()
    trace = task["context_history"]["gemma4_operator"]
    if kind == "failed_task":
        task["status"] = "FAILED"
    elif kind == "failed_trace":
        trace["execution_status"] = "failed"
    elif kind == "timeout":
        trace["timed_out"] = True
    elif kind == "ambiguous":
        trace["has_unconfirmed_effects"] = True
    elif kind == "pending":
        trace["pending_actions"] = ["mutation"]
    else:
        trace["messages"].pop(2)
        trace["supervised_assistant_indices"] = [1, 2]
        receipt["redaction"]["trajectory"]["messages"].pop(2)
        receipt["review"]["selected_assistant_indices"] = [1, 2]
        receipt["source_task_sha256"] = digest(task)
        trajectory_hash = digest(receipt["redaction"]["trajectory"])
        receipt["redaction"]["source_trajectory_sha256"] = trajectory_hash
        receipt["review"]["trajectory_sha256"] = trajectory_hash
        receipt["verification"]["trajectory_sha256"] = trajectory_hash
        proof = json.loads(evidence)
        proof["trajectory_sha256"] = trajectory_hash
        evidence = bind_evidence(receipt, proof)
    report = build_experience(task, receipt, evidence)
    assert report["status"] == "REJECTED"
    if kind == "missing_result":
        assert report["reasons"] == ["gemma_experience_canonical_material_invalid"]
    assert "record" not in report


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("root", "task_id", "wrong-task"),
        ("root", "schema_version", True),
        ("root", "source_task_sha256", "0" * 64),
        ("redaction", "status", "pending"),
        ("redaction", "source_trajectory_sha256", "0" * 64),
        ("review", "status", "pending"),
        ("review", "reviewer", "model"),
        ("review", "trajectory_sha256", "0" * 64),
        ("root", "training_consent", False),
        ("verification", "evidence_sha256", "0" * 64),
        ("verification", "trajectory_sha256", "0" * 64),
        ("verification", "verifier", "other"),
        ("verification", "status", "failed"),
    ],
)
def test_receipt_must_match_source_redaction_replay_and_review(section, key, value):
    task, receipt, evidence = sample()
    target = receipt if section == "root" else receipt[section]
    target[key] = value
    report = build_experience(task, receipt, evidence)
    assert report["eligible"] is False
    assert report["reasons"]
    assert "record" not in report


@pytest.mark.parametrize(
    "key,value",
    [
        ("kind", "model_assertion"),
        ("status", "failed"),
        ("task_id", "wrong-task"),
        ("trajectory_sha256", "0" * 64),
        ("verifier", "model"),
        ("checks", []),
        ("checks", [{"name": "check", "passed": False}]),
        ("checks", [{"name": "", "passed": True}]),
    ],
)
def test_independent_replay_content_is_checked_even_when_bytes_match(key, value):
    task, receipt, evidence = sample()
    proof = json.loads(evidence)
    proof[key] = value
    if key == "verifier":
        receipt["verification"]["verifier"] = value
    report = build_experience(task, receipt, bind_evidence(receipt, proof))
    assert report["eligible"] is False
    assert "record" not in report


def test_no_evidence_bytes_means_no_verified_stage():
    task, receipt, _ = sample()
    report = build_experience(task, receipt)
    assert report["stage"] == "REDACTED"
    assert report["eligible"] is False


@pytest.mark.parametrize("evidence", [b"{broken", b"[]", b"", b"\xff"])
def test_malformed_evidence_has_no_private_output(evidence):
    task, receipt, _ = sample()
    receipt["verification"]["evidence_sha256"] = hashlib.sha256(evidence).hexdigest()
    report = build_experience(task, receipt, evidence)
    assert report["status"] == "REJECTED"
    assert "record" not in report


@pytest.mark.parametrize(
    "kind", ["tool_catalog", "call_name", "call_id", "message_count", "role"]
)
def test_redaction_cannot_invent_execution(kind):
    task, receipt, evidence = sample()
    redacted = receipt["redaction"]["trajectory"]
    if kind == "tool_catalog":
        redacted["tools"] = []
    elif kind == "call_name":
        redacted["messages"][1]["tool_calls"][0]["function"]["name"] = "invented"
    elif kind == "call_id":
        redacted["messages"][1]["tool_calls"][0]["id"] = "invented"
    elif kind == "message_count":
        redacted["messages"].pop()
    else:
        redacted["messages"][0]["role"] = "system"
    report = build_experience(task, receipt, evidence)
    assert report["eligible"] is False


@pytest.mark.parametrize("selected", [None, [], [1, 1], [0], [True], [100]])
def test_review_must_explicitly_select_valid_assistant_targets(selected):
    task, receipt, evidence = sample()
    receipt["review"]["selected_assistant_indices"] = selected
    report = build_experience(task, receipt, evidence)
    assert report["eligible"] is False


def test_review_can_reduce_but_not_expand_source_targets():
    task, receipt, evidence = sample()
    receipt["review"]["selected_assistant_indices"] = [3]
    report = build_experience(task, receipt, evidence)
    assert report["record"]["supervised_assistant_indices"] == [3]
    assert report["record"]["context_only_assistant_indices"] == [1]
    trace = task["context_history"]["gemma4_operator"]
    trace["supervised_assistant_indices"] = [3]
    trace["context_only_assistant_indices"] = [1]
    receipt["source_task_sha256"] = digest(task)
    receipt["review"]["selected_assistant_indices"] = [1, 3]
    rejected = build_experience(task, receipt, evidence)
    assert rejected["eligible"] is False


@pytest.mark.parametrize(
    "secret",
    [
        "sk-" + "a" * 30,
        "Bearer " + "a" * 30,
        "password" + "=" + "x" * 30,
        "-----BEGIN OPENSSH PRIVATE KEY-----",
    ],
)
def test_secret_scan_blocks_unredacted_approved_content(secret):
    task, receipt, evidence = sample()
    receipt["redaction"]["trajectory"]["messages"][0]["content"] = secret
    report = build_experience(task, receipt, evidence)
    assert report["eligible"] is False
    assert secret not in json.dumps(report)


def test_raw_secret_can_be_redacted_without_exporting_original():
    task, receipt, evidence = sample()
    secret = "sk-" + "a" * 30
    task["content"] = secret
    trace = task["context_history"]["gemma4_operator"]
    trace["messages"][0]["content"] = secret
    receipt["source_task_sha256"] = digest(task)
    receipt["redaction"]["source_trajectory_sha256"] = digest(
        {
            "messages": trace["messages"],
            "tools": trace["tools"],
        }
    )
    report = build_experience(task, receipt, evidence)
    assert report["eligible"] is True
    assert secret not in json.dumps(report)


def test_unused_verification_fields_are_not_published():
    task, receipt, evidence = sample()
    receipt["verification"]["stdout"] = "private raw material"
    report = build_experience(task, receipt, evidence)
    assert report["eligible"] is True
    assert "private raw material" not in json.dumps(report)


def test_actual_runtime_incomplete_capture_cannot_be_eligible():
    task, receipt, evidence = sample()
    task["context_history"]["gemma4_operator"]["capture_complete"] = False
    report = build_experience(task, receipt, evidence)
    assert report["eligible"] is False
    assert report["reasons"] == ["gemma_experience_trace_capture_incomplete"]


@pytest.mark.parametrize("target", ["task", "trace"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("training_allowed", False),
        ("training_allowed", "false"),
        ("split", "holdout"),
        ("split", "validation"),
    ],
)
def test_explicit_source_training_restrictions_are_preserved(target, field, value):
    task, receipt, evidence = sample()
    source = task if target == "task" else task["context_history"]["gemma4_operator"]
    source[field] = value
    receipt["source_task_sha256"] = digest(task)
    report = build_experience(task, receipt, evidence)
    assert report["eligible"] is False
    assert "record" not in report


@pytest.mark.parametrize("target", ["task", "trace"])
def test_existing_source_problem_group_cannot_be_reassigned(target):
    task, receipt, evidence = sample()
    source = task if target == "task" else task["context_history"]["gemma4_operator"]
    source["problem_group"] = "source-group"
    receipt["source_task_sha256"] = digest(task)
    rejected = build_experience(task, receipt, evidence)
    assert rejected["eligible"] is False
    receipt["problem_group"] = "source-group"
    accepted = build_experience(task, receipt, evidence)
    assert accepted["eligible"] is True
    assert accepted["record"]["problem_group"] == "source-group"


@pytest.mark.parametrize(
    "extra", ["split", "training_allowed", "source_kind", "record_id", "experience"]
)
def test_redacted_trajectory_cannot_override_record_metadata(extra):
    task, receipt, evidence = sample()
    receipt["redaction"]["trajectory"][extra] = "injected"
    rejected = build_experience(task, receipt, evidence)
    assert rejected["eligible"] is False
    assert rejected["reasons"] == [
        "gemma_experience_redacted_trajectory_fields_invalid"
    ]


@pytest.mark.parametrize("key", ["PASSWORD", "API_KEY"])
def test_sensitive_assignment_scanning_is_case_insensitive(key):
    text = key + "=" + "x" * 30
    task, receipt, evidence = sample()
    receipt["redaction"]["trajectory"]["messages"][0]["content"] = text
    rejected = build_experience(task, receipt, evidence)
    assert rejected["eligible"] is False
    assert text not in json.dumps(rejected)


def test_actual_maf_tool_names_survive_reviewed_export():
    task, receipt, evidence = sample()
    trace = task["context_history"]["gemma4_operator"]
    for trajectory in (trace, receipt["redaction"]["trajectory"]):
        trajectory["tools"][0]["function"]["name"] = "ServiceSkill-inspect"
        trajectory["messages"][1]["tool_calls"][0]["function"]["name"] = (
            "ServiceSkill-inspect"
        )
        trajectory["messages"][2]["name"] = "ServiceSkill-inspect"
    trajectory_hash = digest({"messages": trace["messages"], "tools": trace["tools"]})
    receipt["source_task_sha256"] = digest(task)
    receipt["redaction"]["source_trajectory_sha256"] = trajectory_hash
    receipt["review"]["trajectory_sha256"] = trajectory_hash
    receipt["verification"]["trajectory_sha256"] = trajectory_hash
    proof = json.loads(evidence)
    proof["trajectory_sha256"] = trajectory_hash
    evidence = bind_evidence(receipt, proof)
    result = build_experience(task, receipt, evidence)
    assert result["status"] == "ELIGIBLE"
    assert result["record"]["tools"][0]["function"]["name"] == "ServiceSkill-inspect"
    assert result["record"]["messages"][2]["name"] == "ServiceSkill-inspect"


@pytest.mark.parametrize("key", ["db_password", "client_secret", "x-api-key"])
@pytest.mark.parametrize("serialized", [False, True])
def test_prefixed_sensitive_keys_are_blocked_in_objects_and_tool_json(key, serialized):
    task, receipt, evidence = sample()
    secret = "x" * 30
    value = {key: secret}
    message = receipt["redaction"]["trajectory"]["messages"][2]
    message["content"] = json.dumps(value) if serialized else value
    rejected = build_experience(task, receipt, evidence)
    assert rejected["eligible"] is False
    assert rejected["reasons"] == ["gemma_experience_sensitive_content_detected"]
    assert secret not in json.dumps(rejected)


@pytest.mark.parametrize("key", ["password", "client_secret", "x-api-key"])
@pytest.mark.parametrize("quote", ['"', "'"])
def test_sensitive_quoted_assignments_in_log_content_are_blocked(key, quote):
    task, receipt, evidence = sample()
    secret = "x" * 30
    text = "tool log: " + quote + key + quote + ": " + quote + secret + quote
    receipt["redaction"]["trajectory"]["messages"][2]["content"] = text
    rejected = build_experience(task, receipt, evidence)
    assert rejected["eligible"] is False
    assert rejected["reasons"] == ["gemma_experience_sensitive_content_detected"]
    assert secret not in json.dumps(rejected)


@pytest.mark.parametrize("marker", ["[REDACTED]", "<redacted>", "***"])
def test_explicit_redacted_placeholders_survive_json_and_quoted_logs(marker):
    task, receipt, evidence = sample()
    trajectory = receipt["redaction"]["trajectory"]
    trajectory["messages"][2]["content"] = json.dumps({"db_password": marker})
    trajectory["messages"][0]["content"] = (
        "tool log: " + "'client_secret': " + repr(marker)
    )
    target_hash = digest(trajectory)
    receipt["review"]["trajectory_sha256"] = target_hash
    receipt["verification"]["trajectory_sha256"] = target_hash
    proof = json.loads(evidence)
    proof["trajectory_sha256"] = target_hash
    accepted = build_experience(task, receipt, bind_evidence(receipt, proof))
    assert accepted["eligible"] is True
    assert marker in accepted["record"]["messages"][2]["content"]


def test_long_plain_text_and_many_redacted_assignments_remain_safe():
    from venom_core.services.gemma4_operator.experience import _contains_secret

    assert not _contains_secret("x" * 200000)
    marker = "password" + "=[REDACTED] "
    assert not _contains_secret(marker * 20000)
