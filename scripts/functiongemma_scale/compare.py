"""Report paired gains, retained reads, and performance on common correct cases."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from venom_core.services.granite_operator.contract import write_json


def eligible(totals):
    tool = totals["tool_cases"]
    text = totals["text_cases"]
    return (
        bool(tool and text)
        and totals["tool_correct"] * 100 >= tool * 98
        and totals["text_correct"] * 100 >= text * 95
        and not any(
            totals[key]
            for key in (
                "invalid",
                "unexpected_call",
                "unexpected_execution",
                "possible_write_claim",
            )
        )
    )


def timing(values):
    if not values or any(value is None for value in values):
        return None
    return {
        "p50_seconds": median(values),
        "p95_seconds": sorted(values)[math.ceil(0.95 * len(values)) - 1],
    }


def compare(control, candidate):
    if not control.get("case_sha256") or control["case_sha256"] != candidate.get(
        "case_sha256"
    ):
        raise ValueError("comparison requires the same sealed cases")
    pairs = {}
    for document in (control, candidate):
        values = document["verdicts"]
        pairs[len(pairs)] = {row["record_id"]: row for row in values}
        if len(pairs[len(pairs) - 1]) != len(values):
            raise ValueError("duplicated case IDs")
    first, second = pairs[0], pairs[1]
    if first.keys() != second.keys():
        raise ValueError("comparison requires the same case IDs")
    changes = Counter()
    groups = defaultdict(Counter)
    per_family = defaultdict(Counter)
    per_language = defaultdict(Counter)
    lost_reads, common_first, common_second = [], [], []
    for rid, before in first.items():
        after = second[rid]
        fields = ("group", "language", "family", "tool_task")
        if any(before[key] != after[key] for key in fields):
            raise ValueError(f"case metadata changed: {rid}")
        delta = (before["correct"], after["correct"])
        state = {
            (False, True): "gained",
            (True, False): "lost",
            (True, True): "both",
            (False, False): "neither",
        }[delta]
        changes[state] += 1
        groups[before["group"]][state] += 1
        per_family[f"{before['language']}/{before['family']}"][state] += 1
        per_language[before["language"]][state] += 1
        if state == "lost" and before["family"] in {"read", "discovery", "exists"}:
            lost_reads.append(rid)
        if state == "both":
            common_first.append(before["seconds"])
            common_second.append(after["seconds"])
    return {
        "case_sha256": control["case_sha256"],
        "control_raw_sha256": control.get("raw_sha256"),
        "candidate_raw_sha256": candidate.get("raw_sha256"),
        "paired": changes,
        "by_group": groups,
        "by_family": per_family,
        "by_language": per_language,
        "lost_correct_reads": lost_reads,
        "common_correct_timing": {
            "count": len(common_first),
            "control": timing(common_first),
            "candidate": timing(common_second),
        },
        "candidate_passes_quality_thresholds": eligible(candidate["total"])
        and not lost_reads,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "candidate", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = compare(
        json.loads(args.control.read_text()), json.loads(args.candidate.read_text())
    )
    write_json(args.output, result)
    print(result["paired"], "lost correct reads", len(result["lost_correct_reads"]))


if __name__ == "__main__":
    main()
