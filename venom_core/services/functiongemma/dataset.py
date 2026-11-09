"""Immutable FileSkill decision exports; group splits precede expansion."""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any, TypeGuard, cast

from venom_core.services.gemma4_operator.material import digest, supervised_turn_indices
from venom_core.services.gemma4_operator.protocol import (
    _validate_history,
    validate_tools,
)

from .protocol import FILE_TOOLS, validate_result_ids

Json = dict[str, Any]
SPLITS = ("train", "validation", "holdout")


def _text(row: Json, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("functiongemma_source_" + key + "_required")
    return value


def _valid_split_mapping(records: Any) -> TypeGuard[dict[str, Any]]:
    """Narrow mappings to supported splits with required train and validation keys."""
    return (
        isinstance(records, dict)
        and {"train", "validation"} <= set(records)
        and set(records) <= set(SPLITS)
    )


def _register_source(row, split, identifiers, groups) -> None:
    if not isinstance(row, dict) or row.get("split") != split:
        raise ValueError("functiongemma_source_split_invalid")
    ident, group, _language = (
        _text(row, key) for key in ("record_id", "problem_group", "language")
    )
    if ident in identifiers:
        raise ValueError("functiongemma_duplicate_source_id")
    identifiers.add(ident)
    if group in groups and groups[group] != split:
        raise ValueError("functiongemma_problem_group_leakage")
    groups[group] = split


def _source_allowed(row, split, skipped) -> bool:
    if split == "train" and row.get("training_allowed") is not True:
        skipped["training_not_allowed"] += 1
        return False
    if split != "train" and row.get("training_allowed") is not False:
        raise ValueError("functiongemma_evaluation_training_flag_invalid")
    return True


def _decision_record(row, split, prefix, tools, index) -> Json:
    return {
        "record_id": f"{row['record_id']}:decision:{index}",
        "source_record_id": row["record_id"],
        "source_record_sha256": digest(row),
        "source_assistant_index": index,
        "problem_group": row["problem_group"],
        "language": row["language"],
        "split": split,
        "training_allowed": split == "train",
        "tools": copy.deepcopy(tools),
        "messages": copy.deepcopy(prefix),
        "supervised_assistant_indices": [index],
        "context_only_assistant_indices": [
            i
            for i, message in enumerate(prefix)
            if message["role"] == "assistant" and i != index
        ],
    }


def _expand_decisions(row, split, tools, targets, skipped) -> list[Json]:
    outputs = []
    messages = row["messages"]
    for index in targets:
        prefix = messages[: index + 1]
        used = {
            call["function"]["name"]
            for message in prefix
            for call in message.get("tool_calls", [])
        }
        if not used <= FILE_TOOLS:
            skipped["unsupported_prefix"] += 1
            continue
        if not messages[index].get("tool_calls") and not messages[index].get("content"):
            skipped["empty_target"] += 1
            continue
        outputs.append(_decision_record(row, split, prefix, tools, index))
    return outputs


def _export_source(row, split, skipped) -> list[Json]:
    """Validate source history and export its eligible supervised decisions."""
    tools = row.get("tools")
    validators = validate_tools(cast(list[Json], tools))
    messages = row.get("messages")
    targets = supervised_turn_indices(row)
    messages = cast(list[Json], messages)
    _validate_history(messages, validators)
    validate_result_ids(messages)
    selected_tools = [tool for tool in tools if tool["function"]["name"] in FILE_TOOLS]
    if not selected_tools:
        skipped["no_fileskill_tools"] += 1
        return []
    return _expand_decisions(row, split, selected_tools, targets, skipped)


def export_decisions(records_by_split: dict[str, list[Json]]) -> Json:
    """Export selected decisions without dropping earlier operations from context."""
    if not _valid_split_mapping(records_by_split):
        raise ValueError("functiongemma_splits_invalid")
    groups: dict[str, str] = {}
    identifiers: set[str] = set()
    outputs: dict[str, list[Json]] = {split: [] for split in records_by_split}
    skipped: Counter[str] = Counter()
    for split, sources in records_by_split.items():
        if not isinstance(sources, list):
            raise ValueError("functiongemma_records_invalid")
        for row in sources:
            _register_source(row, split, identifiers, groups)
            if _source_allowed(row, split, skipped):
                outputs[split].extend(_export_source(row, split, skipped))
    release = {
        "schema_version": 1,
        "kind": "functiongemma_decision_release",
        "records": outputs,
        "source_records_sha256": digest(records_by_split),
        "records_sha256": digest(outputs),
        "manifest": {
            "counts": {split: len(rows) for split, rows in outputs.items()},
            "skipped": dict(skipped),
            "split_policy": "problem_group_before_decision_expansion",
            "sources_modified": False,
        },
    }
    release["release_sha256"] = digest(release)
    return release


def _validate_decision(row, split, seen, groups) -> None:
    """Validate one released decision against split, provenance and tool contracts."""
    if (
        not isinstance(row, dict)
        or row.get("split") != split
        or row.get("training_allowed") is not (split == "train")
    ):
        raise ValueError("functiongemma_release_split_invalid")
    ident, group = _text(row, "record_id"), _text(row, "problem_group")
    if ident in seen or groups.get(group, split) != split:
        raise ValueError("functiongemma_release_group_or_id_leakage")
    seen.add(ident)
    groups[group] = split
    tools = row.get("tools")
    validators = validate_tools(cast(list[Json], tools))
    if not set(validators) <= FILE_TOOLS:
        raise ValueError("functiongemma_release_tool_scope_invalid")
    messages = row.get("messages")
    targets = supervised_turn_indices(row)
    messages = cast(list[Json], messages)
    if targets != [len(messages) - 1]:
        raise ValueError("functiongemma_release_target_invalid")
    _validate_history(messages, validators)
    validate_result_ids(messages)


def validate_release(release: Json) -> dict[str, list[Json]]:
    """Verify the seal before tokenization."""
    if (
        not isinstance(release, dict)
        or release.get("kind") != "functiongemma_decision_release"
        or release.get("schema_version") != 1
    ):
        raise ValueError("functiongemma_release_invalid")
    if release.get("release_sha256") != digest(
        {key: value for key, value in release.items() if key != "release_sha256"}
    ):
        raise ValueError("functiongemma_release_hash_mismatch")
    records = release.get("records")
    if not _valid_split_mapping(records) or release.get("records_sha256") != digest(
        records
    ):
        raise ValueError("functiongemma_release_records_invalid")
    groups: dict[str, str] = {}
    seen: set[str] = set()
    for split, rows in records.items():
        if not isinstance(rows, list):
            raise ValueError("functiongemma_release_records_invalid")
        for row in rows:
            _validate_decision(row, split, seen, groups)
    return records
