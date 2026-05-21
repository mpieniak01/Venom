#!/usr/bin/env python3
"""PR242 gate: aggregate helper probe reports and fail on any red case."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS = [
    "test-results/242/as_is_routing_matrix.json",
    "test-results/242/command_execution_loop_probe.json",
    "test-results/242/native_chat_probe.json",
    "test-results/242/vscode_executor_probe.json",
]


def _read_report(rel_path: str) -> dict[str, Any]:
    path = REPO_ROOT / rel_path
    if not path.exists():
        return {"report": rel_path, "verdict": "missing", "issues": ["report_missing"]}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"report": rel_path, "verdict": "invalid", "issues": ["invalid_json"]}
    if not isinstance(payload, dict):
        return {"report": rel_path, "verdict": "invalid", "issues": ["invalid_shape"]}
    payload["report"] = rel_path
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="PR242 aggregate helper gate")
    parser.add_argument(
        "--reports",
        nargs="*",
        default=DEFAULT_REPORTS,
    )
    parser.add_argument(
        "--json-output",
        default="test-results/242/pr242_gate.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/242/pr242_gate.md",
    )
    args = parser.parse_args()

    report_payloads = [_read_report(rel) for rel in args.reports]
    failing = [
        payload
        for payload in report_payloads
        if str(payload.get("verdict", "")).lower() != "pass"
    ]
    verdict = "pass" if not failing else "fail"

    result = {
        "scope": "pr242-helper-gate",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "reports": report_payloads,
        "failing_reports": [str(payload.get("report", "")) for payload in failing],
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR242 Helper Gate",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "| report | verdict |",
        "|---|---|",
    ]
    for payload in report_payloads:
        md_lines.append(
            f"| `{payload.get('report', '<unknown>')}` | `{payload.get('verdict', 'missing')}` |"
        )
    if failing:
        md_lines.extend(["", "## Failing Reports"])
        md_lines.extend(
            f"- `{payload.get('report', '<unknown>')}`" for payload in failing
        )
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
