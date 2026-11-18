"""Create revised reviewer controls; this command never runs inference."""

from __future__ import annotations

import argparse
from pathlib import Path

from venom_core.services.training_experiments.semantic_judge_controls import (
    build_controls,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-manifest-sha256", required=True)
    args = parser.parse_args()
    result = build_controls(args.source, args.output, args.source_manifest_sha256)
    print(result["control_version"], "prepared; independent data review required")


if __name__ == "__main__":
    main()
