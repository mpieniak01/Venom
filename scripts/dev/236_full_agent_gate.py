#!/usr/bin/env python3
"""PR236 final gate for the Venom full-agent contract."""

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


def _report_verdict(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return "missing"
    verdict = report.get("verdict")
    if isinstance(verdict, str) and verdict:
        return verdict
    return "invalid"


def _collect_issues(report: dict[str, Any] | None, prefix: str) -> list[str]:
    if not isinstance(report, dict):
        return [f"{prefix}:missing_report"]
    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    collected: list[str] = []
    for issue in issues:
        if isinstance(issue, str) and issue:
            collected.append(f"{prefix}:{issue}")
    if _report_verdict(report) != "pass":
        collected.append(f"{prefix}:verdict_{_report_verdict(report)}")
    return collected


def _collect_advisories(report: dict[str, Any] | None, prefix: str) -> list[str]:
    if not isinstance(report, dict):
        return []
    advisories = (
        report.get("advisories") if isinstance(report.get("advisories"), list) else []
    )
    collected: list[str] = []
    for adv in advisories:
        if isinstance(adv, str) and adv:
            collected.append(f"{prefix}:{adv}")
    return collected


def main() -> int:
    parser = argparse.ArgumentParser(description="PR236 final gate")
    parser.add_argument(
        "--persona-report", default="test-results/236/full_agent_contract.json"
    )
    parser.add_argument(
        "--tool-report", default="test-results/236/full_agent_tool.json"
    )
    parser.add_argument(
        "--debug-report", default="test-results/236/full_agent_debug.json"
    )
    parser.add_argument(
        "--handoff-report", default="test-results/236/full_agent_handoff.json"
    )
    parser.add_argument(
        "--json-output", default="test-results/236/full_agent_gate.json"
    )
    parser.add_argument("--md-output", default="test-results/236/full_agent_gate.md")
    args = parser.parse_args()

    persona_report = _read_json(REPO_ROOT / args.persona_report)
    tool_report = _read_json(REPO_ROOT / args.tool_report)
    debug_report = _read_json(REPO_ROOT / args.debug_report)
    handoff_report = _read_json(REPO_ROOT / args.handoff_report)

    issues: list[str] = []
    advisories: list[str] = []

    issues.extend(_collect_issues(persona_report, "persona"))
    issues.extend(_collect_issues(tool_report, "tool"))
    issues.extend(_collect_issues(debug_report, "debug"))
    issues.extend(_collect_issues(handoff_report, "handoff"))

    advisories.extend(_collect_advisories(persona_report, "persona"))
    advisories.extend(_collect_advisories(tool_report, "tool"))
    advisories.extend(_collect_advisories(debug_report, "debug"))
    advisories.extend(_collect_advisories(handoff_report, "handoff"))

    if persona_report is None:
        issues.append("persona:missing_report_file")
    if tool_report is None:
        issues.append("tool:missing_report_file")
    if debug_report is None:
        issues.append("debug:missing_report_file")
    if handoff_report is None:
        issues.append("handoff:missing_report_file")

    result = {
        "scope": "pr236-full-agent-gate",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": "pass" if not issues else "fail",
        "issues": issues,
        "advisories": advisories,
        "reports": {
            "persona": {
                "path": str((REPO_ROOT / args.persona_report).resolve()),
                "verdict": _report_verdict(persona_report),
            },
            "tool": {
                "path": str((REPO_ROOT / args.tool_report).resolve()),
                "verdict": _report_verdict(tool_report),
            },
            "debug": {
                "path": str((REPO_ROOT / args.debug_report).resolve()),
                "verdict": _report_verdict(debug_report),
            },
            "handoff": {
                "path": str((REPO_ROOT / args.handoff_report).resolve()),
                "verdict": _report_verdict(handoff_report),
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
        "# PR236 Full Agent Gate",
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
        md_lines.extend(f"- `{issue}`" for issue in issues)
    else:
        md_lines.append("- `<none>`")

    md_lines.extend(["", "## Advisories"])
    if advisories:
        md_lines.extend(f"- `{adv}`" for adv in advisories)
    else:
        md_lines.append("- `<none>`")

    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
