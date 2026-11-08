"""Inspect read-only model decisions and optionally replay authorized synthetic fixtures."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .cases import ACTIONS, context_of
from .score import (
    STOP_REASONS,
    decode_action,
    effect,
    fixture_skill,
    previous_reads,
    route,
)


async def assess_case(case, prediction, *, execute_fixtures=False):
    """Keep model proposals separate from the frozen fixture authorization."""
    record, oracle = case["record"], case["oracle"]
    action = None
    if prediction.get("stop_reason") in STOP_REASONS and not prediction.get("error"):
        try:
            action = decode_action(prediction["text"])
        except (ValueError, AttributeError, KeyError, TypeError, RecursionError):
            pass
    files = oracle["fixture"]["files"]
    calls, result, rendered = [], "invalid", None
    if action is not None:
        # Shadow evaluation uses the fixture specification as evidence. It does not
        # touch the filesystem or trust any target emitted by the model.
        previous = next(
            (
                returned
                for path, returned in previous_reads(record)
                if files.get(path) == returned
            ),
            None,
        )
        calls, result, rendered = route(action, context_of(record), record, previous)
    expected = oracle["expected_calls"]
    intent_correct = action == oracle["expected_action"]
    arguments_correct = calls == expected
    decision_correct = (
        intent_correct
        and arguments_correct
        and result == oracle["expected_result"]
        and rendered == oracle["reference_text"]
    )
    authorized = bool(calls) and decision_correct
    observed = None
    if execute_fixtures and authorized:
        with fixture_skill(files) as skill:
            observed = await effect(skill, calls)
    return {
        "record_id": record["record_id"],
        "family": oracle["family"],
        "language": record["language"],
        "action": action,
        "format_ok": action is not None,
        "intent_ok": intent_correct,
        "arguments_ok": arguments_correct,
        "decision_ok": decision_correct,
        "disposition": result,
        "fallback": "clarify"
        if result in {"invalid", "blocked", "clarify_read"}
        else None,
        "unexpected_proposal": action is not None
        and bool(ACTIONS[action])
        and not expected,
        "proposed_calls": calls,
        "fixture_authorized": authorized,
        "executed_calls": calls if observed is not None else [],
        "observed_effects": observed,
        "seconds": prediction.get("seconds"),
    }


async def assess(cases, predictions, *, execute_fixtures=False):
    """Require complete, unique input pairing before recording or executing anything."""
    ids = {case["record"]["record_id"] for case in cases}
    if len(ids) != len(cases) or ids != set(predictions):
        raise ValueError("prediction IDs must match the frozen cases")
    return [
        await assess_case(
            case,
            predictions[case["record"]["record_id"]],
            execute_fixtures=execute_fixtures,
        )
        for case in cases
    ]


def main():
    """Run in shadow mode unless the operator selects fixture replay."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-fixtures", action="store_true")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    raw = json.loads(args.predictions.read_text(encoding="utf-8"))["raw"]
    with args.output.open("x", encoding="utf-8") as output:
        rows = asyncio.run(assess(cases, raw, execute_fixtures=args.execute_fixtures))
        json.dump(
            {"mode": "fixtures" if args.execute_fixtures else "shadow", "rows": rows},
            output,
            ensure_ascii=False,
            indent=2,
        )
        output.write("\n")


if __name__ == "__main__":
    main()
