#!/usr/bin/env python3
"""Block commits that stage files from docs_dev/."""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath


def staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_forbidden(path_str: str) -> bool:
    path = PurePosixPath(path_str)
    return path.parts[:1] == ("docs_dev",)


def main() -> int:
    blocked = [path for path in staged_files() if is_forbidden(path)]
    if not blocked:
        return 0

    print("ERROR: commit blocked. 'docs_dev/' is local-only and must not be committed.")
    print("Remove these staged paths:")
    for path in blocked:
        print(f"  - {path}")
    print("Hint: git restore --staged <path>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
