"""CPU-only canonical material preparation; training requires remote qualification."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

SPLITS = frozenset({"train", "validation", "holdout"})
SHA256 = re.compile(r"[a-f0-9]{64}")
Json = dict[str, Any]
_TOOL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def digest(value: Any) -> str:
    """Bind canonical JSON values, rejecting non-JSON numbers."""
    data = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(data.encode()).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("gemma_material_invalid_" + label)
    return value


def supervised_turn_indices(row: Mapping[str, Any]) -> list[int]:
    """Retain selective targets; never turn excluded demonstrations into labels."""
    messages = row.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("gemma_material_messages_required")
    assistants = {
        i
        for i, item in enumerate(messages)
        if isinstance(item, dict) and item.get("role") == "assistant"
    }
    selected = row.get("supervised_assistant_indices")
    context = row.get("context_only_assistant_indices", [])
    for values in (context, selected if selected is not None else []):
        if (
            not isinstance(values, list)
            or any(type(i) is not int for i in values)
            or len(set(values)) != len(values)
            or not set(values) <= assistants
        ):
            raise ValueError("gemma_material_supervision_indices_invalid")
    if selected is None and context:
        raise ValueError("gemma_material_explicit_targets_required")
    targets = assistants if selected is None else set(selected)
    if not targets or targets.intersection(context):
        raise ValueError("gemma_material_supervision_overlap_or_empty")
    return sorted(targets)


def _check_references(value: Any, depth: int = 0) -> None:
    """Keep JSON-schema validation offline, including nested schemas."""
    if depth > 32:
        raise ValueError("gemma_material_schema_depth_exceeded")
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (
                not isinstance(item, str) or not item.startswith("#")
            ):
                raise ValueError("gemma_material_external_schema_reference")
            _check_references(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_references(item, depth + 1)


def _schema_library() -> Any:
    try:
        return importlib.import_module("jsonschema")
    except ImportError as exc:
        raise RuntimeError("gemma_schema_dependency_missing") from exc


def _tools(row: Mapping[str, Any]) -> dict[str, Any]:
    tools = row.get("tools")
    if not isinstance(tools, list):
        raise ValueError("gemma_material_tools_required")
    library = _schema_library()
    result = {}
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            raise ValueError("gemma_material_tool_invalid")
        function = tool.get("function")
        if not isinstance(function, dict):
            raise ValueError("gemma_material_tool_invalid")
        name = _text(function.get("name"), "tool_name")
        if not _TOOL_NAME.fullmatch(name) or name in result:
            raise ValueError("gemma_material_tool_name_invalid")
        schema = function.get("parameters")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ValueError("gemma_material_tool_schema_invalid")
        _check_references(schema)
        try:
            library.Draft202012Validator.check_schema(schema)
        except library.exceptions.SchemaError as exc:
            raise ValueError("gemma_material_tool_schema_invalid") from exc
        result[name] = library.Draft202012Validator(schema)
    return result


def _calls(
    message: Json,
    tools: Mapping[str, Any],
    seen: set[str],
    pending: dict[str, str],
) -> None:
    calls = message.get("tool_calls", [])
    if not isinstance(calls, list):
        raise ValueError("gemma_material_calls_invalid")
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
            raise ValueError("gemma_material_call_invalid")
        ident = _text(call.get("id"), "call_id")
        function = call["function"]
        name, arguments = function.get("name"), function.get("arguments")
        if ident in seen or not isinstance(name, str) or name not in tools:
            raise ValueError("gemma_material_call_invalid")
        if not isinstance(arguments, dict):
            raise ValueError("gemma_material_arguments_must_be_object")
        try:
            tools[name].validate(arguments)
        except (
            _schema_library().exceptions.ValidationError,
            importlib.import_module("referencing.exceptions").Unresolvable,
            RecursionError,
        ) as exc:
            raise ValueError("gemma_material_arguments_invalid") from exc
        seen.add(ident)
        # Historical canonical data uses Finish as a terminal declaration.
        if name != "Finish":
            pending[ident] = name


def _conversation(row: Mapping[str, Any]) -> None:
    tools = _tools(row)
    pending: dict[str, str] = {}
    seen: set[str] = set()
    messages = row["messages"]
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError("gemma_material_message_invalid")
        role = message.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("gemma_material_role_invalid")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("gemma_material_text_only")
        if role in {"system", "user"} and not isinstance(content, str):
            raise ValueError("gemma_material_message_content_invalid")
        if role == "tool":
            ident = message.get("tool_call_id")
            if (
                not isinstance(ident, str)
                or ident not in pending
                or pending.pop(ident) != message.get("name")
            ):
                raise ValueError("gemma_material_orphan_tool_result")
            if not isinstance(content, str) or message.get("tool_calls"):
                raise ValueError("gemma_material_tool_result_invalid")
        else:
            if pending:
                raise ValueError("gemma_material_missing_tool_result")
            if role != "assistant" and message.get("tool_calls"):
                raise ValueError("gemma_material_nonassistant_call")
            if role == "assistant":
                _calls(message, tools, seen, pending)
                if any(
                    c["function"]["name"] == "Finish"
                    for c in message.get("tool_calls", [])
                ):
                    if index != len(messages) - 1 or len(message["tool_calls"]) != 1:
                        raise ValueError("gemma_material_finish_not_terminal")
    if not any(item["role"] == "user" for item in messages):
        raise ValueError("gemma_material_user_required")
    if pending or messages[-1].get("role") != "assistant":
        raise ValueError("gemma_material_incomplete_conversation")


def verify_experience(row: Mapping[str, Any]) -> bool:
    """Check a transcript-bound eligibility receipt, not the model's success claim."""
    proof = row.get("experience")
    if not isinstance(proof, dict):
        return False
    verification = proof.get("verification")
    if not isinstance(verification, dict):
        return False
    return (
        proof.get("training_consent") is True
        and proof.get("redacted") is True
        and proof.get("review_status") == "approved"
        and isinstance(proof.get("environment_revision"), str)
        and bool(proof["environment_revision"].strip())
        and verification.get("status") == "passed"
        and isinstance(verification.get("verifier"), str)
        and bool(verification["verifier"].strip())
        and isinstance(verification.get("evidence_sha256"), str)
        and SHA256.fullmatch(verification["evidence_sha256"]) is not None
        and verification.get("trajectory_sha256")
        == digest({"messages": row.get("messages"), "tools": row.get("tools")})
    )


def _record(row: Mapping[str, Any], split: str) -> Json:
    if not isinstance(row, dict):
        raise ValueError("gemma_material_record_invalid")
    if row.get("split") != split or row.get("training_allowed") is not (
        split == "train"
    ):
        raise ValueError("gemma_material_split_not_allowed")
    for field in ("record_id", "problem_group", "language"):
        _text(row.get(field), field)
    targets = supervised_turn_indices(row)
    _conversation(row)
    if row.get("source_kind", "canonical") not in {
        "canonical",
        "synthetic",
        "experience",
    }:
        raise ValueError("gemma_material_source_kind_invalid")
    if row.get("source_kind") == "experience" and not verify_experience(row):
        raise ValueError("gemma_material_experience_not_verified")
    # Copy through canonical JSON to reject non-serializable/non-finite metadata.
    digest(row)
    result = copy.deepcopy(row)
    result["supervised_assistant_indices"] = targets
    result["context_only_assistant_indices"] = [
        i
        for i, item in enumerate(row["messages"])
        if item["role"] == "assistant" and i not in targets
    ]
    return result


def prepare_material(splits: Mapping[str, Sequence[Json]]) -> Json:
    """Validate and export canonical records without claiming token or GPU readiness."""
    if not isinstance(splits, Mapping) or not splits or not set(splits) <= SPLITS:
        raise ValueError("gemma_material_splits_invalid")
    records: dict[str, list[Json]] = {}
    groups: dict[str, str] = {}
    contents: set[str] = set()
    prompts: dict[str, str] = {}
    ids: set[str] = set()
    summary = {}
    for split, rows in splits.items():
        if not isinstance(rows, (list, tuple)) or not rows:
            raise ValueError("gemma_material_empty_split")
        records[split] = []
        for raw in rows:
            row = _record(raw, split)
            ident, group = row["record_id"], row["problem_group"]
            checksum = digest({"messages": row["messages"], "tools": row["tools"]})
            prompt = next(m["content"] for m in row["messages"] if m["role"] == "user")
            normalized = " ".join(re.sub(r"\d+", "<n>", prompt.casefold()).split())
            prompt_hash = digest(normalized)
            if prompt_hash in prompts and prompts[prompt_hash] != split:
                raise ValueError("gemma_material_prompt_leakage")
            if ident in ids:
                raise ValueError("gemma_material_duplicate_record_id")
            if checksum in contents:
                raise ValueError("gemma_material_duplicate_conversation")
            if group in groups and groups[group] != split:
                raise ValueError("gemma_material_group_leakage")
            prompts[prompt_hash] = split
            ids.add(ident)
            contents.add(checksum)
            groups[group] = split
            records[split].append(row)
        summary[split] = {
            "records": len(records[split]),
            "problem_groups": len({r["problem_group"] for r in records[split]}),
            "languages": dict(Counter(r["language"] for r in records[split])),
            "supervised_turns": sum(
                len(r["supervised_assistant_indices"]) for r in records[split]
            ),
            "context_only_turns": sum(
                len(r["context_only_assistant_indices"]) for r in records[split]
            ),
            "records_sha256": digest(records[split]),
        }
    return {
        "records": records,
        "manifest": {
            "schema_version": 1,
            "source_sha256": digest(splits),
            "splits": summary,
            "prepared_material_sha256": digest(records),
            "tokenization_status": "pending_remote_qualification",
            "eligibility_scope": "supplied_receipts_not_independent_execution",
            "training_ready": False,
            "activation_authorized": False,
        },
    }
