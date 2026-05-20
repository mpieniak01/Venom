#!/usr/bin/env python3
"""PR236 probe for the Venom full-agent implementation handoff contract."""

from __future__ import annotations

import argparse
import json
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
    parser = argparse.ArgumentParser(description="PR236 full-agent handoff probe")
    parser.add_argument(
        "--contract",
        default="config/chat_operator/venom_full_agent_handoff_contract.json",
    )
    parser.add_argument(
        "--agent-file",
        default=".github/agents/venom-full-agent.agent.md",
    )
    parser.add_argument(
        "--json-output", default="test-results/236/full_agent_handoff.json"
    )
    parser.add_argument("--md-output", default="test-results/236/full_agent_handoff.md")
    args = parser.parse_args()

    contract = _read_json(REPO_ROOT / args.contract) or {}
    agent_text = _read_text(REPO_ROOT / args.agent_file)
    docs_en = _read_text(REPO_ROOT / "docs/CHAT_OPERATOR.md")
    docs_pl = _read_text(REPO_ROOT / "docs/PL/CHAT_OPERATOR.md")

    issues: list[str] = []
    advisories: list[str] = []

    if not contract:
        issues.append("missing_or_invalid_contract")

    required_terms = (
        contract.get("required_terms")
        if isinstance(contract.get("required_terms"), list)
        else []
    )
    handoff_steps = (
        contract.get("handoff_steps")
        if isinstance(contract.get("handoff_steps"), list)
        else []
    )

    if contract.get("planning_boundary") != "local-agent-plan-first":
        issues.append("planning_boundary_mismatch")
    if contract.get("handoff_lane") != "copilot-cli-worktree":
        issues.append("handoff_lane_mismatch")
    if contract.get("review_return_surface") != "main-vscode-window":
        issues.append("review_return_surface_mismatch")
    if contract.get("worktree_policy") != "isolated_worktree_required":
        issues.append("worktree_policy_mismatch")

    for term in required_terms:
        if term not in agent_text + "\n" + docs_en + "\n" + docs_pl:
            issues.append(f"missing_required_term:{term}")

    if (
        "If the task is not well-defined enough for handoff"
        not in agent_text + "\n" + docs_en + "\n" + docs_pl
    ):
        advisories.append("handoff_fallback_text_not_found")

    for step in handoff_steps:
        if step not in agent_text + "\n" + docs_en + "\n" + docs_pl:
            issues.append(f"missing_handoff_step:{step}")

    result = {
        "scope": "pr236-full-agent-handoff-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": "pass" if not issues else "fail",
        "issues": issues,
        "advisories": advisories,
        "contract": contract,
        "inputs": {
            "contract": str((REPO_ROOT / args.contract).resolve()),
            "agent_file": str((REPO_ROOT / args.agent_file).resolve()),
            "docs_en": str((REPO_ROOT / "docs/CHAT_OPERATOR.md").resolve()),
            "docs_pl": str((REPO_ROOT / "docs/PL/CHAT_OPERATOR.md").resolve()),
        },
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR236 Full Agent Handoff Probe",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{result['verdict']}`",
        "",
        "## Issues",
    ]
    md_lines.extend(f"- `{issue}`" for issue in issues) if issues else md_lines.append(
        "- `<none>`"
    )
    md_lines.extend(["", "## Advisories"])
    md_lines.extend(
        f"- `{adv}`" for adv in advisories
    ) if advisories else md_lines.append("- `<none>`")

    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
