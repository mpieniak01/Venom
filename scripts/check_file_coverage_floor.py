#!/usr/bin/env python3
"""Fail when configured files are below minimum coverage percent."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _load_thresholds(path: Path) -> list[tuple[str, float]]:
    items: list[tuple[str, float]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "," not in line:
            raise ValueError(f"Invalid threshold line (expected file,min): {line}")
        file_path, min_percent = [part.strip() for part in line.split(",", 1)]
        items.append((file_path, float(min_percent)))
    return items


def _load_coverage_percent_by_file(coverage_xml: Path) -> dict[str, float]:
    root = ET.parse(coverage_xml).getroot()
    out: dict[str, float] = {}
    for cls in root.findall(".//class"):
        filename = cls.get("filename")
        line_rate = cls.get("line-rate")
        if not filename or line_rate is None:
            continue
        try:
            out[filename] = float(line_rate) * 100.0
        except ValueError:
            continue
    return out


def _candidates(path_text: str) -> list[str]:
    normalized = path_text.strip().replace("\\", "/").lstrip("./")
    candidates = [normalized]
    prefix = "venom_core/"
    if normalized.startswith(prefix):
        candidates.append(normalized[len(prefix) :])
    else:
        candidates.append(prefix + normalized)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-xml", required=True)
    parser.add_argument("--thresholds", required=True)
    args = parser.parse_args()

    coverage_xml = Path(args.coverage_xml)
    thresholds = Path(args.thresholds)

    if not coverage_xml.exists():
        print(f"ERROR: coverage xml not found: {coverage_xml}")
        return 2
    if not thresholds.exists():
        print(f"ERROR: thresholds file not found: {thresholds}")
        return 2

    threshold_items = _load_thresholds(thresholds)
    covered = _load_coverage_percent_by_file(coverage_xml)

    failures: list[str] = []
    missing: list[str] = []

    for file_path, min_percent in threshold_items:
        current = None
        for candidate in _candidates(file_path):
            if candidate in covered:
                current = covered[candidate]
                break
        if current is None:
            missing.append(file_path)
            continue
        if current + 1e-9 < min_percent:
            failures.append(
                f"{file_path}: {current:.1f}% < required {min_percent:.1f}%"
            )

    if missing:
        print("ERROR: missing files in coverage report:")
        for item in missing:
            print(f"  - {item}")
        return 1

    if failures:
        print("ERROR: coverage floor violations:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print(
        f"OK: coverage floors passed for {len(threshold_items)} files (threshold file: {thresholds})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
