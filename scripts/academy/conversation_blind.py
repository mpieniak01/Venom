"""Prepare a blinded 0A review package from sealed Academy evaluations."""

from __future__ import annotations

import argparse
from pathlib import Path

from venom_core.services.training_experiments.conversation_blind import (
    prepare_blind_package,
    publish_blind_package,
)
from venom_core.services.training_experiments.profiles import read_json


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("pending", "panel", "dataset", "parent", "candidate", "output"):
        parser.add_argument("--" + argument, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        package, private = prepare_blind_package(
            read_json(args.pending),
            read_json(args.panel),
            args.dataset,
            args.parent,
            args.candidate,
        )
        target = publish_blind_package(args.output, package, private)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"Blind review failed: {exc}\n")
    print(f"Review package saved to {target}.")
    print("Share reviewer.json and judgments-template.json with the reviewer.")


if __name__ == "__main__":
    main()
