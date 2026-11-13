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
    commands.add_parser("adapters")
    commands.add_parser("audit").add_argument("profile_id")
    for action in ("validate", "run"):
        sub = commands.add_parser(action)
        sub.add_argument("profile_id")
        sub.add_argument("--recipe", type=Path)
        if action == "run":
            sub.add_argument("run_id")
    for action in ("status", "stop", "resume", "evaluate", "logs", "review", "report"):
        commands.add_parser(action).add_argument("run_id")
    imported = commands.add_parser("import-results")
    imported.add_argument("run_id")
    imported.add_argument("file", type=Path)
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
    if args.command == "adapters":
        return service.adapters()
    if args.command == "audit":
        return service.data_audit(args.profile_id)
    if args.command == "list":
        return service.list_runs()
    if args.command in {"validate", "run"}:
        recipe = read_json(args.recipe) if args.recipe else None
        if args.command == "validate":
            return service.validate(args.profile_id, recipe)
        return service.start(args.profile_id, args.run_id, recipe)
    if args.command == "import-results":
        return service.import_results(args.run_id, args.file)
    if args.command == "judgments":
        payload = (
            rows(args.file) if args.file.suffix == ".jsonl" else read_json(args.file)
        )
        if isinstance(payload, dict):
            if (
                payload.keys() != {"checkpoint_step", "judgments"}
                or type(payload["checkpoint_step"]) is not int
            ):
                raise ValueError("experiment_checkpoint_review_changed")
            return service.submit(
                args.run_id,
                payload["judgments"],
                checkpoint_step=payload["checkpoint_step"],
            )
        return service.submit(args.run_id, payload)
    return getattr(service, args.command)(args.run_id)


if __name__ == "__main__":
    main()
