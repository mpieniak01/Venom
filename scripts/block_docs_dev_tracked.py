#!/usr/bin/env python3
"""Block pushes when current branch diff contains docs_dev/ changes."""

from __future__ import annotations

import os
import subprocess
import sys


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _resolve_base_ref() -> str | None:
    explicit = os.getenv("DOCS_DEV_DIFF_BASE", "").strip()
    if explicit:
        return explicit
    try:
        upstream = _run_git(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
        ).stdout.strip()
        if upstream:
            return upstream
    except subprocess.CalledProcessError:
        pass
    return "origin/main"


def changed_docs_dev_files() -> list[str]:
    base_ref = _resolve_base_ref()
    if not base_ref:
        return []

    try:
        merge_base = _run_git(["merge-base", "HEAD", base_ref]).stdout.strip()
        if not merge_base:
            return []
        changed = _run_git(
            ["diff", "--name-only", "--diff-filter=ACMRD", f"{merge_base}...HEAD"]
        ).stdout.splitlines()
    except subprocess.CalledProcessError:
        return []

    return [path.strip() for path in changed if path.strip().startswith("docs_dev/")]


def main() -> int:
    changed = changed_docs_dev_files()
    if not changed:
        return 0

    print("ERROR: push blocked. Branch contains changes under local-only docs_dev/.")
    print("Changed files:")
    for path in changed:
        print(f"  - {path}")
    print("Fix: remove docs_dev paths from branch commits before push/PR.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
