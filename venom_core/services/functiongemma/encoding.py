"""Native token boundaries and sealed selected-decision labels; no truncation."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from venom_core.services.gemma4_operator.material import digest

from .dataset import validate_release
from .profile import MODEL, REVISION
from .protocol import CALL_END, render_messages

Json = dict[str, Any]


def _need(value: Any, code: str) -> None:
    if not value:
        raise ValueError("functiongemma_encoding_" + code)


def _seal(value: Json, field: str) -> str:
    return digest({key: item for key, item in value.items() if key != field})


def encode_decision(record: Json, tokenizer: Any, context: int = 1024) -> Json:
    """Supervise exactly the last selected assistant, including its native EOS."""
    _need(type(context) is int and context in {1024, 2048}, "context_invalid")
    messages = record.get("messages")
    _need(isinstance(messages, list) and len(messages) >= 2, "messages_invalid")
    messages = cast(list[Json], messages)
    target = len(messages) - 1
    _need(
        messages[target].get("role") == "assistant"
        and record.get("supervised_assistant_indices") == [target],
        "target_invalid",
    )
    full = render_messages(tokenizer, messages, record["tools"])
    prefix = render_messages(
        tokenizer, messages[:-1], record["tools"], add_generation_prompt=True
    )
    _need(full.startswith(prefix) and len(full) > len(prefix), "native_prefix_unstable")
    target_text = full[len(prefix) :]
    _need(
        any(target_text.rstrip().endswith(stop) for stop in ("<end_of_turn>", "<eos>"))
        or (
            bool(messages[target].get("tool_calls"))
            and target_text.rstrip().endswith(
                (CALL_END, CALL_END + "<start_function_response>")
            )
        ),
        "native_end_missing",
    )
    encoded = tokenizer(
        full, add_special_tokens=False, return_offsets_mapping=True, truncation=False
    )
    ids, offsets = encoded.get("input_ids"), encoded.get("offset_mapping")
    _need(
        isinstance(ids, list)
        and isinstance(offsets, list)
        and len(ids) == len(offsets)
        and 0 < len(ids) <= context,
        "sequence_exceeds_context",
    )
    _need(
        all(type(value) is int and 0 <= value < len(tokenizer) for value in ids),
        "token_ids_invalid",
    )

    def decode(values: list[int]) -> str:
        return tokenizer.decode(
            values, skip_special_tokens=False, clean_up_tokenization_spaces=False
        )

    _need(decode(ids) == full, "decode_mismatch")
    selected = []
    for index, pair in enumerate(offsets):
        _need(
            isinstance(pair, (list, tuple))
            and len(pair) == 2
            and all(type(v) is int for v in pair),
            "offset_invalid",
        )
        left, right = pair
        _need(0 <= left <= right <= len(full), "offset_invalid")
        _need(not left < len(prefix) < right, "token_crosses_boundary")
        if len(prefix) <= left < right:
            selected.append(index)
    _need(
        bool(selected) and selected == list(range(selected[0], len(ids))),
        "target_tokens_missing",
    )
    first = selected[0]
    _need(first > 0 and decode(ids[first:]) == target_text, "target_decode_mismatch")
    labels = [-100] * first + ids[first:]
    result = {
        "record_id": record["record_id"],
        "problem_group": record["problem_group"],
        "language": record["language"],
        "source_record_sha256": digest(record),
        "native_text_sha256": hashlib.sha256(full.encode()).hexdigest(),
        "input_ids": ids,
        "attention_mask": [1] * len(ids),
        "labels": labels,
        "assistant_token_spans": [
            {
                "message_index": target,
                "start": first,
                "end": len(ids),
                "supervised": True,
            }
        ],
    }
    result["sequence_sha256"] = _seal(result, "sequence_sha256")
    return result


def encode_release(release: Json, tokenizer: Any, context: int = 1024) -> Json:
    """Encode split decisions with the provided qualified native tokenizer."""
    records = validate_release(release)
    template = getattr(tokenizer, "chat_template", None)
    _need(isinstance(template, str) and bool(template), "template_required")
    template = cast(str, template)
    result = {
        "schema_version": 1,
        "kind": "functiongemma_encoded_release",
        "model": MODEL,
        "revision": REVISION,
        "context": context,
        "source_release_sha256": release["release_sha256"],
        "tokenizer_template_sha256": hashlib.sha256(template.encode()).hexdigest(),
        "records": {
            split: [encode_decision(row, tokenizer, context) for row in rows]
            for split, rows in records.items()
        },
        "packing": False,
        "mask_policy": "last_selected_assistant_only",
        "qualification": "CPU_TESTED_NOT_GPU_QUALIFIED",
    }
    result["encoded_release_sha256"] = _seal(result, "encoded_release_sha256")
    validate_encoded_release(result, context)
    return result


def validate_encoded_release(
    document: Json, context: int = 1024
) -> dict[str, list[Json]]:
    """Check sealed vectors, exact mask spans and split isolation on reload."""
    _need(
        isinstance(document, dict)
        and document.get("schema_version") == 1
        and document.get("kind") == "functiongemma_encoded_release",
        "release_invalid",
    )
    _need(
        document.get("encoded_release_sha256")
        == _seal(document, "encoded_release_sha256"),
        "release_hash_mismatch",
    )
    _need(
        document.get("model") == MODEL and document.get("revision") == REVISION,
        "base_mismatch",
    )
    _need(
        type(context) is int
        and context in {1024, 2048}
        and document.get("context") == context
        and document.get("packing") is False,
        "context_invalid",
    )
    records = document.get("records")
    _need(
        isinstance(records, dict)
        and {"train", "validation"} <= set(records)
        and set(records) <= {"train", "validation", "holdout"},
        "splits_invalid",
    )
    records = cast(dict[str, list[Json]], records)
    groups: dict[str, str] = {}
    identifiers: set[str] = set()
    for split, rows in records.items():
        _validate_encoded_split(rows, split, context, groups, identifiers)
    return records


def _validate_encoded_split(rows, split, context, groups, identifiers) -> None:
    _need(
        isinstance(rows, list) and (split == "holdout" or bool(rows)),
        "records_invalid",
    )
    for row in rows:
        _need(
            isinstance(row, dict)
            and row.get("sequence_sha256") == _seal(row, "sequence_sha256"),
            "sequence_hash_mismatch",
        )
        ident, group = row.get("record_id"), row.get("problem_group")
        _need(
            isinstance(ident, str) and ident and ident not in identifiers,
            "record_id_invalid",
        )
        _need(
            isinstance(group, str) and group and groups.get(group, split) == split,
            "group_leakage",
        )
        identifiers.add(ident)
        groups[group] = split
        _validate_encoded_sequence(row, context)


def _validate_encoded_sequence(row, context) -> None:
    ids, mask, labels = (
        row.get("input_ids"),
        row.get("attention_mask"),
        row.get("labels"),
    )
    _need(
        isinstance(ids, list)
        and 0 < len(ids) <= context
        and all(type(v) is int and v >= 0 for v in ids),
        "ids_invalid",
    )
    _need(
        mask == [1] * len(ids) and isinstance(labels, list) and len(labels) == len(ids),
        "vectors_invalid",
    )
    spans = row.get("assistant_token_spans")
    _need(
        isinstance(spans, list) and len(spans) == 1 and isinstance(spans[0], dict),
        "span_invalid",
    )
    span = spans[0]
    start, end = span.get("start"), span.get("end")
    _need(
        type(start) is int
        and type(end) is int
        and 0 < start < end == len(ids)
        and span.get("supervised") is True,
        "span_invalid",
    )
    _need(labels == [-100] * start + ids[start:], "mask_invalid")
