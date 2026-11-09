"""Paired exact tool/argument scoring. No tool execution or automatic promotion."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any, cast

from venom_core.services.granite_operator.contract import digest

from .protocol import CALL_START, validate_calls

ARMS = {"B0", "F1", "L1"}
TRIAL_HASH_FIELDS = ("benchmark_sha256", "tools_sha256", "generation_sha256")


def score(text: str, tools: list[dict], expected: list[dict]) -> dict:
    try:
        calls = validate_calls(text, tools)
    except ValueError:
        return {
            "schema_valid": False,
            "exact": False,
            "unexpected_call": not expected
            and isinstance(text, str)
            and CALL_START in text,
        }
    actual = [{"name": call.name, "arguments": call.arguments} for call in calls]
    return {
        "schema_valid": True,
        "exact": sorted(map(digest, actual)) == sorted(map(digest, expected)),
        "unexpected_call": bool(actual) and not expected,
    }


def _validate_trial(row: dict) -> None:
    if (
        row.get("arm") not in ARMS
        or not row.get("case_id")
        or not row.get("problem_group")
        or any(
            not isinstance(row.get(key), str) or not row[key].strip()
            for key in TRIAL_HASH_FIELDS
        )
    ):
        raise ValueError("functiongemma_trial_identity_invalid")
    seconds = row.get("seconds")
    # Exact runtime type validation below still rejects non-numbers and booleans.
    seconds = cast(int | float, seconds)
    if type(seconds) not in {int, float} or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("functiongemma_timing_invalid")
    for name in ("exact", "schema_valid", "unexpected_call"):
        if type(row.get(name)) is not bool:
            raise ValueError("functiongemma_score_missing:" + name)


def _require_matched_pair(pair: dict) -> None:
    if set(pair) != ARMS:
        raise ValueError("functiongemma_incomplete_pairs")
    identities = {
        digest({key: row[key] for key in ("problem_group", *TRIAL_HASH_FIELDS)})
        for row in pair.values()
    }
    if len(identities) != 1:
        raise ValueError("functiongemma_unmatched_trials")


def _arm_metrics(group: list[dict]) -> dict:
    seconds = sorted(row["seconds"] for row in group)
    return {
        "trials": len(group),
        "exact_rate": sum(row["exact"] for row in group) / len(group),
        "schema_rate": sum(row["schema_valid"] for row in group) / len(group),
        "unexpected_calls": sum(row["unexpected_call"] for row in group),
        "p50_seconds": statistics.median(seconds),
        "p95_seconds": seconds[math.ceil(0.95 * len(seconds)) - 1],
    }


def compare(rows: Sequence[dict[str, Any]]) -> dict:
    if not rows:
        raise ValueError("functiongemma_trials_required")
    pairs: dict[str, dict[str, dict]] = {}
    for row in rows:
        _validate_trial(row)
        pair = pairs.setdefault(row["case_id"], {})
        if row["arm"] in pair:
            raise ValueError("functiongemma_duplicate_trial")
        pair[row["arm"]] = row
    for pair in pairs.values():
        _require_matched_pair(pair)
    arms = {
        arm: _arm_metrics([pair[arm] for pair in pairs.values()])
        for arm in sorted(ARMS)
    }
    return {
        "arms": arms,
        "groups": len({row["problem_group"] for row in rows}),
        "trials_sha256": digest(rows),
        "activation_allowed": False,
        "qualification": "diagnostic_only",
    }


def propose(
    tokenizer: Any,
    model: Any,
    messages: list[dict],
    tools: list[dict],
    *,
    context: int = 1024,
    max_new_tokens: int = 256,
) -> dict:
    """Return a validated proposal; existing executor must enforce permissions."""
    from .protocol import render_messages

    prompt = render_messages(tokenizer, messages, tools, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
    if inputs["input_ids"].shape[-1] + max_new_tokens > context:
        return {"decision": "escalate", "reason": "context_budget"}
    inputs = {key: value.to(model.device) for key, value in inputs.items()}
    import torch

    marker = tokenizer.convert_tokens_to_ids("<start_function_response>")
    if type(marker) is not int or marker < 0 or marker == tokenizer.unk_token_id:
        raise ValueError("functiongemma_response_stop_missing")
    turn_end = tokenizer.convert_tokens_to_ids("<end_of_turn>")
    if type(turn_end) is not int or turn_end < 0 or turn_end == tokenizer.unk_token_id:
        raise ValueError("functiongemma_turn_stop_missing")
    model.eval()
    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=max_new_tokens,
            eos_token_id=list(
                dict.fromkeys([tokenizer.eos_token_id, marker, turn_end])
            ),
        )
    output = generated[0][inputs["input_ids"].shape[-1] :]
    # A response marker is a boundary, never evidence of execution.
    text = tokenizer.decode(output, skip_special_tokens=False).split(
        "<start_function_response>", 1
    )[0]
    try:
        calls = validate_calls(text, tools)
    except ValueError:
        return {"decision": "escalate", "reason": "invalid_call"}
    return {
        "decision": "propose" if calls else "no_call",
        "calls": [{"name": c.name, "arguments": c.arguments} for c in calls],
        "execution_authorized": False,
    }
