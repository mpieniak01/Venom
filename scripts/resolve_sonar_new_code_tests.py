#!/usr/bin/env python3
"""Resolve lightweight pytest set for Sonar new-code coverage runs."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

LIGHT_BLOCKED_MARKERS = (
    "integration",
    "requires_docker",
    "requires_docker_compose",
    "performance",
    "smoke",
)


def _read_group(path: Path) -> list[str]:
    if not path.exists():
        return []
    tests: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        tests.append(item)
    return tests


def _git_changed_files(diff_base: str) -> list[str]:
    cmd = ["git", "diff", "--name-only", f"{diff_base}...HEAD"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _all_test_files() -> list[str]:
    return sorted(
        str(path).replace("\\", "/") for path in Path("tests").glob("test_*.py")
    )


def _collect_changed_tests(changed_files: list[str]) -> set[str]:
    return {
        path
        for path in changed_files
        if path.startswith("tests/test_") and path.endswith(".py")
    }


def _related_tests_for_modules(
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
            # Search tests referencing full dotted module path.
            rg_full = subprocess.run(
                [
                    "rg",
                    "-l",
                    "--fixed-strings",
                    module_path,
                    "tests",
                    "-g",
                    "test_*.py",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in rg_full.stdout.splitlines():
                if line:
                    related.add(line.strip().replace("\\", "/"))

            # Fallback by module stem to catch local imports/helpers.
            rg_stem = subprocess.run(
                [
                    "rg",
                    "-l",
                    "--fixed-strings",
                    module_stem,
                    "tests",
                    "-g",
                    "test_*.py",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in rg_stem.stdout.splitlines():
                if line:
                    related.add(line.strip().replace("\\", "/"))
        else:
            # Portable fallback for environments without ripgrep.
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


def _is_light_test(path: str) -> bool:
    file_path = Path(path)
    if not file_path.exists():
        return False

    marker_re = re.compile(
        r"pytest\.mark\.(integration|requires_docker|requires_docker_compose|performance|smoke)\b"
    )
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0]
        if marker_re.search(line):
            return False
    return True


def resolve_tests(
    baseline_group: Path,
    new_code_group: Path,
    include_baseline: bool,
    diff_base: str,
) -> list[str]:
    selected: set[str] = set(_read_group(new_code_group))
    if include_baseline:
        selected.update(_read_group(baseline_group))

    changed_files = _git_changed_files(diff_base)
    all_tests = _all_test_files()
    selected.update(_collect_changed_tests(changed_files))
    selected.update(_related_tests_for_modules(changed_files, all_tests))

    light_tests = sorted(path for path in selected if _is_light_test(path))
    return light_tests


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
    args = parser.parse_args()

    tests = resolve_tests(
        baseline_group=Path(args.baseline_group),
        new_code_group=Path(args.new_code_group),
        include_baseline=bool(args.include_baseline),
        diff_base=args.diff_base,
    )
    if not tests:
        print("Brak lekkich testów po resolve.", file=sys.stderr)
        return 1

    print(
        f"Resolved {len(tests)} lightweight tests "
        f"(include_baseline={int(bool(args.include_baseline))}, diff_base={args.diff_base}).",
        file=sys.stderr,
    )
    for item in tests:
        print(item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
