#!/usr/bin/env python3
"""PR238G probe: validate canonical agent state registry and live workspace snapshot."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _run(cmd: list[str], timeout: float = 30.0) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "").strip()
    return True, (proc.stdout or "").strip()


def _registry_paths(registry: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for group in registry.get("state_groups", {}).values():
        if not isinstance(group, list):
            continue
        for entry in group:
            if not isinstance(entry, dict):
                continue
            source = entry.get("authoritative_source")
            if (
                isinstance(source, str)
                and source
                and source != "terminal"
                and "*" not in source
                and source.startswith(
                    (
                        "config/",
                        "docs/",
                        ".github/",
                        "make/",
                        "scripts/",
                        "test-results/",
                    )
                )
            ):
                paths.append(source)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="PR238G agent state registry probe")
    parser.add_argument(
        "--registry",
        default="config/chat_operator/agent_state_registry.json",
    )
    parser.add_argument(
        "--json-output", default="test-results/238g/agent_state_registry_probe.json"
    )
    parser.add_argument(
        "--md-output", default="test-results/238g/agent_state_registry_probe.md"
    )
    args = parser.parse_args()

    registry_path = REPO_ROOT / args.registry
    registry = _read_json(registry_path)
    issues: list[str] = []
    advisories: list[str] = []

    if registry is None:
        issues.append("registry_missing_or_invalid")
        registry = {}

    schema_version = registry.get("schema_version")
    if not isinstance(schema_version, int) or schema_version != 1:
        issues.append("registry_schema_version_invalid")

    state_groups = registry.get("state_groups")
    if not isinstance(state_groups, dict):
        issues.append("registry_state_groups_missing")
        state_groups = {}
    for required_group in ("local", "remote", "hybrid"):
        if required_group not in state_groups:
            issues.append(f"registry_group_missing:{required_group}")

    source_paths = _registry_paths(registry)
    missing_sources = [
        source for source in source_paths if not (REPO_ROOT / source).exists()
    ]
    if missing_sources:
        issues.append("missing_registry_sources:" + ",".join(missing_sources))

    branch_ok, branch = _run(["git", "branch", "--show-current"])
    status_ok, status_short_branch = _run(["git", "status", "--short", "--branch"])
    diff_ok, diff_shortstat = _run(["git", "diff", "--shortstat"])
    head_ok, head = _run(["git", "rev-parse", "--short", "HEAD"])
    if not branch_ok:
        issues.append("git_branch_failed")
    if not status_ok:
        issues.append("git_status_failed")
    if not diff_ok:
        issues.append("git_diff_failed")
    if not head_ok:
        issues.append("git_head_failed")

    workspace_contract = (
        _read_json(
            REPO_ROOT / "config/chat_operator/vscode_workspace_context_contract.json"
        )
        or {}
    )
    decision_contract = (
        _read_json(
            REPO_ROOT / "config/chat_operator/venom_agent_decision_contract.json"
        )
        or {}
    )
    routing_contract = (
        _read_json(REPO_ROOT / "config/chat_operator/decision_gate_contract.json") or {}
    )
    tool_profile = (
        _read_json(REPO_ROOT / "config/chat_operator/venom_operator_tool_profile.json")
        or {}
    )

    if workspace_contract.get("venom.workspaceIndexMode") != "local-first":
        issues.append("workspace_index_mode_mismatch")
    if workspace_contract.get("venom.workspaceContextDefault") != "#codebase":
        issues.append("workspace_context_default_mismatch")

    if decision_contract.get("decision_policy") != "tool-feedback-first":
        issues.append("decision_policy_mismatch")
    if decision_contract.get("repo_context_policy") != "index-first":
        issues.append("repo_context_policy_mismatch")
    if decision_contract.get("repo_truth_policy") != "terminal-preflight-required":
        issues.append("repo_truth_policy_mismatch")
    if decision_contract.get("required_response_fields") != [
        "repo_truth",
        "tools_used",
        "decision",
        "next_step",
    ]:
        issues.append("decision_response_fields_mismatch")

    if routing_contract.get("repo_truth_policy") != "tool-first-required":
        issues.append("routing_repo_truth_policy_mismatch")
    if routing_contract.get("operator_model_local_first") != "qwen2.5-coder:7b":
        advisories.append("routing_local_model_is_provisional")

    if tool_profile.get("decision_policy") != "tool-first-required":
        issues.append("tool_profile_decision_policy_mismatch")
    core_tools = (
        tool_profile.get("core_tools")
        if isinstance(tool_profile.get("core_tools"), list)
        else []
    )
    if not {"exec_command", "write_stdin", "apply_patch"}.issubset(
        {str(item) for item in core_tools}
    ):
        issues.append("tool_profile_core_tools_incomplete")

    docs_en = _read_text(REPO_ROOT / "docs/CHAT_OPERATOR.md")
    docs_pl = _read_text(REPO_ROOT / "docs/PL/CHAT_OPERATOR.md")
    if "local-first-agent-state-registry-probe" not in docs_en:
        advisories.append("docs_en_missing_state_registry_probe_reference")
    if "local-first-agent-state-registry-probe" not in docs_pl:
        advisories.append("docs_pl_missing_state_registry_probe_reference")

    runtime_mk = _read_text(REPO_ROOT / "make/runtime.mk")
    help_mk = _read_text(REPO_ROOT / "make/help.mk")
    if "local-first-agent-state-registry-probe" not in runtime_mk:
        issues.append("make_runtime_missing_state_registry_probe_target")
    if "local-first-agent-state-registry-probe" not in help_mk:
        issues.append("make_help_missing_state_registry_probe_entry")

    live_snapshot = {
        "repo_truth": {
            "branch": branch,
            "status_short_branch": status_short_branch,
            "diff_shortstat": diff_shortstat,
            "head": head,
        },
        "contracts": {
            "workspace_context": {
                "venom.workspaceIndexMode": workspace_contract.get(
                    "venom.workspaceIndexMode"
                ),
                "venom.workspaceContextDefault": workspace_contract.get(
                    "venom.workspaceContextDefault"
                ),
            },
            "decision_contract": {
                "decision_policy": decision_contract.get("decision_policy"),
                "repo_context_policy": decision_contract.get("repo_context_policy"),
                "repo_truth_policy": decision_contract.get("repo_truth_policy"),
            },
            "routing_contract": {
                "operator_model_local_first": routing_contract.get(
                    "operator_model_local_first"
                ),
                "utility_model": routing_contract.get("utility_model"),
                "repo_truth_policy": routing_contract.get("repo_truth_policy"),
            },
            "tool_profile": {
                "decision_policy": tool_profile.get("decision_policy"),
                "core_tools": tool_profile.get("core_tools"),
                "extended_tools": tool_profile.get("extended_tools"),
            },
        },
    }

    verdict = "pass" if not issues else "fail"
    report = {
        "scope": "pr238g-agent-state-registry-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "issues": issues,
        "advisories": advisories,
        "registry_path": str(registry_path.resolve()),
        "registry": registry,
        "live_snapshot": live_snapshot,
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR238G Agent State Registry Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "## Repo Truth",
        f"- branch: `{branch}`",
        f"- diff_shortstat: `{diff_shortstat}`",
        f"- head: `{head}`",
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
