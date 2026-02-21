#!/usr/bin/env python3
"""Resolve lightweight pytest set for Sonar new-code coverage runs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

LIGHT_BLOCKED_MARKERS = (
    "integration",
    "requires_docker",
    "requires_docker_compose",
    "performance",
    "smoke",
)

PRIORITY_TEST_ORDER = ("tests/test_core_nervous_system.py",)

_PRIORITY_INDEX = {path: idx for idx, path in enumerate(PRIORITY_TEST_ORDER)}

SLOW_FASTLANE_MARKER = "slow_fastlane_exempt"
SLOW_FASTLANE_PATH_PATTERNS = (
    "integration",
    "benchmark",
    "test_core_nervous_system.py",
)

SLEEP_RE = re.compile(r"(?:time|asyncio)\.sleep\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)")
MARKER_RE = re.compile(
    r"pytest\.mark\.(integration|requires_docker|requires_docker_compose|performance|smoke)\b"
)


class CandidateInfo(NamedTuple):
    path: str
    source_rank: int
    estimated_seconds: float


def read_group(path: Path) -> list[str]:
    if not path.exists():
        return []
    tests: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        tests.append(item)
    return tests


def git_changed_files(diff_base: str) -> list[str]:
    cmd = ["git", "diff", "--name-only", f"{diff_base}...HEAD"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def all_test_files() -> list[str]:
    return sorted(
        str(path).replace("\\", "/") for path in Path("tests").rglob("test_*.py")
    )


def collect_changed_tests(changed_files: list[str]) -> set[str]:
    return {
        path
        for path in changed_files
        if path.startswith("tests/")
        and path.endswith(".py")
        and Path(path).name.startswith("test_")
    }


def related_tests_for_modules(
    changed_files: list[str], test_files: list[str]
) -> set[str]:
    related: set[str] = set()
    test_set = set(test_files)
    has_rg = shutil.which("rg") is not None

    for path in changed_files:
        if not (path.startswith("venom_core/") and path.endswith(".py")):
            continue

        module_path = path[:-3].replace("/", ".")
        module_stem = Path(path).stem
        direct_candidate = f"tests/test_{module_stem}.py"
        if direct_candidate in test_set:
            related.add(direct_candidate)

        if has_rg:
            rg_full = subprocess.run(
                [
                    "rg",
                    "-l",
                    "--fixed-strings",
                    module_path,
                    "tests",
                    "-g",
                    "**/test_*.py",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in rg_full.stdout.splitlines():
                if line:
                    related.add(line.strip().replace("\\", "/"))

            rg_stem = subprocess.run(
                [
                    "rg",
                    "-l",
                    "--fixed-strings",
                    module_stem,
                    "tests",
                    "-g",
                    "**/test_*.py",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in rg_stem.stdout.splitlines():
                if line:
                    related.add(line.strip().replace("\\", "/"))
        else:
            for test_path in test_files:
                path_obj = Path(test_path)
                if not path_obj.exists():
                    continue
                try:
                    text = path_obj.read_text(encoding="utf-8")
                except Exception:
                    continue
                if module_path in text or module_stem in text:
                    related.add(test_path)

    return related


def is_light_test(path: str) -> bool:
    file_path = Path(path)
    if not file_path.exists():
        return False

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0]
        if MARKER_RE.search(line):
            return False
    return True


def _has_marker(path: str, marker_name: str) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    content = p.read_text(encoding="utf-8")
    return f"pytest.mark.{marker_name}" in content


def _sleep_total_seconds(path: str) -> float:
    p = Path(path)
    if not p.exists():
        return 0.0
    total = 0.0
    for match in SLEEP_RE.findall(p.read_text(encoding="utf-8")):
        try:
            total += float(match)
        except ValueError:
            continue
    return total


def is_fast_safe_test(path: str) -> bool:
    if not is_light_test(path):
        return False
    if _has_marker(path, SLOW_FASTLANE_MARKER):
        return False

    lowered = path.lower()
    if any(pattern in lowered for pattern in SLOW_FASTLANE_PATH_PATTERNS):
        return False

    # Ogranicz testy ze znaczącymi sleepami do pełnej ścieżki testowej.
    if _sleep_total_seconds(path) > 2.0:
        return False

    return True


def _junit_classname_to_test_path(classname: str) -> str | None:
    parts = classname.split(".")
    if not parts or parts[0] != "tests":
        return None
    if parts[-1].startswith("test_"):
        return "/".join(parts) + ".py"
    if len(parts) >= 2:
        return "/".join(parts[:-1]) + ".py"
    return None


def load_junit_timings(xml_path: str | None) -> dict[str, float]:
    if not xml_path:
        return {}
    path = Path(xml_path)
    if not path.exists():
        return {}

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return {}

    totals: dict[str, float] = {}
    for tc in root.iter("testcase"):
        classname = tc.attrib.get("classname", "")
        test_path = _junit_classname_to_test_path(classname)
        if not test_path:
            continue
        try:
            sec = float(tc.attrib.get("time", "0") or "0")
        except ValueError:
            sec = 0.0
        totals[test_path] = totals.get(test_path, 0.0) + max(sec, 0.0)
    return totals


def estimate_test_cost(path: str, timings: dict[str, float]) -> float:
    if path in timings:
        return max(timings[path], 0.2)

    lowered = path.lower()
    cost = 0.8
    if "integration" in lowered:
        cost += 12.0
    if "benchmark" in lowered:
        cost += 18.0
    if "test_core_nervous_system.py" in lowered:
        cost += 50.0

    sleep_total = _sleep_total_seconds(path)
    if sleep_total > 0:
        cost += min(sleep_total * 2.5, 60.0)

    if _has_marker(path, SLOW_FASTLANE_MARKER):
        cost += 120.0

    return cost


def _build_candidate_infos(
    baseline_items: list[str],
    new_code_items: list[str],
    changed_tests: set[str],
    related_tests: set[str],
    timings: dict[str, float],
    exclude_slow_fastlane: bool,
) -> list[CandidateInfo]:
    selected = set(baseline_items) | set(new_code_items) | changed_tests | related_tests

    source_rank: dict[str, int] = {path: 4 for path in selected}
    for path in baseline_items:
        source_rank[path] = min(source_rank.get(path, 4), 2)
    for path in new_code_items:
        source_rank[path] = min(source_rank.get(path, 4), 2)
    for path in related_tests:
        source_rank[path] = min(source_rank.get(path, 4), 1)
    for path in changed_tests:
        source_rank[path] = min(source_rank.get(path, 4), 0)

    infos: list[CandidateInfo] = []
    for path in selected:
        if not is_light_test(path):
            continue
        if exclude_slow_fastlane and not is_fast_safe_test(path):
            continue
        infos.append(
            CandidateInfo(
                path=path,
                source_rank=source_rank.get(path, 4),
                estimated_seconds=estimate_test_cost(path, timings),
            )
        )

    infos.sort(
        key=lambda row: (
            row.source_rank,
            _PRIORITY_INDEX.get(row.path, len(PRIORITY_TEST_ORDER)),
            row.estimated_seconds,
            row.path,
        )
    )
    return infos


def _apply_budget(
    infos: list[CandidateInfo], time_budget_sec: float, max_tests: int
) -> list[CandidateInfo]:
    if max_tests > 0:
        infos = infos[:max_tests]

    if time_budget_sec <= 0:
        return infos

    total = 0.0
    selected: list[CandidateInfo] = []
    for info in infos:
        next_total = total + info.estimated_seconds
        if selected and next_total > time_budget_sec:
            continue
        selected.append(info)
        total = next_total

    if not selected and infos:
        selected = [infos[0]]

    return selected


def resolve_tests(
    baseline_group: Path,
    new_code_group: Path,
    include_baseline: bool,
    diff_base: str,
    *,
    time_budget_sec: float = 0.0,
    timings_junit_xml: str | None = None,
    exclude_slow_fastlane: bool = False,
    max_tests: int = 0,
) -> list[str]:
    baseline_items = read_group(baseline_group) if include_baseline else []
    new_code_items = read_group(new_code_group)

    changed_files = git_changed_files(diff_base)
    tests = all_test_files()
    changed_tests = collect_changed_tests(changed_files)
    related_tests = related_tests_for_modules(changed_files, tests)
    timings = load_junit_timings(timings_junit_xml)

    infos = _build_candidate_infos(
        baseline_items,
        new_code_items,
        changed_tests,
        related_tests,
        timings,
        exclude_slow_fastlane,
    )
    infos = _apply_budget(infos, time_budget_sec, max_tests)
    return [row.path for row in infos]


def resolve_tests_with_metadata(
    baseline_group: Path,
    new_code_group: Path,
    include_baseline: bool,
    diff_base: str,
    *,
    time_budget_sec: float = 0.0,
    timings_junit_xml: str | None = None,
    exclude_slow_fastlane: bool = False,
    max_tests: int = 0,
) -> tuple[list[str], list[dict[str, object]]]:
    baseline_items = read_group(baseline_group) if include_baseline else []
    new_code_items = read_group(new_code_group)

    changed_files = git_changed_files(diff_base)
    tests = all_test_files()
    changed_tests = collect_changed_tests(changed_files)
    related_tests = related_tests_for_modules(changed_files, tests)
    timings = load_junit_timings(timings_junit_xml)

    infos = _build_candidate_infos(
        baseline_items,
        new_code_items,
        changed_tests,
        related_tests,
        timings,
        exclude_slow_fastlane,
    )
    selected = _apply_budget(infos, time_budget_sec, max_tests)
    selected_set = {row.path for row in selected}

    metadata = [
        {
            "path": row.path,
            "source_rank": row.source_rank,
            "estimated_seconds": round(row.estimated_seconds, 3),
            "selected": row.path in selected_set,
        }
        for row in infos
    ]

    return [row.path for row in selected], metadata


def resolve_candidates_from_changed_files(
    changed_files: list[str], *, exclude_slow_fastlane: bool = False
) -> list[str]:
    tests = all_test_files()
    selected = collect_changed_tests(changed_files) | related_tests_for_modules(
        changed_files, tests
    )

    out: list[str] = []
    for path in sorted(selected):
        if not is_light_test(path):
            continue
        if exclude_slow_fastlane and not is_fast_safe_test(path):
            continue
        out.append(path)
    return out


# Backward-compatible aliases for legacy imports/tests.
_read_group = read_group
_git_changed_files = git_changed_files
_all_test_files = all_test_files
_collect_changed_tests = collect_changed_tests
_related_tests_for_modules = related_tests_for_modules
_is_light_test = is_light_test


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve lightweight tests for Sonar new-code coverage."
    )
    parser.add_argument(
        "--baseline-group",
        default="config/pytest-groups/ci-lite.txt",
        help="Path to baseline test group file.",
    )
    parser.add_argument(
        "--new-code-group",
        default="config/pytest-groups/sonar-new-code.txt",
        help="Path to Sonar new-code group file.",
    )
    parser.add_argument(
        "--include-baseline",
        type=int,
        choices=(0, 1),
        default=1,
        help="Include baseline group in resolved list (1/0).",
    )
    parser.add_argument(
        "--diff-base",
        default="origin/main",
        help="Git diff base for changed files.",
    )
    parser.add_argument(
        "--time-budget-sec",
        type=float,
        default=0.0,
        help="Optional time budget for selected tests. 0 disables budgeting.",
    )
    parser.add_argument(
        "--timings-junit-xml",
        default="test-results/sonar/python-junit.xml",
        help="Optional junit xml path used for time estimation.",
    )
    parser.add_argument(
        "--exclude-slow-fastlane",
        type=int,
        choices=(0, 1),
        default=0,
        help="Exclude tests considered too heavy for fast lane (1/0).",
    )
    parser.add_argument(
        "--max-tests",
        type=int,
        default=0,
        help="Optional hard cap for number of selected tests (0 = unlimited).",
    )
    parser.add_argument(
        "--debug-json",
        default="",
        help="Optional path to write metadata JSON.",
    )
    args = parser.parse_args()

    tests, metadata = resolve_tests_with_metadata(
        baseline_group=Path(args.baseline_group),
        new_code_group=Path(args.new_code_group),
        include_baseline=bool(args.include_baseline),
        diff_base=args.diff_base,
        time_budget_sec=args.time_budget_sec,
        timings_junit_xml=args.timings_junit_xml,
        exclude_slow_fastlane=bool(args.exclude_slow_fastlane),
        max_tests=args.max_tests,
    )
    if not tests:
        print("Brak lekkich testów po resolve.", file=sys.stderr)
        return 1

    if args.debug_json:
        debug_path = Path(args.debug_json)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(
            json.dumps(
                {
                    "selected": tests,
                    "count": len(tests),
                    "time_budget_sec": args.time_budget_sec,
                    "exclude_slow_fastlane": bool(args.exclude_slow_fastlane),
                    "metadata": metadata,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(
        f"Resolved {len(tests)} lightweight tests "
        f"(include_baseline={int(bool(args.include_baseline))}, diff_base={args.diff_base}, "
        f"budget={args.time_budget_sec:.1f}s, exclude_slow={int(bool(args.exclude_slow_fastlane))}).",
        file=sys.stderr,
    )
    for item in tests:
        print(item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
