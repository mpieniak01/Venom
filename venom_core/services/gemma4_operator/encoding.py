"""CPU encoding with native template boundaries and selective assistant loss."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .material import digest, prepare_material, supervised_turn_indices
from .paths import checked_directory
from .profile import GemmaProfile
from .protocol import STOP_SEQUENCES, render_messages

MAX_CONTEXT = 4096
SPLITS = ("train", "validation")
Json = dict[str, Any]


def _need(condition: Any, code: str) -> None:
    if not condition:
        raise ValueError("gemma_encoding_" + code)


def _mapping(value: Any, code: str) -> Json:
    if not isinstance(value, dict):
        raise ValueError("gemma_encoding_" + code)
    return value


def _items(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("gemma_encoding_" + code)
    return value


def _integer(value: Any, code: str) -> int:
    if type(value) is not int:
        raise ValueError("gemma_encoding_" + code)
    return value


def _fingerprint(document: Json, key: str) -> str:
    return digest({name: value for name, value in document.items() if name != key})


def _release_records(release: Json, profile: GemmaProfile) -> dict[str, list[Json]]:
    _need(isinstance(release, dict), "release_required")
    _need(release.get("kind") == "gemma4_material_release", "release_kind_invalid")
    _need(
        release.get("release_sha256") == _fingerprint(release, "release_sha256"),
        "source_release_hash_mismatch",
    )
    _need(release.get("model_profile") == profile.identity(), "profile_mismatch")
    _need(
        type(release.get("schema_version")) is int and release["schema_version"] == 1,
        "schema_invalid",
    )
    payload = _mapping(release.get("training_payload"), "training_payload_required")
    records = _mapping(payload.get("records"), "training_splits_invalid")
    _need(
        set(records) == set(SPLITS),
        "training_splits_invalid",
    )
    _need(
        payload.get("records_sha256") == digest(records), "source_records_hash_mismatch"
    )
    checked = prepare_material(records)
    _need(checked["records"] == records, "canonical_records_mismatch")
    _need(
        payload.get("splits") == checked["manifest"]["splits"],
        "source_split_manifest_mismatch",
    )
    return records


def _tokenizer_identity(tokenizer: Any, profile: GemmaProfile) -> Json:
    profile.validate()
    _need(profile.context <= MAX_CONTEXT, "context_budget_exceeded")
    _need(getattr(tokenizer, "is_fast", False) is True, "fast_tokenizer_required")
    name = getattr(tokenizer, "name_or_path", None)
    if not isinstance(name, str) or not name:
        raise ValueError("gemma_encoding_materialized_tokenizer_required")
    snapshot = checked_directory(Path(name))
    files = profile.validate_snapshot(snapshot)
    backend = getattr(tokenizer, "backend_tokenizer", None)
    if backend is None or not callable(getattr(backend, "to_str", None)):
        raise ValueError("gemma_encoding_native_tokenizer_backend_required")
    actual = json.loads(backend.to_str())
    expected = json.loads((snapshot / "tokenizer.json").read_text(encoding="utf-8"))
    _need(actual == expected, "active_tokenizer_mismatch")
    return {
        "model": profile.model,
        "revision": profile.revision,
        "files": files,
        "backend_sha256": digest(actual),
        "vocabulary_size": len(tokenizer),
    }


def _decode(tokenizer: Any, ids: list[int]) -> str:
    return tokenizer.decode(
        ids, skip_special_tokens=False, clean_up_tokenization_spaces=False
    )


def _character_span(
    row: Json, index: int, tokenizer: Any, profile: GemmaProfile, full: str
) -> tuple[int, int]:
    marker = "VENOM_BOUNDARY_" + digest({"record": row["record_id"], "index": index})
    messages = row["messages"]
    probe = render_messages(
        tokenizer,
        messages[:index] + [{"role": "assistant", "content": marker}],
        row["tools"],
        profile,
        add_generation_prompt=False,
    )
    _need(probe.count(marker) == 1 and marker not in full, "boundary_probe_ambiguous")
    start = probe.index(marker)
    prefix = probe[:start]
    after = render_messages(
        tokenizer,
        messages[: index + 1],
        row["tools"],
        profile,
        add_generation_prompt=False,
    )
    _need(full.startswith(prefix), "native_prefix_unstable")
    if full.startswith(after):
        end = len(after)
    else:
        end = _continued_character_end(row, index, tokenizer, profile, full, marker)
    _need(end > start, "empty_assistant_target")
    return start, end


def _continued_character_end(
    row: Json, index: int, tokenizer: Any, profile: GemmaProfile, full: str, marker: str
) -> int:
    messages = row["messages"]
    current = messages[index]
    following = next((m for m in messages[index + 1 :] if m["role"] != "tool"), None)
    _need(
        not current.get("tool_calls")
        and following is not None
        and following["role"] == "assistant",
        "native_prefix_unstable",
    )
    _need(isinstance(current.get("content"), str), "continuation_content_invalid")
    changed = [dict(message) for message in messages]
    changed[index]["content"] += marker
    probe = render_messages(
        tokenizer, changed, row["tools"], profile, add_generation_prompt=False
    )
    _need(
        probe.count(marker) == 1 and probe.replace(marker, "", 1) == full,
        "native_prefix_unstable",
    )
    return probe.index(marker)


def _token_span(
    ids: list[int], offsets: list[Any], start: int, end: int, tokenizer: Any, text: str
) -> tuple[int, int]:
    selected: list[int] = []
    for index, offset in enumerate(offsets):
        _need(isinstance(offset, (tuple, list)) and len(offset) == 2, "offset_invalid")
        left, right = offset
        _need(
            type(left) is int
            and type(right) is int
            and 0 <= left <= right <= len(text),
            "offset_invalid",
        )
        _need(
            not (left < start < right or left < end < right),
            "token_crosses_turn_boundary",
        )
        if start <= left < right <= end:
            selected.append(index)
    _need(bool(selected), "assistant_tokens_missing")
    first, stop = selected[0], selected[-1] + 1
    _need(selected == list(range(first, stop)), "noncontiguous_turn_tokens")
    _need(
        _decode(tokenizer, ids[first:stop]) == text[start:end], "turn_decode_mismatch"
    )
    return first, stop


def _tokenize(full: str, tokenizer: Any, context: int) -> tuple[list[int], list[Any]]:
    tokenized = tokenizer(
        full, add_special_tokens=False, return_offsets_mapping=True, truncation=False
    )
    ids = _items(tokenized["input_ids"], "token_ids_invalid")
    offsets = _items(tokenized["offset_mapping"], "offset_count_mismatch")
    _need(0 < len(ids) <= context, "sequence_exceeds_context")
    _need(len(offsets) == len(ids), "offset_count_mismatch")
    _need(
        all(type(token) is int and 0 <= token < len(tokenizer) for token in ids),
        "token_ids_invalid",
    )
    _need(_decode(tokenizer, ids) == full, "full_decode_mismatch")
    return ids, offsets


def _native_stop(text: str, ids: list[int], tokenizer: Any, may_continue: bool) -> Json:
    ending = next(
        (token for token in STOP_SEQUENCES if text.rstrip().endswith(token)), None
    )
    ending_id = tokenizer.convert_tokens_to_ids(ending) if ending else None
    continued = ending is None and may_continue
    _need(ending is not None or continued, "native_end_marker_missing")
    _need(
        continued or (type(ending_id) is int and ending_id in ids),
        "native_end_token_missing",
    )
    return {
        "stop_token": ending,
        "stop_token_id": ending_id,
        "native_continuation": continued,
    }


def _assistant_span(
    row: Json,
    index: int,
    tokenizer: Any,
    profile: GemmaProfile,
    full: str,
    ids: list[int],
    offsets: list[Any],
    targets: list[int],
) -> Json:
    message = row["messages"][index]
    _need(not message.get("tool_responses"), "inline_tool_results_unsupported")
    start, end = _character_span(row, index, tokenizer, profile, full)
    first, stop = _token_span(ids, offsets, start, end, tokenizer, full)
    following = next(
        (m for m in row["messages"][index + 1 :] if m["role"] != "tool"), None
    )
    may_continue = (
        not message.get("tool_calls")
        and following is not None
        and following["role"] == "assistant"
    )
    return {
        "message_index": index,
        "start": first,
        "end": stop,
        "supervised": index in targets,
        **_native_stop(full[start:end], ids[first:stop], tokenizer, may_continue),
    }


def _encode_record(row: Json, tokenizer: Any, profile: GemmaProfile) -> Json:
    full = render_messages(
        tokenizer, row["messages"], row["tools"], profile, add_generation_prompt=False
    )
    ids, offsets = _tokenize(full, tokenizer, profile.context)
    targets = supervised_turn_indices(row)
    labels = [-100] * len(ids)
    spans: list[Json] = []
    for index, message in enumerate(row["messages"]):
        if message["role"] != "assistant":
            continue
        span = _assistant_span(
            row, index, tokenizer, profile, full, ids, offsets, targets
        )
        if span["supervised"]:
            first, stop = span["start"], span["end"]
            labels[first:stop] = ids[first:stop]
        spans.append(span)
    _need(
        labels[0] == -100 and any(value != -100 for value in labels),
        "loss_targets_invalid",
    )
    result = {
        "record_id": row["record_id"],
        "problem_group": row["problem_group"],
        "language": row["language"],
        "source_record_sha256": digest(row),
        "native_text_sha256": hashlib.sha256(full.encode()).hexdigest(),
        "input_ids": ids,
        "attention_mask": [1] * len(ids),
        "labels": labels,
        "supervised_assistant_indices": targets,
        "assistant_token_spans": spans,
    }
    result["sequence_sha256"] = _fingerprint(result, "sequence_sha256")
    return result


def encode_release(release: Json, tokenizer: Any, profile: GemmaProfile) -> Json:
    """Encode immutable train/validation records; never truncate or pack examples."""
    identity = _tokenizer_identity(tokenizer, profile)
    records = _release_records(release, profile)
    encoded = {
        split: [_encode_record(row, tokenizer, profile) for row in records[split]]
        for split in SPLITS
    }
    result = {
        "schema_version": 1,
        "kind": "gemma4_encoded_release",
        "model_profile": profile.identity(),
        "tokenizer_identity": identity,
        "source_release_sha256": release["release_sha256"],
        "source_records_sha256": release["training_payload"]["records_sha256"],
        "records": encoded,
        "packing": {"enabled": False, "sequence_boundary": "one_canonical_record"},
        "mask_policy": "selected_assistant_turns_only",
        "tokenization_status": "CPU_QUALIFIED",
        "training_ready": False,
        "training_started": False,
        "adapter_activation_authorized": False,
        "qualification": "tokenization_is_not_remote_loader_or_gpu_qualification",
        "split_summary": {split: _summary(rows) for split, rows in encoded.items()},
    }
    result["encoded_release_sha256"] = _fingerprint(result, "encoded_release_sha256")
    validate_encoded_release(result, profile)
    return result


def _validate_span(
    raw: Any, ids: list[int], selected: set[int], occupied: set[int]
) -> tuple[int, int, int, bool]:
    span = _mapping(raw, "span_invalid")
    index, start, end = (
        _integer(span.get(key), "span_invalid")
        for key in ("message_index", "start", "end")
    )
    _need(index > 0 and 0 < start < end <= len(ids), "span_bounds_invalid")
    supervised = span.get("supervised")
    if type(supervised) is not bool or supervised != (index in selected):
        raise ValueError("gemma_encoding_span_supervision_mismatch")
    positions = set(range(start, end))
    _need(not positions.intersection(occupied), "span_overlap")
    occupied.update(positions)
    continued = span.get("native_continuation")
    _need(type(continued) is bool, "span_stop_invalid")
    if continued:
        _need(
            span.get("stop_token") is None and span.get("stop_token_id") is None,
            "span_stop_invalid",
        )
    else:
        _need(span.get("stop_token") in STOP_SEQUENCES, "span_stop_invalid")
        _need(
            type(span.get("stop_token_id")) is int
            and span["stop_token_id"] in ids[start:end],
            "span_stop_invalid",
        )
    return index, start, end, supervised


def _validate_vectors(
    row: Json, profile: GemmaProfile, vocabulary: int
) -> tuple[list[int], list[int]]:
    ids = _items(row.get("input_ids"), "token_ids_invalid")
    labels = _items(row.get("labels"), "labels_invalid")
    attention = _items(row.get("attention_mask"), "attention_invalid")
    _need(0 < len(ids) <= profile.context, "sequence_exceeds_context")
    _need(
        all(type(value) is int and 0 <= value < vocabulary for value in ids),
        "token_ids_invalid",
    )
    _need(
        len(labels) == len(ids) and all(type(value) is int for value in labels),
        "labels_invalid",
    )
    _need(
        attention == [1] * len(ids) and all(type(value) is int for value in attention),
        "attention_invalid",
    )
    return ids, labels


def _validate_record(raw: Any, profile: GemmaProfile, vocabulary: int) -> Json:
    row = _mapping(raw, "record_invalid")
    _need(
        row.get("sequence_sha256") == _fingerprint(row, "sequence_sha256"),
        "sequence_hash_mismatch",
    )
    ids, labels = _validate_vectors(row, profile, vocabulary)
    targets = _items(row.get("supervised_assistant_indices"), "targets_invalid")
    _need(
        bool(targets) and all(type(value) is int and value > 0 for value in targets),
        "targets_invalid",
    )
    _need(len(set(targets)) == len(targets), "targets_invalid")
    spans = _items(row.get("assistant_token_spans"), "spans_invalid")
    _need(bool(spans), "spans_invalid")
    expected = [-100] * len(ids)
    occupied: set[int] = set()
    seen: set[int] = set()
    for span in spans:
        index, start, end, supervised = _validate_span(
            span, ids, set(targets), occupied
        )
        _need(index not in seen, "duplicate_assistant_span")
        seen.add(index)
        if supervised:
            expected[start:end] = ids[start:end]
    _need(set(targets) <= seen, "target_span_missing")
    _need(labels == expected, "label_leakage")
    _need(
        labels[0] == -100 and any(value != -100 for value in labels),
        "loss_targets_invalid",
    )
    return row


def _summary(rows: list[Json]) -> Json:
    return {
        "records": len(rows),
        "tokens": sum(len(row["input_ids"]) for row in rows),
        "supervised_tokens": sum(
            sum(value != -100 for value in row["labels"]) for row in rows
        ),
        "records_sha256": digest(rows),
    }


def _validate_identity(document: Json, profile: GemmaProfile) -> int:
    _need(document.get("model_profile") == profile.identity(), "profile_mismatch")
    identity = _mapping(
        document.get("tokenizer_identity"), "tokenizer_identity_mismatch"
    )
    _need(
        identity.get("files") == dict(profile.files)
        and identity.get("model") == profile.model
        and identity.get("revision") == profile.revision,
        "tokenizer_identity_mismatch",
    )
    vocabulary = _integer(identity.get("vocabulary_size"), "vocabulary_invalid")
    _need(vocabulary > 0, "vocabulary_invalid")
    return vocabulary


def _validate_group(
    row: Json, split: str, ids: set[str], groups: dict[str, str]
) -> None:
    ident, group = row.get("record_id"), row.get("problem_group")
    if not isinstance(ident, str) or not ident or ident in ids:
        raise ValueError("gemma_encoding_record_identity_invalid")
    if not isinstance(group, str) or not group or groups.get(group, split) != split:
        raise ValueError("gemma_encoding_group_leakage")
    ids.add(ident)
    groups[group] = split


def validate_encoded_release(
    document: Json, profile: GemmaProfile
) -> dict[str, list[Json]]:
    """Verify sealed CPU vectors before remote smoke/train without retokenizing.

    Hashes protect reproducibility and transport integrity; they do not authenticate
    a document supplied by an untrusted producer.
    """
    profile.validate()
    _need(profile.context <= MAX_CONTEXT, "context_budget_exceeded")
    _need(
        isinstance(document, dict) and document.get("kind") == "gemma4_encoded_release",
        "encoded_release_invalid",
    )
    _need(
        type(document.get("schema_version")) is int and document["schema_version"] == 1,
        "schema_invalid",
    )
    _need(
        document.get("encoded_release_sha256")
        == _fingerprint(document, "encoded_release_sha256"),
        "encoded_release_hash_mismatch",
    )
    vocabulary = _validate_identity(document, profile)
    _need(
        document.get("packing")
        == {"enabled": False, "sequence_boundary": "one_canonical_record"},
        "packing_invalid",
    )
    _need(
        document.get("mask_policy") == "selected_assistant_turns_only",
        "mask_policy_invalid",
    )
    records = _mapping(document.get("records"), "encoded_splits_invalid")
    _need(set(records) == set(SPLITS), "encoded_splits_invalid")
    summaries = _mapping(document.get("split_summary"), "split_summary_invalid")
    _need(set(summaries) == set(SPLITS), "split_summary_invalid")
    ids: set[str] = set()
    groups: dict[str, str] = {}
    for split, raw_rows in records.items():
        rows = _items(raw_rows, "empty_split")
        _need(bool(rows), "empty_split")
        for raw in rows:
            row = _validate_record(raw, profile, vocabulary)
            _validate_group(row, split, ids, groups)
        _need(summaries.get(split) == _summary(rows), "split_hash_mismatch")
    return records
