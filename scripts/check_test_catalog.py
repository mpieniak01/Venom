#!/usr/bin/env python3
"""Validate canonical test catalog against repository and lane groups."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Violation:
    scope: str
    item: str
    message: str


TEST_PATH_RE = re.compile(r"^tests(?:/[^/]+)*/test_.*\.py$")


def _load_json_like(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain JSON object.")
    return payload


def _read_group(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line)
    return out


def _repo_tests(repo_root: Path) -> set[str]:
    return {
        str(path.relative_to(repo_root)).replace("\\", "/")
        for path in (repo_root / "tests").rglob("test_*.py")
        if path.is_file()
    }


def _resolve_diff_base(repo_root: Path, preferred: str) -> str | None:
    candidates = [preferred, "origin/main", "main", "HEAD~1"]
    seen: set[str] = set()
    for ref in candidates:
        ref = ref.strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return ref
    return None


def _changed_tests(repo_root: Path, diff_base: str) -> set[str]:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{diff_base}...HEAD",
            "--",
            "tests/**/test_*.py",
            "tests/test_*.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return set()
    out: set[str] = set()
    for raw in proc.stdout.splitlines():
        path = raw.strip().replace("\\", "/")
        if path and TEST_PATH_RE.match(path):
            out.add(path)
    return out


def _catalog_entries(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Violation]]:
    raw = payload.get("tests")
    if not isinstance(raw, list):
        return [], [Violation("catalog", "tests", "'tests' must be a list.")]
    out: list[dict[str, Any]] = []
    violations: list[Violation] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            violations.append(
                Violation("entry", str(idx), "Catalog entry must be an object.")
            )
            continue
        out.append(item)
    return out, violations


def evaluate(
    *,
    repo_root: Path,
    catalog_path: Path,
    ci_lite_group: Path,
    sonar_new_code_group: Path,
    fast_group: Path,
    long_group: Path,
    heavy_group: Path,
    enforce_changed_test_new_code: bool = False,
    diff_base: str = "origin/main",
) -> tuple[list[Violation], dict[str, Any]]:
    payload = _load_json_like(catalog_path)
    entries, violations = _catalog_entries(payload)

    allowed_domains = set(payload.get("allowed_domains", []))
    allowed_types = set(payload.get("allowed_test_types", []))
    allowed_intents = set(payload.get("allowed_intents", []))
    legacy_targeted_fastlane_max = int(
        payload.get("meta", {}).get("legacy_targeted_fastlane_max", 17)
    )

    required_fields = {
        "path",
        "domain",
        "test_type",
        "intent",
        "primary_lane",
        "allowed_lanes",
        "legacy_targeted",
        "rationale",
    }
    valid_lanes = {"ci-lite", "new-code", "release", "pr-fast"}

    by_path: dict[str, dict[str, Any]] = {}
    for idx, entry in enumerate(entries):
        missing = sorted(required_fields - set(entry.keys()))
        if missing:
            violations.append(
                Violation("entry", str(idx), f"Missing fields: {', '.join(missing)}")
            )
            continue

        path = str(entry.get("path", "")).strip()
        if not path:
            violations.append(Violation("entry", str(idx), "Empty 'path'."))
            continue
        if path in by_path:
            violations.append(Violation("entry", path, "Duplicate path in catalog."))
            continue

        domain = str(entry.get("domain", "")).strip()
        if domain not in allowed_domains:
            violations.append(Violation("entry", path, f"Unknown domain '{domain}'."))

        test_type = str(entry.get("test_type", "")).strip()
        if test_type not in allowed_types:
            violations.append(
                Violation("entry", path, f"Unknown test_type '{test_type}'.")
            )

        intent = str(entry.get("intent", "")).strip()
        if intent not in allowed_intents:
            violations.append(Violation("entry", path, f"Unknown intent '{intent}'."))

        primary_lane = str(entry.get("primary_lane", "")).strip()
        if primary_lane not in valid_lanes:
            violations.append(
                Violation("entry", path, f"Unknown primary_lane '{primary_lane}'.")
            )

        allowed_lanes = entry.get("allowed_lanes", [])
        if not isinstance(allowed_lanes, list) or not allowed_lanes:
            violations.append(
                Violation("entry", path, "'allowed_lanes' must be non-empty list.")
            )
        else:
            for lane in allowed_lanes:
                if str(lane).strip() not in valid_lanes:
                    violations.append(
                        Violation(
                            "entry",
                            path,
                            f"Unknown lane in allowed_lanes: '{lane}'.",
                        )
                    )
            if primary_lane and primary_lane not in {str(x) for x in allowed_lanes}:
                violations.append(
                    Violation(
                        "entry",
                        path,
                        "primary_lane must be included in allowed_lanes.",
                    )
                )

        legacy_targeted = entry.get("legacy_targeted")
        if not isinstance(legacy_targeted, bool):
            violations.append(
                Violation("entry", path, "'legacy_targeted' must be boolean.")
            )

        rationale = str(entry.get("rationale", "")).strip()
        if not rationale:
            violations.append(Violation("entry", path, "Empty rationale."))

        by_path[path] = entry

    repo_tests = _repo_tests(repo_root)
    catalog_tests = set(by_path.keys())
    missing_in_catalog = sorted(repo_tests - catalog_tests)
    stale_in_catalog = sorted(catalog_tests - repo_tests)

    for path in missing_in_catalog:
        violations.append(
            Violation("coverage", path, "Repository test is missing in catalog.")
        )
    for path in stale_in_catalog:
        violations.append(
            Violation("coverage", path, "Catalog contains non-existing test path.")
        )

    ci_lite = _read_group(ci_lite_group)
    sonar_new_code = _read_group(sonar_new_code_group)
    fast_lane_union = ci_lite | sonar_new_code

    release_fast = _read_group(fast_group)
    release_long = _read_group(long_group)
    release_heavy = _read_group(heavy_group)
    release_lane_union = release_fast | release_long | release_heavy

    missing_lane_catalog_entries = sorted(
        [path for path in fast_lane_union if path not in by_path]
    )
    for path in missing_lane_catalog_entries:
        violations.append(
            Violation("lane", path, "Fast-lane test path is missing in catalog.")
        )

    release_expected = sorted(
        [
            path
            for path, entry in by_path.items()
            if "release" in entry.get("allowed_lanes", [])
        ]
    )
    missing_release_group_entries = sorted(
        [path for path in release_expected if path not in release_lane_union]
    )
    for path in missing_release_group_entries:
        violations.append(
            Violation(
                "release_lane",
                path,
                "Catalog allows 'release' lane but test is missing from fast/long/heavy groups.",
            )
        )

    for path in sorted(release_lane_union):
        if not TEST_PATH_RE.match(path):
            violations.append(
                Violation(
                    "release_lane",
                    path,
                    "Release lane group contains path outside tests/**/test_*.py pattern.",
                )
            )

        entry = by_path.get(path)
        if entry is None:
            violations.append(
                Violation(
                    "release_lane",
                    path,
                    "Release lane test path is missing in catalog.",
                )
            )
            continue

        allowed_lanes = {str(x) for x in entry.get("allowed_lanes", [])}
        if "release" not in allowed_lanes:
            violations.append(
                Violation(
                    "release_lane",
                    path,
                    "Listed in fast/long/heavy groups but catalog disallows 'release' lane.",
                )
            )

    legacy_fast_count = 0
    for path in sorted(fast_lane_union):
        entry = by_path.get(path)
        if entry is None:
            continue

        allowed_lanes = {str(x) for x in entry.get("allowed_lanes", [])}
        if path in ci_lite and "ci-lite" not in allowed_lanes:
            violations.append(
                Violation(
                    "lane",
                    path,
                    "Listed in ci-lite group but catalog disallows 'ci-lite' lane.",
                )
            )
        if path in sonar_new_code and "new-code" not in allowed_lanes:
            violations.append(
                Violation(
                    "lane",
                    path,
                    "Listed in sonar-new-code group but catalog disallows 'new-code' lane.",
                )
            )

        legacy = bool(entry.get("legacy_targeted", False))
        if legacy:
            legacy_fast_count += 1
            domain = str(entry.get("domain", ""))
            if domain in {"misc", ""}:
                violations.append(
                    Violation(
                        "legacy_targeted",
                        path,
                        "Legacy-targeted fast-lane test must be assigned to concrete domain "
                        "(split by domain instead of generic PR-gate/IPT bucket).",
                    )
                )

    if legacy_fast_count > legacy_targeted_fastlane_max:
        violations.append(
            Violation(
                "legacy_targeted",
                "fast-lane-limit",
                f"legacy_targeted in fast lanes={legacy_fast_count} exceeds "
                f"limit={legacy_targeted_fastlane_max}.",
            )
        )

    summary = {
        "tests_repo": len(repo_tests),
        "tests_catalog": len(catalog_tests),
        "tests_ci_lite": len(ci_lite),
        "tests_sonar_new_code": len(sonar_new_code),
        "tests_release_groups": len(release_lane_union),
        "tests_release_catalog": len(release_expected),
        "legacy_targeted_fast_lane": legacy_fast_count,
        "legacy_targeted_fast_lane_max": legacy_targeted_fastlane_max,
    }

    if enforce_changed_test_new_code:
        resolved_base = _resolve_diff_base(repo_root, diff_base)
        if not resolved_base:
            violations.append(
                Violation(
                    "local_new_code_gate",
                    diff_base,
                    "Cannot resolve diff base for changed-test new-code gate.",
                )
            )
        else:
            changed_tests = _changed_tests(repo_root, resolved_base)
            summary["changed_tests"] = len(changed_tests)
            summary["changed_tests_diff_base"] = resolved_base
            for path in sorted(changed_tests):
                entry = by_path.get(path)
                if not entry:
                    continue
                test_type = str(entry.get("test_type", "")).strip()
                if test_type in {"integration", "perf"}:
                    continue
                allowed_lanes = {str(x).strip() for x in entry.get("allowed_lanes", [])}
                if "new-code" not in allowed_lanes and "ci-lite" not in allowed_lanes:
                    violations.append(
                        Violation(
                            "local_new_code_gate",
                            path,
                            "Changed test must allow 'new-code' (or 'ci-lite') lane; "
                            "release-only is blocked in local gate.",
                        )
                    )
    return violations, summary


def _print_text(violations: list[Violation], summary: dict[str, Any]) -> None:
    if not violations:
        print(
            "✅ Test catalog check passed "
            f"(repo={summary['tests_repo']}, catalog={summary['tests_catalog']}, "
            f"legacy_fast={summary['legacy_targeted_fast_lane']}/"
            f"{summary['legacy_targeted_fast_lane_max']})."
        )
        return

    print("❌ Test catalog violations detected:")
    for v in violations:
        print(f"- [{v.scope}] {v.item}: {v.message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate test catalog consistency.")
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
        "--ci-lite-group",
        type=Path,
        default=Path("config/pytest-groups/ci-lite.txt"),
        help="Path to ci-lite group file.",
    )
    parser.add_argument(
        "--new-code-group",
        type=Path,
        default=Path("config/pytest-groups/sonar-new-code.txt"),
        help="Path to sonar-new-code group file.",
    )
    parser.add_argument(
        "--fast-group",
        type=Path,
        default=Path("config/pytest-groups/fast.txt"),
        help="Path to release fast group file.",
    )
    parser.add_argument(
        "--long-group",
        type=Path,
        default=Path("config/pytest-groups/long.txt"),
        help="Path to release long group file.",
    )
    parser.add_argument(
        "--heavy-group",
        type=Path,
        default=Path("config/pytest-groups/heavy.txt"),
        help="Path to release heavy group file.",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--enforce-changed-test-new-code",
        type=int,
        default=0,
        help="Enable local gate enforcing new-code lane on changed tests.",
    )
    parser.add_argument(
        "--diff-base",
        default="origin/main",
        help="Git base ref for changed-tests detection.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root
    ci_lite_group = (
        args.ci_lite_group
        if args.ci_lite_group.is_absolute()
        else repo_root / args.ci_lite_group
    )
    new_code_group = (
        args.new_code_group
        if args.new_code_group.is_absolute()
        else repo_root / args.new_code_group
    )
    fast_group = (
        args.fast_group
        if args.fast_group.is_absolute()
        else repo_root / args.fast_group
    )
    long_group = (
        args.long_group
        if args.long_group.is_absolute()
        else repo_root / args.long_group
    )
    heavy_group = (
        args.heavy_group
        if args.heavy_group.is_absolute()
        else repo_root / args.heavy_group
    )
    catalog_path = (
        args.catalog if args.catalog.is_absolute() else repo_root / args.catalog
    )

    violations, summary = evaluate(
        repo_root=repo_root,
        catalog_path=catalog_path,
        ci_lite_group=ci_lite_group,
        sonar_new_code_group=new_code_group,
        fast_group=fast_group,
        long_group=long_group,
        heavy_group=heavy_group,
        enforce_changed_test_new_code=bool(args.enforce_changed_test_new_code),
        diff_base=args.diff_base,
    )

    if args.output == "json":
        print(
            json.dumps(
                {
                    "summary": summary,
                    "violations": [
                        {"scope": v.scope, "item": v.item, "message": v.message}
                        for v in violations
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_text(violations, summary)

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
