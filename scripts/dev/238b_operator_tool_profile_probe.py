#!/usr/bin/env python3
"""PR238B probe for the operator tool profile contract."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = (
    REPO_ROOT / "config" / "chat_operator" / "venom_operator_tool_profile.json"
)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_profile(profile: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    issues: list[str] = []
    advisories: list[str] = []

    schema_version = profile.get("schema_version")
    if not isinstance(schema_version, int) or schema_version < 1:
        issues.append("schema_version_invalid")

    profile_name = profile.get("profile_name")
    if not _non_empty_str(profile_name):
        issues.append("profile_name_missing_or_empty")

    decision_policy = profile.get("decision_policy")
    if not _non_empty_str(decision_policy):
        issues.append("decision_policy_missing_or_empty")

    core_tools = profile.get("core_tools")
    if not isinstance(core_tools, list) or not core_tools:
        issues.append("core_tools_missing_or_empty")
        core_tools = []
    elif not all(_non_empty_str(item) for item in core_tools):
        issues.append("core_tools_invalid_entries")

    extended_tools = profile.get("extended_tools")
    if not isinstance(extended_tools, list) or not extended_tools:
        issues.append("extended_tools_missing_or_empty")
        extended_tools = []
    elif not all(_non_empty_str(item) for item in extended_tools):
        issues.append("extended_tools_invalid_entries")

    default_repo_probes = profile.get("default_repo_probes")
    if not isinstance(default_repo_probes, dict):
        issues.append("default_repo_probes_missing_or_invalid")
        default_repo_probes = {}
    else:
        for key in ("repo_probe", "workspace_probe", "task_probe"):
            value = default_repo_probes.get(key)
            if not isinstance(value, list) or not value:
                issues.append(f"default_repo_probes.{key}_missing_or_empty")
            elif not all(_non_empty_str(item) for item in value):
                issues.append(f"default_repo_probes.{key}_invalid_entries")

    expected_core = {
        "exec_command",
        "write_stdin",
        "update_plan",
        "apply_patch",
        "view_image",
    }
    missing_core = sorted(
        expected_core
        - {str(item).strip() for item in core_tools if _non_empty_str(item)}
    )
    if missing_core:
        issues.append("missing_expected_core_tools:" + ",".join(missing_core))

    repo_probe_items = {
        str(item).strip()
        for item in default_repo_probes.get("repo_probe", [])
        if _non_empty_str(item)
    }
    workspace_probe_items = {
        str(item).strip()
        for item in default_repo_probes.get("workspace_probe", [])
        if _non_empty_str(item)
    }
    if {
        "git status -sb",
        "git diff --shortstat",
        "git branch --show-current",
    } - repo_probe_items:
        advisories.append("repo_probe_should_include_git_status_diff_branch")
    if {"pwd", "source .venv/bin/activate"} - workspace_probe_items:
        advisories.append("workspace_probe_should_include_pwd_and_venv_activation")

    verdict = "pass" if not issues else "fail"
    return verdict, issues, advisories


def main() -> int:
    parser = argparse.ArgumentParser(description="PR238B operator tool profile probe")
    parser.add_argument(
        "--profile-file",
        default=str(DEFAULT_PROFILE.relative_to(REPO_ROOT)),
    )
    parser.add_argument(
        "--json-output",
        default="test-results/238b/operator_tool_profile_probe.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/238b/operator_tool_profile_probe.md",
    )
    args = parser.parse_args()

    profile_path = (REPO_ROOT / args.profile_file).resolve()
    profile = _load_json(profile_path)
    issues: list[str] = []
    advisories: list[str] = []

    if profile is None:
        issues.append("profile_missing_or_invalid")
        verdict = "fail"
    else:
        verdict, profile_issues, profile_advisories = _validate_profile(profile)
        issues.extend(profile_issues)
        advisories.extend(profile_advisories)

    report = {
        "scope": "pr238b-operator-tool-profile-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "profile_path": str(profile_path),
        "verdict": verdict,
        "issues": issues,
        "advisories": advisories,
        "profile": profile,
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR238B Operator Tool Profile Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Profile: `{profile_path}`",
        f"Verdict: `{verdict}`",
        "",
        "## Issues",
    ]
    if issues:
        md_lines.extend(f"- `{item}`" for item in issues)
    else:
        md_lines.append("- `<none>`")
    md_lines.extend(["", "## Advisories"])
    if advisories:
        md_lines.extend(f"- `{item}`" for item in advisories)
    else:
        md_lines.append("- `<none>`")
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
