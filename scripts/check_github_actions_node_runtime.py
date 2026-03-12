#!/usr/bin/env python3
"""Guard for Node runtime compatibility of GitHub Actions workflows."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

RULES: dict[str, int] = {
    "actions/upload-artifact": 6,
    "actions/download-artifact": 7,
    "actions/cache": 5,
}
FORCE_NODE24_ENV = "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24"


def _iter_action_versions(content: str, action: str):
    pattern = re.compile(rf"uses:\s*{re.escape(action)}@v(?P<major>\d+)")
    for match in pattern.finditer(content):
        major = int(match.group("major"))
        line = content.count("\n", 0, match.start()) + 1
        yield line, major


def validate_workflow(path: Path, content: str) -> list[str]:
    issues: list[str] = []
    contains_artifact_action = False

    for action, min_major in RULES.items():
        for line, major in _iter_action_versions(content, action):
            contains_artifact_action = True
            if major < min_major:
                issues.append(
                    f"{path}:{line}: {action}@v{major} is deprecated for Node 24. "
                    f"Use @{min_major} or newer."
                )

    if contains_artifact_action and FORCE_NODE24_ENV not in content:
        issues.append(
            f"{path}: missing `{FORCE_NODE24_ENV}` env hardening for JS actions runtime."
        )

    return issues


def collect_workflows(workflow_dir: Path) -> list[Path]:
    return sorted(list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml")))


def run_check(workflow_dir: Path) -> list[str]:
    issues: list[str] = []
    for workflow_path in collect_workflows(workflow_dir):
        content = workflow_path.read_text(encoding="utf-8")
        issues.extend(validate_workflow(workflow_path, content))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate GitHub Actions workflows for Node runtime deprecations."
    )
    parser.add_argument(
        "--workflow-dir",
        type=Path,
        default=Path(".github/workflows"),
        help="Directory with workflow YAML files.",
    )
    args = parser.parse_args()

    issues = run_check(args.workflow_dir)
    if issues:
        print("❌ GitHub Actions Node runtime guard failed:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("✅ GitHub Actions Node runtime guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
