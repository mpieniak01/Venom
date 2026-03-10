#!/usr/bin/env python3
"""Audit Makefile targets vs .PHONY declarations."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TARGET_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?![=])")


def parse_phony(makefile_text: str) -> set[str]:
    lines = makefile_text.splitlines()
    items: list[str] = []
    collecting = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(".PHONY:"):
            collecting = True
            payload = stripped[len(".PHONY:") :].strip()
            if payload:
                items.extend(payload.replace("\\", " ").split())
            if not stripped.endswith("\\"):
                collecting = False
            continue

        if collecting:
            payload = stripped
            if payload:
                items.extend(payload.replace("\\", " ").split())
            if not stripped.endswith("\\"):
                collecting = False

    return set(items)


def parse_targets(path: Path) -> set[str]:
    targets: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("\t"):
            continue
        match = TARGET_RE.match(line)
        if match:
            targets.add(match.group(1))
    return targets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Makefile .PHONY vs target definitions."
    )
    parser.add_argument(
        "--makefile", default="Makefile", help="Path to top-level Makefile."
    )
    parser.add_argument(
        "--modules-dir",
        default="make",
        help="Directory with modularized *.mk includes (default: make).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    makefile_path = Path(args.makefile).resolve()
    modules_dir = Path(args.modules_dir).resolve()

    if not makefile_path.exists():
        print(f"ERROR: missing makefile: {makefile_path}")
        return 2

    makefile_text = makefile_path.read_text(encoding="utf-8")
    phony_targets = parse_phony(makefile_text)

    defined_targets = parse_targets(makefile_path)
    if modules_dir.exists():
        for module_file in sorted(modules_dir.glob("*.mk")):
            defined_targets.update(parse_targets(module_file))

    missing_defs = sorted(item for item in phony_targets if item not in defined_targets)
    not_phony = sorted(
        item
        for item in defined_targets
        if item not in phony_targets
        and not item.startswith(".")
        and not item.startswith("_")
    )

    print("Make targets audit")
    print(f"- .PHONY count: {len(phony_targets)}")
    print(f"- defined target count: {len(defined_targets)}")
    print(f"- phony_without_definition: {len(missing_defs)}")
    print(f"- definition_without_phony: {len(not_phony)}")

    if missing_defs:
        print("\n❌ .PHONY targets without definition:")
        for item in missing_defs:
            print(f"  - {item}")

    if not_phony:
        print("\n⚠️ Defined targets not listed in .PHONY:")
        for item in not_phony:
            print(f"  - {item}")

    if missing_defs:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
