"""Summarize real run receipts. Validation NLL is not operator task accuracy."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float:
    if (
        not values
        or not 0 <= fraction <= 1
        or not all(math.isfinite(x) and x >= 0 for x in values)
    ):
        raise ValueError("invalid_timing_samples")
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def summarize(root: Path) -> dict:
    status = json.loads((root / "status.json").read_text())
    if status["status"] != "PASS":
        raise ValueError("run_did_not_pass")
    stages = [
        json.loads(path.read_text()) for path in sorted(root.glob("*/metrics.json"))
    ]
    if not stages or len({s["fingerprint"] for s in stages}) != 1:
        raise ValueError("missing_or_inconsistent_stages")
    durations = []
    for stage in stages:
        previous = 0.0
        for step in stage["steps"]:
            current = step["elapsed_seconds"]
            durations.append(current - previous)
            previous = current
    seconds = sum(stage["training_seconds"] for stage in stages)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("invalid_training_duration")
    return {
        "status": "PASS",
        "fingerprint": stages[0]["fingerprint"],
        "global_step": stages[-1]["global_step"],
        "training_rows": stages[-1]["training_rows"],
        "validation_rows": stages[-1]["validation_rows"],
        "initial_validation_assistant_nll": stages[0]["initial_validation"][
            "assistant_nll"
        ],
        "final_validation_assistant_nll": stages[-1]["validation"]["assistant_nll"],
        "training_seconds": seconds,
        "load_seconds": sum(stage["load_seconds"] for stage in stages),
        "target_tokens": stages[-1]["target_tokens"],
        "target_tokens_per_training_second": stages[-1]["target_tokens"] / seconds,
        "optimizer_step_p50_seconds": percentile(durations, 0.5),
        "optimizer_step_p95_seconds": percentile(durations, 0.95),
        "peak_allocated_bytes": max(s["peak_allocated_bytes"] for s in stages),
        "peak_reserved_bytes": max(s["peak_reserved_bytes"] for s in stages),
        "checks_by_stage": {s["stage"]: s["checks"] for s in stages},
        "limitation": "Training throughput and validation NLL; not held-out operator accuracy or latency.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.run), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
