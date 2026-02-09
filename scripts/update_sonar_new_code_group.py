#!/usr/bin/env python3
"""Auto-update Sonar new-code pytest group from staged backend/test changes."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

GROUP_PATH = Path("config/pytest-groups/sonar-new-code.txt")
AUTO_SECTION_HEADER = "# AUTO-ADDED by pre-commit (staged backend/test changes)"


def _load_resolver_module():
    resolver_path = Path("scripts/resolve_sonar_new_code_tests.py")
    spec = importlib.util.spec_from_file_location(
        "resolve_sonar_new_code_tests", resolver_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load resolver module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_staged_files() -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--cached"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff --cached failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _read_group_items(path: Path) -> list[str]:
    if not path.exists():
        return []
    items: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


def _append_auto_items(path: Path, new_items: list[str]) -> None:
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = content.splitlines()

    if lines and lines[-1].strip():
        lines.append("")

    if AUTO_SECTION_HEADER not in content:
        lines.append(AUTO_SECTION_HEADER)

    lines.extend(new_items)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    staged = _git_staged_files()
    relevant_changes = [
        p
        for p in staged
        if p.startswith("venom_core/")
        or (p.startswith("tests/test_") and p.endswith(".py"))
    ]
    if not relevant_changes:
        print("No staged backend/test changes detected; skip Sonar group update.")
        return 0

    resolver = _load_resolver_module()
    all_tests = resolver._all_test_files()
    changed_tests = resolver._collect_changed_tests(staged)
    related_tests = resolver._related_tests_for_modules(staged, all_tests)

    candidates = sorted(changed_tests | related_tests)
    candidates = [test for test in candidates if resolver._is_light_test(test)]

    existing = set(_read_group_items(GROUP_PATH))
    to_add = [test for test in candidates if test not in existing]

    if not to_add:
        print("Sonar new-code group already up to date for staged changes.")
        return 0

    _append_auto_items(GROUP_PATH, to_add)
    print(f"Added {len(to_add)} test(s) to {GROUP_PATH}:")
    for item in to_add:
        print(f"  - {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
