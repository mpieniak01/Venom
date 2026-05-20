#!/usr/bin/env python3
"""PR237 probe: policy enforcement hook wiring for repo-truth workflow."""

from __future__ import annotations

import argparse
import json
import os
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


def main() -> int:
    parser = argparse.ArgumentParser(description="PR237 policy enforcement probe")
    parser.add_argument("--hook-config", default=".github/hooks/repo-truth-policy.json")
    parser.add_argument(
        "--json-output", default="test-results/237/policy_enforcement_probe.json"
    )
    parser.add_argument(
        "--md-output", default="test-results/237/policy_enforcement_probe.md"
    )
    args = parser.parse_args()

    issues: list[str] = []
    advisories: list[str] = []

    hook_config_path = REPO_ROOT / args.hook_config
    hook_config = _read_json(hook_config_path)
    if hook_config is None:
        issues.append("missing_or_invalid_hook_config")
        hook_config = {}

    hooks = (
        hook_config.get("hooks") if isinstance(hook_config.get("hooks"), dict) else {}
    )
    session_end = (
        hooks.get("sessionEnd") if isinstance(hooks.get("sessionEnd"), list) else []
    )
    if not session_end:
        issues.append("sessionEnd_hook_missing")

    expected_cmd = "bash scripts/agent_repo_truth_policy_gate.sh"
    has_expected_cmd = any(
        isinstance(entry, dict) and entry.get("bash") == expected_cmd
        for entry in session_end
    )
    if not has_expected_cmd:
        issues.append("repo_truth_policy_command_missing")

    policy_script = REPO_ROOT / "scripts/agent_repo_truth_policy_gate.sh"
    if not policy_script.exists():
        issues.append("policy_script_missing")
    else:
        if not os.access(policy_script, os.R_OK):
            issues.append("policy_script_not_readable")
        script_text = _read_text(policy_script)
        if "test-results/235/decision_gate.json" not in script_text:
            issues.append("policy_script_missing_pr235_gate_check")
        if "test-results/237/agent_decision_gate.json" not in script_text:
            issues.append("policy_script_missing_pr237_gate_check")

    hooks_readme = _read_text(REPO_ROOT / ".github/hooks/README.md")
    if "repo-truth-policy.json" not in hooks_readme:
        advisories.append("hooks_readme_missing_repo_truth_policy_reference")

    docs_en = _read_text(REPO_ROOT / "docs/CHAT_OPERATOR.md")
    docs_pl = _read_text(REPO_ROOT / "docs/PL/CHAT_OPERATOR.md")
    if "local-first-policy-enforcement-probe" not in docs_en:
        advisories.append("docs_en_missing_policy_probe_reference")
    if "local-first-policy-enforcement-probe" not in docs_pl:
        advisories.append("docs_pl_missing_policy_probe_reference")

    verdict = "pass" if not issues else "fail"
    report = {
        "scope": "pr237-policy-enforcement-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "issues": issues,
        "advisories": advisories,
        "inputs": {
            "hook_config": str(hook_config_path.resolve()),
            "policy_script": str(policy_script.resolve()),
            "hooks_readme": str((REPO_ROOT / ".github/hooks/README.md").resolve()),
        },
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR237 Policy Enforcement Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
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
