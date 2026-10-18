#!/usr/bin/env python3
"""Guard for Node runtime compatibility of GitHub Actions workflows."""

from __future__ import annotations

import argparse
import json
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


def validate_project_runtime(root: Path, workflow_dir: Path | None = None) -> list[str]:
    """One Node pin for native bootstrap, npm, Docker and workflow consumers."""
    try:
        version = (root / "web-next/.nvmrc").read_text().strip()
        package = json.loads((root / "web-next/package.json").read_text())
        lock = json.loads((root / "web-next/package-lock.json").read_text())
        docker = (root / "docker/frontend.Dockerfile").read_text()
    except (OSError, ValueError) as exc:
        return [f"Node runtime contract cannot be read: {type(exc).__name__}"]
    issues = []
    if not re.fullmatch(r"24\.\d+\.\d+", version):
        issues.append("web-next/.nvmrc must pin a qualified Node 24 patch release")
    engines = package.get("engines", {})
    if engines.get("node") != f">={version} <25":
        issues.append("package.json Node engine differs from .nvmrc")
    manager = package.get("packageManager", "")
    if not re.fullmatch(r"npm@11\.\d+\.\d+", manager):
        issues.append("packageManager must pin npm 11")
    elif engines.get("npm") != f">={manager.removeprefix('npm@')} <12":
        issues.append("npm engine differs from packageManager")
    if lock.get("packages", {}).get("", {}).get("engines") != engines:
        issues.append("package-lock root engines differ from package.json")
    image = rf"node:{re.escape(version)}-alpine@sha256:[a-f0-9]{{64}}"
    if not re.search(rf"^ARG NODE_IMAGE={image}$", docker, re.MULTILINE):
        issues.append("frontend Docker image must pin the same Node patch and digest")
    for path in collect_workflows(
        workflow_dir if workflow_dir is not None else root / ".github/workflows"
    ):
        content = path.read_text()
        if "uses: actions/setup-node@" not in content:
            continue
        if (
            re.search(r"node-version\s*:", content)
            or 'node-version-file: "web-next/.nvmrc"' not in content
        ):
            issues.append(f"{path.name}: setup-node must consume web-next/.nvmrc")
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
    issues.extend(validate_project_runtime(Path("."), args.workflow_dir))
    if issues:
        print("❌ GitHub Actions Node runtime guard failed:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("✅ GitHub Actions Node runtime guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
