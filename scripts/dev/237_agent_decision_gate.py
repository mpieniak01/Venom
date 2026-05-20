#!/usr/bin/env python3
"""PR237 final gate for env/index readiness and decision evidence."""

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


def _verdict(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return "missing"
    value = report.get("verdict")
    return value if isinstance(value, str) and value else "invalid"


def _issues(report: dict[str, Any] | None, prefix: str) -> list[str]:
    if not isinstance(report, dict):
        return [f"{prefix}:missing_report"]
    out: list[str] = []
    entries = report.get("issues") if isinstance(report.get("issues"), list) else []
    for entry in entries:
        if isinstance(entry, str) and entry:
            out.append(f"{prefix}:{entry}")
    if _verdict(report) != "pass":
        out.append(f"{prefix}:verdict_{_verdict(report)}")
    return out


def _advisories(report: dict[str, Any] | None, prefix: str) -> list[str]:
    if not isinstance(report, dict):
        return []
    out: list[str] = []
    entries = (
        report.get("advisories") if isinstance(report.get("advisories"), list) else []
    )
    for entry in entries:
        if isinstance(entry, str) and entry:
            out.append(f"{prefix}:{entry}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="PR237 agent decision gate")
    parser.add_argument(
        "--state-registry-report",
        default="test-results/238g/agent_state_registry_probe.json",
    )
    parser.add_argument(
        "--env-index-report",
        default="test-results/237/env_index_readiness_probe.json",
    )
    parser.add_argument(
        "--decision-evidence-report",
        default="test-results/237/agent_decision_evidence_probe.json",
    )
    parser.add_argument(
        "--policy-report",
        default="test-results/237/policy_enforcement_probe.json",
    )
    parser.add_argument(
        "--json-output",
        default="test-results/237/agent_decision_gate.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/237/agent_decision_gate.md",
    )
    args = parser.parse_args()

    state_registry_report = _read_json(REPO_ROOT / args.state_registry_report)
    env_report = _read_json(REPO_ROOT / args.env_index_report)
    decision_report = _read_json(REPO_ROOT / args.decision_evidence_report)
    policy_report = _read_json(REPO_ROOT / args.policy_report)

    issues: list[str] = []
    advisories: list[str] = []
    if not isinstance(state_registry_report, dict):
        issues.append("state_registry:missing_report")
    else:
        state_verdict = _verdict(state_registry_report)
        if state_verdict != "pass":
            issues.append(f"state_registry:verdict_{state_verdict}")
        for entry in (
            state_registry_report.get("issues")
            if isinstance(state_registry_report.get("issues"), list)
            else []
        ):
            if isinstance(entry, str) and entry:
                issues.append(f"state_registry:{entry}")
        for entry in (
            state_registry_report.get("advisories")
            if isinstance(state_registry_report.get("advisories"), list)
            else []
        ):
            if isinstance(entry, str) and entry:
                advisories.append(f"state_registry:{entry}")
    issues.extend(_issues(env_report, "env_index"))
    issues.extend(_issues(decision_report, "decision_evidence"))
    issues.extend(_issues(policy_report, "policy"))
    advisories.extend(_advisories(state_registry_report, "state_registry"))
    advisories.extend(_advisories(env_report, "env_index"))
    advisories.extend(_advisories(decision_report, "decision_evidence"))
    advisories.extend(_advisories(policy_report, "policy"))

    result = {
        "scope": "pr237-agent-decision-gate",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": "pass" if not issues else "fail",
        "issues": issues,
        "advisories": advisories,
        "reports": {
            "state_registry": {
                "path": str((REPO_ROOT / args.state_registry_report).resolve()),
                "verdict": _verdict(state_registry_report),
            },
            "env_index": {
                "path": str((REPO_ROOT / args.env_index_report).resolve()),
                "verdict": _verdict(env_report),
            },
            "decision_evidence": {
                "path": str((REPO_ROOT / args.decision_evidence_report).resolve()),
                "verdict": _verdict(decision_report),
            },
            "policy": {
                "path": str((REPO_ROOT / args.policy_report).resolve()),
                "verdict": _verdict(policy_report),
            },
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
        "# PR237 Agent Decision Gate",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{result['verdict']}`",
        "",
        "## Reports",
    ]
    for name, report in result["reports"].items():
        md_lines.append(f"- {name}: `{report['verdict']}` -> `{report['path']}`")
    md_lines.extend(["", "## Issues"])
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

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
