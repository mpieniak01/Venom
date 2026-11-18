#!/usr/bin/env python3
"""Stage or execute one local frozen semantic judge v4 qualification."""

import argparse
import json
from pathlib import Path

from venom_core.services.training_experiments.semantic_judge_audit import (
    prepare_audit,
    run_audit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-seconds", type=int, default=1500)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--judge",
        choices=("semantic-local-v4", "semantic-local-v5", "semantic-local-v6"),
        default="semantic-local-v4",
    )
    args = parser.parse_args()
    context = prepare_audit(
        args.controls,
        args.output,
        args.manifest_sha256,
        args.run_id,
        args.max_seconds,
        judge_id=args.judge,
    )
    if not args.execute:
        print(json.dumps({"status": "staged_no_gpu", "output": str(context["root"])}))
        return 0
    result = run_audit(
        context, progress=lambda value: print(json.dumps(value), flush=True)
    )
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
