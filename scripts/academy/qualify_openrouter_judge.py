"""Explicit operator CLI for preparing and running Luna audits and targeted regressions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from venom_core.services.training_experiments import semantic_openrouter_audit as audit
from venom_core.services.training_experiments import (
    semantic_openrouter_targeted as targeted,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--controls", type=Path, required=True)
    prepare.add_argument("--data-review", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--controls-manifest-sha256", required=True)
    prepare.add_argument("--data-review-sha256", required=True)
    prepare.add_argument("--budget-usd", required=True)
    prepare.add_argument("--max-seconds", type=float, required=True)
    prepare.add_argument(
        "--holdout-max-request-usd",
        required=True,
        help="Explicit hard cap per held-out request; not a measured estimate",
    )
    prepare.add_argument("--max-request-usd", default="0.01")
    prepare.add_argument("--initial-accounted-usd", default="0")
    prepare.add_argument("--initial-unknown-reserved-usd", default="0")
    regression = commands.add_parser("prepare-targeted")
    regression.add_argument("--panel", type=Path, required=True)
    regression.add_argument("--panel-sha256", required=True)
    regression.add_argument("--output", type=Path, required=True)
    regression.add_argument("--budget-usd", required=True)
    regression.add_argument("--max-seconds", type=float, required=True)
    regression.add_argument("--max-request-usd", default="0.01")
    regression.add_argument("--initial-accounted-usd", default="0")
    regression.add_argument("--initial-unknown-reserved-usd", default="0")
    verify = commands.add_parser(
        "verify-targeted", help="Check a published panel and its seal offline"
    )
    verify.add_argument("--audit-root", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--audit-root", type=Path, required=True)
    execute.add_argument(
        "--execute",
        action="store_true",
        help="Operator-requested real OpenRouter requests",
    )
    args = parser.parse_args()
    if args.action == "prepare":
        result = audit.prepare(
            args.controls,
            args.data_review,
            args.output,
            controls_sha256=args.controls_manifest_sha256,
            data_review_sha256=args.data_review_sha256,
            budget_usd=args.budget_usd,
            max_seconds=args.max_seconds,
            holdout_max_request_usd=args.holdout_max_request_usd,
            max_request_usd=args.max_request_usd,
            initial_accounted_usd=args.initial_accounted_usd,
            initial_unknown_reserved_usd=args.initial_unknown_reserved_usd,
        )
    elif args.action == "prepare-targeted":
        result = targeted.prepare(
            args.panel,
            args.output,
            panel_sha256=args.panel_sha256,
            budget_usd=args.budget_usd,
            max_seconds=args.max_seconds,
            max_request_usd=args.max_request_usd,
            initial_accounted_usd=args.initial_accounted_usd,
            initial_unknown_reserved_usd=args.initial_unknown_reserved_usd,
        )
    elif args.action == "verify-targeted":
        result = targeted.verify(args.audit_root)
    else:
        result = audit.run(args.audit_root, execute=args.execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] not in {
        "prepared_not_qualified",
        "verified_targeted",
        "passed",
        "targeted_review_required",
    }:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
