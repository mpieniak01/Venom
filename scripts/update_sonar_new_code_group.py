#!/usr/bin/env python3
"""Auto-update Sonar new-code pytest group from staged backend/test changes."""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

GROUP_PATH = Path("config/pytest-groups/sonar-new-code.txt")
AUTO_SECTION_HEADER = "# AUTO-ADDED by pre-commit (staged backend/test changes)"
SLEEP_RE = re.compile(r"(?:time|asyncio)\.sleep\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)")


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


def _split_auto_section(lines: list[str]) -> tuple[list[str], list[str]]:
    header_idx = next(
        (idx for idx, line in enumerate(lines) if line.strip() == AUTO_SECTION_HEADER),
        None,
    )
    if header_idx is None:
        return lines[:], []

    head = lines[: header_idx + 1]
    auto_entries: list[str] = []
    idx = header_idx + 1
    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped.startswith("#"):
            break
        if stripped:
            auto_entries.append(stripped)
        idx += 1
    tail = lines[idx:]
    return head + tail, auto_entries


def _render_group(manual_lines: list[str], auto_entries: list[str]) -> str:
    out = manual_lines[:]
    if auto_entries:
        if not any(line.strip() == AUTO_SECTION_HEADER for line in out):
            if out and out[-1].strip():
                out.append("")
            out.append(AUTO_SECTION_HEADER)
        header_idx = next(
            idx for idx, line in enumerate(out) if line.strip() == AUTO_SECTION_HEADER
        )
        insert_idx = header_idx + 1
        while insert_idx < len(out) and not out[insert_idx].strip().startswith("#"):
            insert_idx += 1
        out = out[: header_idx + 1] + auto_entries + out[insert_idx:]
    return "\n".join(out).rstrip() + "\n"


def _append_auto_items(path: Path, new_items: list[str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    manual_lines, auto_entries = _split_auto_section(lines)
    merged = _dedupe_keep_order(auto_entries + new_items)
    path.write_text(_render_group(manual_lines, merged), encoding="utf-8")


def _sleep_total_seconds(path: str) -> float:
    file_path = Path(path)
    if not file_path.exists():
        return 0.0
    total = 0.0
    for value in SLEEP_RE.findall(file_path.read_text(encoding="utf-8")):
        try:
            total += float(value)
        except ValueError:
            continue
    return total


def _is_fast_safe_candidate(path: str, resolver_module) -> bool:
    lower = path.lower()
    if any(
        token in lower
        for token in (
            "integration",
            "benchmark",
            "test_core_nervous_system.py",
            "test_evolution_coordinator_phase132d.py",
        )
    ):
        return False

    is_fast_safe_test = getattr(resolver_module, "is_fast_safe_test", None)
    if callable(is_fast_safe_test):
        if not is_fast_safe_test(path):
            return False
    elif not Path(path).exists():
        # Legacy resolver stubs don't expose fast-safe check; keep backward behavior.
        return True

    if _sleep_total_seconds(path) > 2.0:
        return False

    return True


def _apply_auto_cleanup(
    auto_entries: list[str],
    *,
    resolver_module,
    mode: str,
    max_auto_size: int,
) -> list[str]:
    existing_files = _dedupe_keep_order(auto_entries)

    if mode == "fast-safe":
        existing_files = [
            item
            for item in existing_files
            if _is_fast_safe_candidate(item, resolver_module)
        ]

    if max_auto_size > 0 and len(existing_files) > max_auto_size:
        existing_files = existing_files[-max_auto_size:]

    return existing_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update Sonar new-code test group with staged related tests."
    )
    parser.add_argument(
        "--mode",
        choices=("fast-safe", "strict-append"),
        default="fast-safe",
        help="Candidate filtering mode.",
    )
    parser.add_argument(
        "--prune-auto",
        action="store_true",
        help="Cleanup AUTO section before appending new candidates.",
    )
    parser.add_argument(
        "--max-auto-size",
        type=int,
        default=120,
        help="Maximum AUTO section size after cleanup (0 disables cap).",
    )
    args = parser.parse_args(argv)

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
    try:
        candidates = resolver.resolve_candidates_from_changed_files(
            relevant_changes,
            exclude_slow_fastlane=(args.mode == "fast-safe"),
        )
    except TypeError:
        # Backward-compat for resolver stubs/signatures used in tests/tools.
        candidates = resolver.resolve_candidates_from_changed_files(relevant_changes)
    candidates = _dedupe_keep_order(candidates)

    if args.mode == "fast-safe":
        candidates = [
            item for item in candidates if _is_fast_safe_candidate(item, resolver)
        ]

    file_lines = (
        GROUP_PATH.read_text(encoding="utf-8").splitlines()
        if GROUP_PATH.exists()
        else []
    )
    manual_lines, auto_entries = _split_auto_section(file_lines)

    if args.prune_auto:
        auto_entries = _apply_auto_cleanup(
            auto_entries,
            resolver_module=resolver,
            mode=args.mode,
            max_auto_size=args.max_auto_size,
        )

    existing = set(_read_group_items(GROUP_PATH))
    to_add = [test for test in candidates if test not in existing]

    merged_auto = auto_entries + to_add
    merged_auto = _apply_auto_cleanup(
        merged_auto,
        resolver_module=resolver,
        mode=args.mode,
        max_auto_size=args.max_auto_size,
    )

    GROUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    GROUP_PATH.write_text(_render_group(manual_lines, merged_auto), encoding="utf-8")

    if to_add:
        print(f"Added {len(to_add)} test(s) to {GROUP_PATH}:")
        for item in to_add:
            print(f"  - {item}")
    else:
        print("Sonar new-code group already up to date for staged changes.")

    if args.prune_auto:
        print(f"AUTO section size after cleanup: {len(merged_auto)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
