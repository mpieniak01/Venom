"""Prepare or score a blind Academy diagnostic from a completed generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from venom_core.services.training_experiments.conversation_blind import (
    diagnostic_cutoff_ceiling,
    prepare_diagnostic_review,
    publish_blind_package,
    score_diagnostic_review,
)
from venom_core.services.training_experiments.profiles import read_json


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    for name in ("run", "panel", "dataset", "output"):
        prepare.add_argument(name, type=Path)
    ceiling = commands.add_parser("cutoff-ceiling")
    for name in ("run", "panel", "dataset"):
        ceiling.add_argument(name, type=Path)
    evaluate = commands.add_parser("score")
    for name in ("run", "package", "judgments"):
        evaluate.add_argument(name, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            package, private = prepare_diagnostic_review(
                args.run, read_json(args.panel), args.dataset
            )
            result = {
                "package": str(publish_blind_package(args.output, package, private))
            }
        elif args.command == "cutoff-ceiling":
            result = diagnostic_cutoff_ceiling(
                args.run, read_json(args.panel), args.dataset
            )
        else:
            result = score_diagnostic_review(
                args.run, args.package, read_json(args.judgments)
            )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"Conversation diagnostic failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
