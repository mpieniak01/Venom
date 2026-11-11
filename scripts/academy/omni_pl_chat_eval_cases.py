"""Load and materialize the authored Polish Omni chat pilot cases."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

CASES = Path(__file__).with_suffix(".jsonl")
TASKS = ("natural", "source", "correction", "long_dialogue")
SPLIT_COUNTS = {"dev": 8, "pilot": 16}


def _validate_case(case: Any) -> None:
    if not isinstance(case, dict):
        raise ValueError("Each evaluation case must be a JSON object")
    record_id = case.get("record_id")
    group_id = case.get("group_id")
    if not all(
        isinstance(value, str) and value.startswith("eval-") and len(value) > 5
        for value in (record_id, group_id)
    ):
        raise ValueError("Evaluation record and group IDs must begin with eval-")

    if case.get("split") not in ("dev", "pilot") or case.get("task") not in TASKS:
        raise ValueError(f"{record_id}: invalid split or task")
    if case.get("language") != "pl":
        raise ValueError(f"{record_id}: language must be pl")

    expected = case.get("expected")
    if (
        not isinstance(expected, list)
        or not expected
        or any(
            not isinstance(criterion, str) or not criterion.strip()
            for criterion in expected
        )
    ):
        raise ValueError(f"{record_id}: missing or empty scoring criteria")

    messages = case.get("messages")
    if not isinstance(messages, list) or len(messages) % 2 != 1:
        raise ValueError(f"{record_id}: history must end with a user turn")
    for index, message in enumerate(messages):
        role = "user" if index % 2 == 0 else "assistant"
        if (
            not isinstance(message, dict)
            or message.get("role") != role
            or not isinstance(message.get("content"), str)
            or not message["content"].strip()
        ):
            raise ValueError(f"{record_id}: invalid message at index {index}")

    user_turns = (len(messages) + 1) // 2
    expected_turns = {"natural": (1,), "source": (1,), "correction": (2,)}
    allowed = expected_turns.get(case["task"], range(8, 17))
    if user_turns not in allowed:
        raise ValueError(f"{record_id}: unexpected number of user turns")


def load_cases(path: Path = CASES, *, split: str | None = None) -> list[dict[str, Any]]:
    """Read the frozen definitions. Keep expected criteria out of model inputs."""
    if split is not None and split not in SPLIT_COUNTS:
        raise ValueError(f"Unknown evaluation split: {split}")

    with path.open(encoding="utf-8") as file:
        cases = [json.loads(line) for line in file if line.strip()]
    for case in cases:
        _validate_case(case)

    for key in ("record_id", "group_id"):
        if len({case[key] for case in cases}) != len(cases):
            raise ValueError(f"Evaluation cases have duplicate {key} values")

    prompts = {
        tuple(
            " ".join(message["content"].casefold().split())
            for message in case["messages"]
            if message["role"] == "user"
        )
        for case in cases
    }
    if len(prompts) != len(cases):
        raise ValueError("Evaluation cases have duplicate user histories")

    observed = Counter((case["split"], case["task"]) for case in cases)
    required = {
        (split_name, task): count
        for split_name, count in SPLIT_COUNTS.items()
        for task in TASKS
    }
    if observed != required:
        raise ValueError(f"Unexpected evaluation case distribution: {dict(observed)}")

    return [case for case in cases if split is None or case["split"] == split]


def write_split(path: Path, *, split: str) -> int:
    """Write a fresh JSONL file in UTF-8 and return the record count."""
    cases = load_cases(split=split)
    with path.open("x", encoding="utf-8", newline="\n") as file:
        for case in cases:
            file.write(json.dumps(case, ensure_ascii=False) + "\n")
    return len(cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=SPLIT_COUNTS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = write_split(args.output, split=args.split)
    print(f"{count} {args.split} cases written to {args.output}")


if __name__ == "__main__":
    main()
