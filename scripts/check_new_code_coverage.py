#!/usr/bin/env python3
"""Local pre-check for Sonar-like coverage on changed Python lines."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


class FileCoverage:
    def __init__(
        self, *, path: str, covered: int, total: int, uncovered_lines: list[int]
    ) -> None:
        self.path = path
        self.covered = covered
        self.total = total
        self.uncovered_lines = uncovered_lines

    @property
    def rate(self) -> float:
        return (self.covered / self.total) if self.total else 0.0


def _run_git_diff_once(diff_base: str, scope: str) -> tuple[int, str, str]:
    cmd = ["git", "diff", "-U0", f"{diff_base}...HEAD", "--", scope]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr.strip()


def _run_git_diff(diff_base: str, scope: str) -> str:
    candidates = [diff_base]
    if diff_base.startswith("origin/"):
        local_branch = diff_base.split("/", 1)[1]
        if local_branch and local_branch not in candidates:
            candidates.append(local_branch)
    for fallback in ("main", "HEAD~1"):
        if fallback not in candidates:
            candidates.append(fallback)

    errors: list[str] = []
    for candidate in candidates:
        code, stdout, stderr = _run_git_diff_once(candidate, scope)
        if code == 0:
            if candidate != diff_base:
                print(
                    f"WARN: diff base '{diff_base}' unavailable; using fallback '{candidate}'."
                )
            return stdout
        errors.append(f"[{candidate}] {stderr or 'unknown git diff error'}")

    raise RuntimeError(
        f"git diff failed for base '{diff_base}'. Attempts:\n" + "\n".join(errors)
    )


def _parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    current_file: str | None = None
    hunk_re = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if not line.startswith("@@") or not current_file:
            continue
        match = hunk_re.search(line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count == 0:
            continue
        target = changed.setdefault(current_file, set())
        for number in range(start, start + count):
            target.add(number)
    return changed


def _parse_sonar_coverage_exclusions(config_path: Path) -> list[str]:
    if not config_path.exists():
        return []

    lines = config_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("sonar.coverage.exclusions="):
            continue
        value = line.split("=", 1)[1]
        cursor = index
        while value.rstrip().endswith("\\") and cursor + 1 < len(lines):
            value = value.rstrip()[:-1] + lines[cursor + 1].strip()
            cursor += 1
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _is_excluded(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _load_coverage_hits(xml_path: Path) -> dict[str, dict[int, int]]:
    if not xml_path.exists():
        raise FileNotFoundError(f"Coverage XML not found: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()
    hits: dict[str, dict[int, int]] = {}
    for cls in root.findall(".//class"):
        filename = cls.attrib.get("filename", "")
        if not filename:
            continue
        normalized = (
            filename if filename.startswith("venom_core/") else f"venom_core/{filename}"
        )
        line_hits: dict[int, int] = {}
        for line in cls.findall("./lines/line"):
            line_no = int(line.attrib["number"])
            line_hits[line_no] = int(line.attrib.get("hits", "0"))
        hits[normalized] = line_hits
    return hits


def _calculate(
    changed_lines: dict[str, set[int]],
    coverage_hits: dict[str, dict[int, int]],
    exclusions: list[str],
) -> tuple[list[FileCoverage], int, int]:
    per_file: list[FileCoverage] = []
    total_coverable = 0
    total_covered = 0

    for path, lines in sorted(changed_lines.items()):
        if not path.startswith("venom_core/"):
            continue
        if _is_excluded(path, exclusions):
            continue
        file_hits = coverage_hits.get(path, {})
        coverable_lines = [line for line in sorted(lines) if line in file_hits]
        if not coverable_lines:
            continue
        uncovered = [line for line in coverable_lines if file_hits.get(line, 0) <= 0]
        covered = len(coverable_lines) - len(uncovered)
        total = len(coverable_lines)
        total_coverable += total
        total_covered += covered
        per_file.append(
            FileCoverage(
                path=path,
                covered=covered,
                total=total,
                uncovered_lines=uncovered,
            )
        )

    return per_file, total_covered, total_coverable


def analyze_changed_lines_coverage(
    *,
    coverage_xml: Path,
    sonar_config: Path,
    diff_base: str,
    scope: str,
) -> tuple[list[FileCoverage], int, int]:
    diff_text = _run_git_diff(diff_base=diff_base, scope=scope)
    changed_lines = _parse_changed_lines(diff_text)
    exclusions = _parse_sonar_coverage_exclusions(sonar_config)
    coverage_hits = _load_coverage_hits(coverage_xml)
    return _calculate(changed_lines, coverage_hits, exclusions)


def _summary_payload(
    per_file: list[FileCoverage],
    total_covered: int,
    total_coverable: int,
    min_coverage: float,
) -> dict[str, object]:
    rate = (total_covered / total_coverable * 100.0) if total_coverable else 100.0
    uncovered_files = [
        {
            "path": row.path,
            "uncovered_lines": row.uncovered_lines,
            "covered": row.covered,
            "total": row.total,
            "rate_percent": round(row.rate * 100.0, 2),
        }
        for row in per_file
        if row.uncovered_lines
    ]
    return {
        "total_covered": total_covered,
        "total_coverable": total_coverable,
        "rate_percent": round(rate, 2),
        "required_percent": round(min_coverage, 2),
        "pass": total_coverable == 0 or rate + 1e-9 >= min_coverage,
        "files": [
            {
                "path": row.path,
                "covered": row.covered,
                "total": row.total,
                "rate_percent": round(row.rate * 100.0, 2),
                "uncovered_lines": row.uncovered_lines,
            }
            for row in per_file
        ],
        "uncovered_files": uncovered_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check coverage for changed lines (Sonar pre-check)."
    )
    parser.add_argument(
        "--coverage-xml",
        default="test-results/sonar/python-coverage.xml",
        help="Path to Cobertura XML report.",
    )
    parser.add_argument(
        "--sonar-config",
        default="sonar-project.properties",
        help="Path to Sonar config (for coverage exclusions).",
    )
    parser.add_argument(
        "--diff-base",
        default="origin/main",
        help="Base branch/ref used in git diff (default: origin/main).",
    )
    parser.add_argument(
        "--scope",
        default="venom_core",
        help="Path scope for diff (default: venom_core).",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=80.0,
        help="Required minimum coverage %% on changed coverable lines.",
    )
    parser.add_argument(
        "--show-top",
        type=int,
        default=15,
        help="Number of lowest-coverage files to display.",
    )
    parser.add_argument(
        "--json-output",
        default="",
        help="Optional path to save machine-readable summary.",
    )
    args = parser.parse_args()

    per_file, total_covered, total_coverable = analyze_changed_lines_coverage(
        coverage_xml=Path(args.coverage_xml),
        sonar_config=Path(args.sonar_config),
        diff_base=args.diff_base,
        scope=args.scope,
    )

    payload = _summary_payload(
        per_file=per_file,
        total_covered=total_covered,
        total_coverable=total_coverable,
        min_coverage=args.min_coverage,
    )

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if total_coverable == 0:
        print("No coverable changed lines found (after exclusions).")
        return 0

    rate = (total_covered / total_coverable) * 100.0
    print(
        f"Changed lines coverage: {total_covered}/{total_coverable} = {rate:.1f}% "
        f"(required: {args.min_coverage:.1f}%)"
    )

    print("\nLowest coverage files (changed + included):")
    for item in sorted(per_file, key=lambda row: row.rate)[: max(args.show_top, 1)]:
        print(f"- {item.path}: {item.covered}/{item.total} ({item.rate * 100:.1f}%)")

    if rate + 1e-9 < args.min_coverage:
        print("\nFAIL: changed-lines coverage is below required threshold.")
        return 1

    print("\nPASS: changed-lines coverage meets the threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
