#!/usr/bin/env python3
"""Bind Sonar input reports to the checkout that generated them."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPORTS = ("python-coverage.xml", "python-junit.xml")
MANIFEST = "report-manifest.json"


def _revision(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Expected the 40-character checkout SHA")
    return value


def _report_metadata(directory: Path, revision: str) -> dict[str, object]:
    hashes = {}
    for name in REPORTS:
        content = (directory / name).read_bytes()
        root = ET.fromstring(content)
        allowed = {"coverage"} if name == REPORTS[0] else {"testsuite", "testsuites"}
        if root.tag not in allowed:
            raise ValueError(f"Unexpected XML root in {name}: {root.tag}")
        if name == REPORTS[0] and not list(root.iter("class")):
            raise ValueError("Coverage report contains no source files")
        if name == REPORTS[1]:
            cases = list(root.iter("testcase"))
            if not cases or all(case.find("skipped") is not None for case in cases):
                raise ValueError("JUnit report contains no executed tests")
        hashes[name] = hashlib.sha256(content).hexdigest()
    return {"version": 1, "revision": _revision(revision), "sha256": hashes}


def write_manifest(directory: Path, revision: str) -> None:
    metadata = _report_metadata(directory, revision)
    (directory / MANIFEST).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def verify_manifest(directory: Path, revision: str) -> None:
    saved = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    actual = _report_metadata(directory, revision)
    if saved != actual:
        raise ValueError("Sonar reports differ from manifest or checkout revision")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("write", "verify"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    try:
        if args.mode == "write":
            write_manifest(args.directory, args.revision)
        else:
            verify_manifest(args.directory, args.revision)
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"ERROR: invalid Sonar reports: {exc}", file=sys.stderr)
        return 1
    print(f"Sonar reports {args.mode} OK for checkout {args.revision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
