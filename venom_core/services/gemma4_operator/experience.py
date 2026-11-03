"""Opt-in export of saved execution traces with independently supplied evidence.

Receipts are operator-provided eligibility inputs, not authentication. This code
does not execute a replay, approve its own output, or change any model weights.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from .material import digest, prepare_material, supervised_turn_indices

MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|secret|api[_-]?key|access[_-]?token|authorization|cookie|private[_-]?key)$",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:Bearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"(?:sk-[A-Za-z0-9_-]{16,})|"
    r"gh[pousr]_[A-Za-z0-9]{20,})",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"""(?<![\w-])(?P<key>[\w-]+)["']?\s*[:=]\s*""",
    re.ASCII,
)
_PLACEHOLDERS = frozenset({"", "[REDACTED]", "<redacted>", "***"})
Json = dict[str, Any]


def _require(condition: Any, code: str) -> None:
    if not condition:
        raise ValueError("gemma_experience_" + code)


def _mapping(value: Any, code: str) -> Json:
    _require(isinstance(value, dict), code)
    return value


def _sequence(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("gemma_experience_" + code)
    return value


def _text(value: Any, code: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), code)
    return value


def _version(value: Json) -> None:
    version = value.get("schema_version")
    _require(type(version) is int and version == 1, "schema_version_invalid")


def _contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_sensitive_pair(key, item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    return isinstance(value, str) and _secret_text(value)


def _secret_text(value: str) -> bool:
    if _SECRET_VALUE.search(value) is not None:
        return True
    try:
        decoded = json.loads(value)
    except (ValueError, RecursionError):
        decoded = None
    if isinstance(decoded, (dict, list)):
        return _contains_secret(decoded)
    return any(
        _SENSITIVE_KEY.search(match["key"]) is not None
        and _assignment_secret(value, match.end())
        for match in _SECRET_ASSIGNMENT.finditer(value)
    )


def _assignment_secret(text: str, offset: int) -> bool:
    if offset < len(text) and text[offset] in {'"', "'"}:
        end = text.find(text[offset], offset + 1)
        value = text[offset + 1 : end if end >= 0 else len(text)]
    else:
        match = re.compile(r"[^\s,;}]*").match(text, offset)
        value = match[0] if match is not None else ""
    return value not in _PLACEHOLDERS


def _sensitive_pair(key: Any, value: Any) -> bool:
    if isinstance(key, str) and _SENSITIVE_KEY.search(key):
        if not isinstance(value, (dict, list)) and value is not None:
            if not isinstance(value, str) or value not in _PLACEHOLDERS:
                return True
    return _contains_secret(value)


def _source_permissions(task: Json, trace: Json) -> None:
    for source in (task, trace):
        if "training_allowed" in source:
            value = source["training_allowed"]
            _require(type(value) is bool, "source_training_permission_invalid")
            _require(value is True, "source_training_forbidden")
        if "split" in source:
            _require(source["split"] == "train", "source_split_forbidden")


def _source(task: Json) -> tuple[str, Json]:
    ident = str(UUID(_text(task.get("id"), "task_id_required")))
    _require(task.get("status") == "COMPLETED", "task_not_completed")
    context = _mapping(task.get("context_history"), "canonical_trace_missing")
    trace = _mapping(context.get("gemma4_operator"), "canonical_trace_missing")
    _version(trace)
    _source_permissions(task, trace)
    _require(trace.get("task_id") == ident, "trace_task_mismatch")
    _require(trace.get("execution_status") == "completed", "trace_not_completed")
    _require(trace.get("capture_complete") is True, "trace_capture_incomplete")
    for flag in ("timed_out", "has_unconfirmed_effects"):
        value = trace.get(flag, False)
        _require(type(value) is bool and not value, "trace_outcome_ambiguous")
    pending = trace.get("pending_actions", [])
    _require(isinstance(pending, list) and not pending, "trace_outcome_ambiguous")
    _require(isinstance(trace.get("messages"), list), "messages_missing")
    _require(isinstance(trace.get("tools"), list), "tools_missing")
    return ident, trace


def _trajectory(value: Json) -> Json:
    return {"messages": value.get("messages"), "tools": value.get("tools")}


def _call_shape(message: Json) -> list[tuple[Any, Any]]:
    calls = message.get("tool_calls", [])
    _require(isinstance(calls, list), "trace_call_shape_invalid")
    result = []
    for call in calls:
        function = _mapping(
            _mapping(call, "trace_call_shape_invalid").get("function"),
            "trace_call_shape_invalid",
        )
        result.append((call.get("id"), function.get("name")))
    return result


def _check_redaction_shape(raw: Json, redacted: Json) -> None:
    _require(redacted.get("tools") == raw.get("tools"), "tool_catalog_changed")
    original = _sequence(raw.get("messages"), "trace_message_invalid")
    cleaned = _sequence(redacted.get("messages"), "message_shape_changed")
    _require(len(cleaned) == len(original), "message_shape_changed")
    for before, after in zip(original, cleaned):
        before = _mapping(before, "trace_message_invalid")
        after = _mapping(after, "redacted_message_invalid")
        for key in ("role", "tool_call_id", "name"):
            _require(before.get(key) == after.get(key), "message_shape_changed")
        _require(_call_shape(before) == _call_shape(after), "call_shape_changed")


def _redacted(task: Json, trace: Json, receipt: Json) -> Json:
    _version(receipt)
    _require(receipt.get("task_id") == trace["task_id"], "receipt_task_mismatch")
    _require(receipt.get("source_task_sha256") == digest(task), "source_hash_mismatch")
    for source in (task, trace):
        if "problem_group" in source:
            _require(
                receipt.get("problem_group") == source["problem_group"],
                "source_problem_group_mismatch",
            )
    redaction = _mapping(receipt.get("redaction"), "redaction_receipt_missing")
    _require(redaction.get("status") == "reviewed", "redaction_not_reviewed")
    _require(
        redaction.get("source_trajectory_sha256") == digest(_trajectory(trace)),
        "source_trajectory_mismatch",
    )
    trajectory = _mapping(redaction.get("trajectory"), "redacted_trajectory_missing")
    _require(
        set(trajectory) == {"messages", "tools"}, "redacted_trajectory_fields_invalid"
    )
    _check_redaction_shape(trace, trajectory)
    _require(not _contains_secret(trajectory), "sensitive_content_detected")
    return copy.deepcopy(trajectory)


def _evidence(
    raw: bytes | None, receipt: Json, ident: str, trajectory_hash: str
) -> Json:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_EVIDENCE_BYTES:
        raise ValueError("gemma_experience_evidence_bytes_missing_or_large")
    verification = _mapping(receipt.get("verification"), "verification_receipt_missing")
    _require(
        verification.get("evidence_sha256") == hashlib.sha256(raw).hexdigest(),
        "evidence_hash_mismatch",
    )
    try:
        proof = _mapping(json.loads(raw), "evidence_document_invalid")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("gemma_experience_evidence_document_invalid") from exc
    _version(proof)
    _require(proof.get("kind") == "independent_replay", "independent_replay_missing")
    _require(proof.get("status") == "passed", "replay_failed")
    _require(proof.get("task_id") == ident, "evidence_task_mismatch")
    _require(
        proof.get("trajectory_sha256") == trajectory_hash,
        "evidence_trajectory_mismatch",
    )
    verifier = _text(proof.get("verifier"), "verifier_missing")
    _require(
        verifier.casefold() not in {"model", "assistant", "llm", "finish"},
        "model_self_verification",
    )
    _require(
        verification.get("verifier") == verifier
        and verification.get("status") == "passed",
        "verification_mismatch",
    )
    _require(
        verification.get("trajectory_sha256") == trajectory_hash,
        "verification_trajectory_mismatch",
    )
    checks = _sequence(proof.get("checks"), "replay_checks_missing")
    _require(bool(checks), "replay_checks_missing")
    for check in checks:
        check = _mapping(check, "replay_check_invalid")
        _text(check.get("name"), "replay_check_name_missing")
        _require(check.get("passed") is True, "replay_check_failed")
    return {
        key: verification[key]
        for key in ("status", "verifier", "evidence_sha256", "trajectory_sha256")
    }


def _review(receipt: Json, trajectory_hash: str) -> None:
    _require(receipt.get("training_consent") is True, "training_consent_missing")
    _text(receipt.get("environment_revision"), "environment_revision_missing")
    review = _mapping(receipt.get("review"), "review_receipt_missing")
    _require(review.get("status") == "approved", "review_not_approved")
    reviewer = _text(review.get("reviewer"), "reviewer_missing")
    _require(
        reviewer.casefold() not in {"model", "assistant", "llm", "gemma"},
        "model_self_approval",
    )
    _require(
        review.get("trajectory_sha256") == trajectory_hash, "review_trajectory_mismatch"
    )


def _review_targets(trace: Json, receipt: Json) -> list[int]:
    selected = _sequence(
        receipt["review"].get("selected_assistant_indices"),
        "review_targets_missing_or_invalid",
    )
    _require(
        isinstance(selected, list)
        and bool(selected)
        and all(type(index) is int for index in selected),
        "review_targets_missing_or_invalid",
    )
    _require(len(set(selected)) == len(selected), "review_targets_duplicate")
    allowed = set(supervised_turn_indices(trace))
    _require(set(selected) <= allowed, "review_targets_expand_source")
    return sorted(selected)


def _record(trace: Json, trajectory: Json, receipt: Json, verification: Json) -> Json:
    row = {
        "record_id": _text(receipt.get("record_id"), "record_id_missing"),
        "problem_group": _text(receipt.get("problem_group"), "problem_group_missing"),
        "language": _text(receipt.get("language"), "language_missing"),
        "split": "train",
        "training_allowed": True,
        "source_kind": "experience",
        **trajectory,
        "experience": {
            "training_consent": True,
            "redacted": True,
            "review_status": "approved",
            "environment_revision": receipt["environment_revision"],
            "verification": verification,
            "source_task_sha256": receipt["source_task_sha256"],
            "source_trajectory_sha256": receipt["redaction"][
                "source_trajectory_sha256"
            ],
            "review_receipt_sha256": digest(receipt),
        },
    }
    selected = _review_targets(trace, receipt)
    row["supervised_assistant_indices"] = selected
    row["context_only_assistant_indices"] = [
        index
        for index, message in enumerate(trajectory["messages"])
        if message["role"] == "assistant" and index not in selected
    ]
    _require(not _contains_secret(row), "sensitive_content_detected")
    try:
        return prepare_material({"train": [row]})["records"]["train"][0]
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise ValueError("gemma_experience_canonical_material_invalid") from exc


def build_experience(
    task: Json, receipt: Json | None = None, evidence_bytes: bytes | None = None
) -> Json:
    """Export eligible canonical material only after all operator inputs agree.

    RAW/REJECTED outputs contain codes and hashes only. Plain learning-log success
    labels and truncated RequestTrace summaries cannot manufacture tool histories.
    """
    report: Json = {
        "schema_version": 1,
        "status": "REJECTED",
        "stage": "RAW",
        "eligible": False,
        "reasons": [],
        "training_started": False,
        "activation_authorized": False,
        "qualification": "supplied_receipts_only",
    }
    try:
        task = _mapping(task, "task_record_invalid")
        ident, trace = _source(task)
        report.update(
            source_task_id=ident,
            source_task_sha256=digest(task),
            source_trajectory_sha256=digest(_trajectory(trace)),
        )
        receipt = _mapping(receipt, "operator_receipt_missing")
        trajectory = _redacted(task, trace, receipt)
        trajectory_hash = digest(trajectory)
        report.update(stage="REDACTED", trajectory_sha256=trajectory_hash)
        verification = _evidence(evidence_bytes, receipt, ident, trajectory_hash)
        report["stage"] = "VERIFIED"
        _review(receipt, trajectory_hash)
        report["stage"] = "REVIEWED"
        row = _record(trace, trajectory, receipt, verification)
        report.update(status="ELIGIBLE", stage="ELIGIBLE", eligible=True, record=row)
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        code = str(exc)
        report["reasons"] = [
            code
            if code.startswith("gemma_experience_")
            else "gemma_experience_malformed_input"
        ]
    return report
