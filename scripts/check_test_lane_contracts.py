#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Violation:
    scope: str
    item: str
    message: str


@dataclass(frozen=True)
class Override:
    group: str | None
    test: str
    lane: str
    rationale: str


def _load_json_like(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _read_group_tests(path: Path) -> list[str]:
    tests: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tests.append(line)
    return tests


def _load_overrides(path: Path | None) -> tuple[list[Override], list[Violation]]:
    if path is None:
        return [], []
    payload = _load_json_like(path)
    raw_overrides = payload.get("overrides", [])
    if not isinstance(raw_overrides, list):
        return [], [Violation("contracts", str(path), "'overrides' must be a list.")]

    overrides: list[Override] = []
    violations: list[Violation] = []
    seen_keys: set[tuple[str | None, str]] = set()
    for idx, item in enumerate(raw_overrides):
        if not isinstance(item, dict):
            violations.append(
                Violation(
                    "override",
                    str(idx),
                    "Override entry must be an object.",
                )
            )
            continue
        group_raw = item.get("group")
        group = str(group_raw).strip() if group_raw is not None else None
        if group == "":
            group = None
        test = str(item.get("test", "")).strip()
        lane = str(item.get("lane", "")).strip()
        rationale = str(item.get("rationale", "")).strip()

        key = (group, test)
        if key in seen_keys:
            violations.append(
                Violation(
                    "override", f"{group or '*'}::{test}", "Duplicate override entry."
                )
            )
            continue
        seen_keys.add(key)
        overrides.append(
            Override(group=group, test=test, lane=lane, rationale=rationale)
        )
    return overrides, violations


def _resolve_override(
    overrides: list[Override], group_id: str, test_path: str
) -> Override | None:
    specific = [o for o in overrides if o.group == group_id and o.test == test_path]
    if len(specific) > 1:
        raise ValueError(f"Multiple overrides for {group_id}:{test_path}")
    if len(specific) == 1:
        return specific[0]
    generic = [o for o in overrides if o.group is None and o.test == test_path]
    if len(generic) > 1:
        raise ValueError(f"Multiple wildcard overrides for {test_path}")
    if len(generic) == 1:
        return generic[0]
    return None


def evaluate(
    *,
    contracts: dict[str, Any],
    overrides: list[Override],
    repo_root: Path,
) -> tuple[list[Violation], dict[str, Any]]:
    violations: list[Violation] = []
    groups = contracts.get("groups", [])
    lanes = contracts.get("lanes", [])
    if not isinstance(groups, list) or not isinstance(lanes, list):
        return (
            [
                Violation(
                    "contracts",
                    "root",
                    "Contracts must define list fields: 'lanes' and 'groups'.",
                )
            ],
            {},
        )

    lane_ids: set[str] = set()
    for lane in lanes:
        if not isinstance(lane, dict):
            violations.append(
                Violation("lane", "<invalid>", "Lane entry must be an object.")
            )
            continue
        lane_id = str(lane.get("id", "")).strip()
        if not lane_id:
            violations.append(Violation("lane", "<missing-id>", "Lane id is required."))
            continue
        if lane_id in lane_ids:
            violations.append(Violation("lane", lane_id, "Duplicate lane id."))
            continue
        lane_ids.add(lane_id)

    group_ids: set[str] = set()
    tests_seen_in_groups: set[tuple[str, str]] = set()
    summary: dict[str, Any] = {"groups": {}, "total_tests": 0}

    for group in groups:
        if not isinstance(group, dict):
            violations.append(
                Violation("group", "<invalid>", "Group entry must be an object.")
            )
            continue
        group_id = str(group.get("id", "")).strip()
        if not group_id:
            violations.append(
                Violation("group", "<missing-id>", "Group id is required.")
            )
            continue
        if group_id in group_ids:
            violations.append(Violation("group", group_id, "Duplicate group id."))
            continue
        group_ids.add(group_id)

        group_file = str(group.get("group_file", "")).strip()
        default_lane = str(group.get("default_lane", "")).strip()
        allowed_lanes = group.get("allowed_lanes", [])
        default_rationale = str(group.get("default_rationale", "")).strip()

        if not group_file:
            violations.append(Violation("group", group_id, "group_file is required."))
            continue
        group_path = repo_root / group_file
        if not group_path.exists():
            violations.append(
                Violation("group", group_id, f"group_file not found: {group_file}")
            )
            continue
        if default_lane not in lane_ids:
            violations.append(
                Violation(
                    "group",
                    group_id,
                    f"default_lane '{default_lane}' not found in lane ids.",
                )
            )
        if not isinstance(allowed_lanes, list) or not allowed_lanes:
            violations.append(
                Violation("group", group_id, "allowed_lanes must be a non-empty list.")
            )
            allowed_lanes = []
        allowed_lane_ids = [str(x).strip() for x in allowed_lanes]
        for lane_id in allowed_lane_ids:
            if lane_id not in lane_ids:
                violations.append(
                    Violation(
                        "group",
                        group_id,
                        f"allowed lane '{lane_id}' is not declared in lanes section.",
                    )
                )
        if default_lane and default_lane not in allowed_lane_ids:
            violations.append(
                Violation(
                    "group",
                    group_id,
                    "default_lane must be included in allowed_lanes.",
                )
            )
        if not default_rationale:
            violations.append(
                Violation(
                    "group",
                    group_id,
                    "default_rationale cannot be empty.",
                )
            )

        tests = _read_group_tests(group_path)
        duplicates = len(tests) - len(set(tests))
        if duplicates:
            violations.append(
                Violation(
                    "group",
                    group_id,
                    f"group_file contains {duplicates} duplicate test entries.",
                )
            )
        group_count = 0
        for test_path in tests:
            tests_seen_in_groups.add((group_id, test_path))
            test_file = repo_root / test_path
            if not test_file.exists():
                violations.append(
                    Violation(
                        "test",
                        f"{group_id}:{test_path}",
                        "Test path listed in group does not exist.",
                    )
                )
                continue

            try:
                override = _resolve_override(overrides, group_id, test_path)
            except ValueError as err:
                violations.append(
                    Violation("override", f"{group_id}:{test_path}", str(err))
                )
                continue

            lane = override.lane if override is not None else default_lane
            rationale = (
                override.rationale if override is not None else default_rationale
            )
            if lane not in lane_ids:
                violations.append(
                    Violation(
                        "test",
                        f"{group_id}:{test_path}",
                        f"Assigned lane '{lane}' is not declared.",
                    )
                )
            if lane not in allowed_lane_ids:
                violations.append(
                    Violation(
                        "test",
                        f"{group_id}:{test_path}",
                        f"Assigned lane '{lane}' is not allowed for group '{group_id}'.",
                    )
                )
            if not rationale.strip():
                violations.append(
                    Violation(
                        "test",
                        f"{group_id}:{test_path}",
                        "Assignment rationale cannot be empty.",
                    )
                )
            group_count += 1

        summary["groups"][group_id] = {
            "group_file": group_file,
            "tests": group_count,
        }
        summary["total_tests"] += group_count

    for override in overrides:
        if override.group is not None and override.group not in group_ids:
            violations.append(
                Violation(
                    "override",
                    f"{override.group}:{override.test}",
                    "Override references unknown group.",
                )
            )
            continue
        if override.lane not in lane_ids:
            violations.append(
                Violation(
                    "override",
                    f"{override.group or '*'}:{override.test}",
                    f"Override lane '{override.lane}' is not declared.",
                )
            )
        if not override.rationale.strip():
            violations.append(
                Violation(
                    "override",
                    f"{override.group or '*'}:{override.test}",
                    "Override rationale cannot be empty.",
                )
            )

        candidates: list[tuple[str, str]] = []
        if override.group is None:
            candidates = [
                item for item in tests_seen_in_groups if item[1] == override.test
            ]
        else:
            pair = (override.group, override.test)
            if pair in tests_seen_in_groups:
                candidates = [pair]
        if not candidates:
            violations.append(
                Violation(
                    "override",
                    f"{override.group or '*'}:{override.test}",
                    "Override test is not present in target group file(s).",
                )
            )

    return violations, summary


def _print_text_report(violations: list[Violation], summary: dict[str, Any]) -> None:
    if not violations:
        total = int(summary.get("total_tests", 0))
        print(
            "✅ Test lane contracts check passed "
            f"({len(summary.get('groups', {}))} groups, {total} tests)."
        )
        return
    print("❌ Test lane contract violations detected:")
    for violation in violations:
        print(f"- [{violation.scope}] {violation.item}: {violation.message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate test lane contracts.")
    parser.add_argument(
        "--contracts",
        type=Path,
        default=Path("config/testing/lane_contracts.yaml"),
        help="Path to lane contracts file (JSON-compatible YAML).",
    )
    parser.add_argument(
        "--assignments",
        type=Path,
        default=Path("config/testing/lane_assignments.yaml"),
        help="Path to explicit lane assignments/overrides file.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Report output format.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contracts = _load_json_like(args.contracts)
    overrides, override_parse_issues = _load_overrides(args.assignments)
    violations, summary = evaluate(
        contracts=contracts,
        overrides=overrides,
        repo_root=args.repo_root,
    )
    all_violations = [*override_parse_issues, *violations]
    if args.output == "json":
        print(
            json.dumps(
                {
                    "summary": summary,
                    "violations": [
                        {
                            "scope": v.scope,
                            "item": v.item,
                            "message": v.message,
                        }
                        for v in all_violations
                    ],
                },
                ensure_ascii=True,
                indent=2,
            )
        )
    else:
        _print_text_report(all_violations, summary)
    return 1 if all_violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
