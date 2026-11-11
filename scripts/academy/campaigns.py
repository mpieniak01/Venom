"""Plan and control Academy campaigns from the same store as the web panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from venom_core.config import SETTINGS
from venom_core.services.training_experiments.campaign import CampaignService
from venom_core.services.training_experiments.campaign_schema import CampaignSpec
from venom_core.services.training_experiments.profiles import read_json
from venom_core.services.training_experiments.service import ExperimentService


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(SETTINGS.ACADEMY_TRAINING_DIR) / "experiments"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("plan").add_argument("manifest", type=Path)
    for action in (
        "status",
        "stop",
        "resume",
        "report",
        "retention-plan",
        "retention-apply",
        "start",
    ):
        cmd = sub.add_parser(action)
        cmd.add_argument("campaign_id")
        if action in {"start", "retention-apply"}:
            cmd.add_argument("plan_sha256")
    args = parser.parse_args(argv)
    service = CampaignService(ExperimentService(args.root))
    try:
        if args.command == "list":
            result = service.list()
        elif args.command == "plan":
            result = service.plan(CampaignSpec.model_validate(read_json(args.manifest)))
        else:
            action = getattr(service, args.command.replace("-", "_"))
            extra = [args.plan_sha256] if hasattr(args, "plan_sha256") else []
            result = action(args.campaign_id, *extra)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        parser.exit(1, f"Campaign failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
