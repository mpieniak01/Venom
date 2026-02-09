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


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _append_auto_items(path: Path, new_items: list[str]) -> None:
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = content.splitlines()

    header_idx = next(
        (idx for idx, line in enumerate(lines) if line.strip() == AUTO_SECTION_HEADER),
        None,
    )
    if header_idx is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(AUTO_SECTION_HEADER)
        lines.extend(new_items)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    insert_idx = header_idx + 1
    while insert_idx < len(lines):
        stripped = lines[insert_idx].strip()
        if stripped.startswith("#"):
            break
        insert_idx += 1

    lines[insert_idx:insert_idx] = new_items
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    staged = _git_staged_files()
    relevant_changes = [
        p
        for p in staged
        if p.startswith("venom_core/")
        or (
            p.startswith("tests/")
            and p.endswith(".py")
            and Path(p).name.startswith("test_")
        )
    ]
    if not relevant_changes:
        print("No staged backend/test changes detected; skip Sonar group update.")
        return 0

    resolver = _load_resolver_module()
    resolver_fn = getattr(resolver, "resolve_candidates_from_changed_files", None)
    if callable(resolver_fn):
        candidates = resolver_fn(relevant_changes)
    else:
        all_tests_fn = getattr(resolver, "all_test_files", None) or getattr(
            resolver, "_all_test_files", None
        )
        changed_fn = getattr(resolver, "collect_changed_tests", None) or getattr(
            resolver, "_collect_changed_tests", None
        )
        related_fn = getattr(resolver, "related_tests_for_modules", None) or getattr(
            resolver, "_related_tests_for_modules", None
        )
        light_fn = getattr(resolver, "is_light_test", None) or getattr(
            resolver, "_is_light_test", None
        )
        if not all(
            callable(fn) for fn in (all_tests_fn, changed_fn, related_fn, light_fn)
        ):
            raise RuntimeError("Resolver module does not expose required API.")
        all_tests = all_tests_fn()
        changed_tests = changed_fn(relevant_changes)
        related_tests = related_fn(relevant_changes, all_tests)
        candidates = sorted(changed_tests | related_tests)
        candidates = [test for test in candidates if light_fn(test)]
    candidates = _dedupe_keep_order(candidates)

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
