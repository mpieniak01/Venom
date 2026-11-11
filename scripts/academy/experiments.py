"""Run from the Venom checkout with python -m scripts.academy.experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from venom_core.config import SETTINGS
from venom_core.services.training_experiments.profiles import read_json, rows
from venom_core.services.training_experiments.service import ExperimentService


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(SETTINGS.ACADEMY_TRAINING_DIR) / "experiments"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("profiles")
    commands.add_parser("list")
    for action in ("validate", "run"):
        sub = commands.add_parser(action)
        sub.add_argument("profile_id")
        sub.add_argument("--recipe", type=Path)
        if action == "run":
            sub.add_argument("run_id")
    for action in ("status", "stop", "resume", "evaluate", "logs", "review", "report"):
        commands.add_parser(action).add_argument("run_id")
    submit = commands.add_parser("judgments")
    submit.add_argument("run_id")
    submit.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    try:
        result = execute(args)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        parser.exit(1, f"Experiment failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


def execute(args: argparse.Namespace):
    service = ExperimentService(args.root)
    if args.command == "profiles":
        return service.profiles()
    if args.command == "list":
        return service.list_runs()
    if args.command in {"validate", "run"}:
        recipe = read_json(args.recipe) if args.recipe else None
        if args.command == "validate":
            return service.validate(args.profile_id, recipe)
        return service.start(args.profile_id, args.run_id, recipe)
    if args.command == "judgments":
        payload = (
            rows(args.file) if args.file.suffix == ".jsonl" else read_json(args.file)
        )
        return service.submit(args.run_id, payload)
    return getattr(service, args.command)(args.run_id)


if __name__ == "__main__":
    main()
