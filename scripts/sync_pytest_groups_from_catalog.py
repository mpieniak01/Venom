#!/usr/bin/env python3
"""Sync pytest group files from canonical test catalog."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEST_PATH_RE = re.compile(r"^tests(?:/[^/]+)*/test_.*\.py$")

GROUP_FILES = {
    "ci-lite": Path("config/pytest-groups/ci-lite.txt"),
    "sonar-new-code": Path("config/pytest-groups/sonar-new-code.txt"),
    "fast": Path("config/pytest-groups/fast.txt"),
    "long": Path("config/pytest-groups/long.txt"),
    "heavy": Path("config/pytest-groups/heavy.txt"),
}

HEADER_LINES = [
    "# AUTO-GENERATED from config/testing/test_catalog.json",
    "# Do not edit manually. Run: make test-groups-sync",
    "",
]


@dataclass(frozen=True)
class Violation:
    scope: str
    item: str
    message: str


def _load_catalog(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Catalog file must contain valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Catalog root must be a JSON object.")
    tests = payload.get("tests", [])
    if not isinstance(tests, list):
        raise ValueError("Catalog must define 'tests' as a list.")
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(tests):
        if not isinstance(item, dict):
            raise ValueError(f"Catalog entry {idx} must be an object.")
        out.append(item)
    return out


def _release_bucket(entry: dict[str, Any], path: str) -> str:
    test_type = str(entry.get("test_type", "")).strip()
    lower = path.lower()
    if test_type == "perf" or "/perf/" in lower:
        return "heavy"
    if test_type == "integration" or "integration" in lower:
        return "long"
    if test_type == "gate":
        return "long"
    return "fast"


def _render_group(paths: set[str]) -> str:
    lines = [*HEADER_LINES, *sorted(paths)]
    return "\n".join(lines).rstrip() + "\n"


def _validate_and_build_groups(
    *,
    entries: list[dict[str, Any]],
    repo_root: Path,
) -> tuple[dict[str, set[str]], list[Violation]]:
    groups = {key: set() for key in GROUP_FILES.keys()}
    violations: list[Violation] = []

    for idx, entry in enumerate(entries):
        path = str(entry.get("path", "")).strip()
        if not path:
            violations.append(Violation("catalog", str(idx), "Missing entry path."))
            continue
        if not TEST_PATH_RE.match(path):
            violations.append(
                Violation(
                    "path_pattern",
                    path,
                    "Catalog path must match tests/**/test_*.py pattern.",
                )
            )
            continue
        if not (repo_root / path).exists():
            violations.append(
                Violation(
                    "path_exists",
                    path,
                    "Catalog path does not exist in repository.",
                )
            )
            continue

        allowed = {str(x).strip() for x in entry.get("allowed_lanes", [])}
        primary_lane = str(entry.get("primary_lane", "")).strip()
        if primary_lane == "ci-lite":
            groups["ci-lite"].add(path)
        if "new-code" in allowed:
            groups["sonar-new-code"].add(path)
        if "release" in allowed:
            groups[_release_bucket(entry, path)].add(path)

    return groups, violations


def _sync_light_alias(repo_root: Path, *, check_only: bool) -> list[Violation]:
    alias_path = repo_root / "config/pytest-groups/light.txt"
    expected_target = "fast.txt"
    violations: list[Violation] = []

    if check_only:
        if not alias_path.is_symlink():
            violations.append(
                Violation(
                    "light_alias",
                    str(alias_path),
                    "light.txt must be a symlink to fast.txt.",
                )
            )
            return violations

        target = os.readlink(alias_path)
        if target != expected_target:
            violations.append(
                Violation(
                    "light_alias",
                    str(alias_path),
                    f"light.txt must point to {expected_target} (got: {target}).",
                )
            )
        return violations

    alias_path.parent.mkdir(parents=True, exist_ok=True)
    if alias_path.exists() or alias_path.is_symlink():
        alias_path.unlink()
    alias_path.symlink_to(expected_target)
    return violations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync pytest groups from catalog.")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("config/testing/test_catalog.json"),
        help="Path to canonical test catalog file.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    parser.add_argument(
        "--write",
        type=int,
        default=0,
        help="Write synchronized group files (1=true, 0=false).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if group files differ from generated content.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root
    catalog_path = (
        args.catalog if args.catalog.is_absolute() else repo_root / args.catalog
    )
    entries = _load_catalog(catalog_path)
    groups, violations = _validate_and_build_groups(
        entries=entries, repo_root=repo_root
    )

    expected_contents = {key: _render_group(paths) for key, paths in groups.items()}

    if args.check:
        for key, rel_path in GROUP_FILES.items():
            file_path = repo_root / rel_path
            current = (
                file_path.read_text(encoding="utf-8") if file_path.exists() else ""
            )
            if current != expected_contents[key]:
                violations.append(
                    Violation(
                        "group_sync",
                        str(rel_path),
                        "Group file differs from catalog-generated content.",
                    )
                )
        violations.extend(_sync_light_alias(repo_root, check_only=True))
        if violations:
            print("❌ Pytest group sync check failed:")
            for violation in violations:
                print(f"- [{violation.scope}] {violation.item}: {violation.message}")
            return 1
        print("✅ Pytest groups are synchronized with test catalog.")
        return 0

    if args.write:
        for key, rel_path in GROUP_FILES.items():
            file_path = repo_root / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(expected_contents[key], encoding="utf-8")
        violations.extend(_sync_light_alias(repo_root, check_only=False))

    if violations:
        print("❌ Pytest group sync failed:")
        for violation in violations:
            print(f"- [{violation.scope}] {violation.item}: {violation.message}")
        return 1

    if args.write:
        summary = ", ".join(
            f"{key}={len(groups[key])}"
            for key in ("ci-lite", "sonar-new-code", "fast", "long", "heavy")
        )
        print(f"✅ Pytest groups synchronized from catalog ({summary}).")
        return 0

    print("ℹ️ No action performed (use --write 1 or --check).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
