#!/usr/bin/env python3
"""Manual runtime maintenance cleanup for logs/data retention."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a plain script (not only module) from repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run runtime retention cleanup for logs/data directories."
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override retention days (default: SETTINGS.RUNTIME_RETENTION_DAYS).",
    )
    return parser.parse_args()


def main() -> int:
    from venom_core.config import SETTINGS
    from venom_core.jobs.scheduler import cleanup_runtime_files

    args = parse_args()
    retention_days = (
        args.retention_days
        if args.retention_days is not None
        else SETTINGS.RUNTIME_RETENTION_DAYS
    )
    summary = cleanup_runtime_files(
        retention_days=retention_days,
        target_dirs=SETTINGS.RUNTIME_RETENTION_TARGETS,
        base_dir=Path(SETTINGS.REPO_ROOT),
    )
    print(
        "runtime_cleanup:",
        f"retention_days={retention_days}",
        f"targets_scanned={summary['targets_scanned']}",
        f"deleted_files={summary['deleted_files']}",
        f"deleted_dirs={summary['deleted_dirs']}",
        f"freed_bytes={summary['freed_bytes']}",
        f"skipped={summary['skipped']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
