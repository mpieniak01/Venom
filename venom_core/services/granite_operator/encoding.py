"""Native Granite serialization with assistant-only labels, including function calls."""

from __future__ import annotations

from typing import Any

from .contract import assistant_targets


def _ids(value: Any) -> list:
    """Unwrap current Transformers BatchEncoding and plain lists consistently."""
    result = value["input_ids"] if hasattr(value, "keys") else value
    if result and isinstance(result[0], list):
        if len(result) != 1:
            raise ValueError("granite_unexpected_batch")
        result = result[0]
    return result


def encode(row: dict, tokenizer: Any, context: int) -> dict[str, list[int]]:
    """Mask actual assistant spans; never train on system/user/tool observations."""
    options = {
        "tools": row["tools"],
        "enable_thinking": False,
        "truncate_history_thinking": False,
    }
    text = tokenizer.apply_chat_template(
        row["messages"], tokenize=False, add_generation_prompt=False, **options
    )
    spans = []
    targets = assistant_targets(row)
    for index, message in enumerate(row["messages"]):
        if message["role"] != "assistant" or index not in targets:
            continue
        prefix = tokenizer.apply_chat_template(
            row["messages"][:index],
            tokenize=False,
            add_generation_prompt=True,
            **options,
        )
        through = tokenizer.apply_chat_template(
            row["messages"][: index + 1],
            tokenize=False,
            add_generation_prompt=False,
            **options,
        )
        if not through.startswith(prefix) or not text.startswith(through):
            raise ValueError("granite_non_prefix_template")
        spans.append((len(prefix), len(through)))
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    ids = _ids(encoded)
    offsets = encoded["offset_mapping"]
    if (
        offsets
        and isinstance(offsets[0], list)
        and offsets[0]
        and isinstance(offsets[0][0], (list, tuple))
    ):
        offsets = offsets[0]
    if len(ids) > context or len(ids) != len(offsets):
        raise ValueError("granite_context_or_offsets_invalid")
    labels = []
    for token, (start, end) in zip(ids, offsets):
        contained = any(a <= start < end <= b for a, b in spans)
        overlaps = any(start < b and end > a for a, b in spans)
        if overlaps and not contained:
            raise ValueError("granite_token_crosses_role_boundary")
        labels.append(token if contained else -100)
    if not spans or not any(x != -100 for x in labels):
        raise ValueError("granite_empty_assistant_mask")
    native = _ids(
        tokenizer.apply_chat_template(
            row["messages"], tokenize=True, add_generation_prompt=False, **options
        )
    )
    if ids != native:
        raise ValueError("granite_tokenization_mismatch")
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": labels}


def collate(rows: list[dict], pad: int, torch: Any) -> dict:
    """Right-pad labels with ignore_index, without severing conversations."""
    length = max(len(r["input_ids"]) for r in rows)
    return {
        key: torch.tensor(
            [
                r[key]
                + [(-100 if key == "labels" else 0 if key == "attention_mask" else pad)]
                * (length - len(r[key]))
                for r in rows
            ]
        )
        for key in ("input_ids", "attention_mask", "labels")
    }
