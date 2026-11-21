"""Import and inspect versioned Academy quality records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from venom_core.config import SETTINGS
from venom_core.services.training_experiments.profiles import read_json
from venom_core.services.training_experiments.quality import QualityStore
from venom_core.services.training_experiments.quality_diagnostics import (
    DiagnosticMatrix,
    diagnose,
)
from venom_core.services.training_experiments.quality_history import (
    analyze_record,
    list_records,
)
from venom_core.services.training_experiments.quality_native import (
    get_record,
    register_parent_reference,
)
from venom_core.services.training_experiments.quality_schema import QualityBundle
from venom_core.services.training_experiments.service import ExperimentService


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(SETTINGS.ACADEMY_TRAINING_DIR) / "experiments"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("import").add_argument("bundle", type=Path)
    parent = commands.add_parser("register-parent")
    parent.add_argument("profile_id")
    parent.add_argument("adapter_id")
    parent.add_argument("checkpoint_step", type=int)
    parent.add_argument("generation", type=Path)
    parent.add_argument("record_id")
    commands.add_parser("list")
    commands.add_parser("show").add_argument("record_id")
    analyze = commands.add_parser("analyze")
    analyze.add_argument("record_id")
    analyze.add_argument("--reference-id")
    diagnostic = commands.add_parser("diagnose")
    diagnostic.add_argument("record_id")
    diagnostic.add_argument("matrix", type=Path)
    args = parser.parse_args(argv)
    experiments = ExperimentService(args.root)
    result: list[dict] | dict
    try:
        if args.command == "import":
            bundle = QualityBundle.model_validate(read_json(args.bundle))
            store = QualityStore(experiments.root)
            result = [store.import_record(record) for record in bundle.records]
        elif args.command == "register-parent":
            result = register_parent_reference(
                experiments,
                args.profile_id,
                args.adapter_id,
                args.generation,
                args.checkpoint_step,
                args.record_id,
            )
        elif args.command == "list":
            result = list_records(experiments)
        elif args.command == "show":
            result = get_record(experiments, args.record_id)
        elif args.command == "diagnose":
            matrix = DiagnosticMatrix.model_validate(read_json(args.matrix))
            result = diagnose(get_record(experiments, args.record_id), matrix)
        else:
            result = analyze_record(experiments, args.record_id, args.reference_id)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Quality failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
