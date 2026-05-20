#!/usr/bin/env python3
"""PR235 probe for VSCODE_AGENT terminal contract.

This probe checks whether a command can reliably observe VSCODE_AGENT and
produces a small machine-readable report for local-first diagnostics.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class CaseResult:
    name: str
    env_value: str | None
    expected_present: bool
    ok: bool
    exit_code: int
    observed_raw: str
    observed_present: bool
    verdict: str


def _run_case(name: str, env_value: str | None, expected_present: bool) -> CaseResult:
    cmd = [
        "python3",
        "-c",
        (
            "import os, json; "
            "value = os.getenv('VSCODE_AGENT'); "
            "print(json.dumps({'value': value, 'present': bool(value)}))"
        ),
    ]
    env = os.environ.copy()
    if env_value is None:
        env.pop("VSCODE_AGENT", None)
    else:
        env["VSCODE_AGENT"] = env_value

    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    observed_raw = (proc.stdout or "").strip()
    observed_present = False
    if observed_raw:
        try:
            payload = json.loads(observed_raw)
            observed_present = bool(payload.get("present"))
        except json.JSONDecodeError:
            observed_present = False

    verdict = (
        "pass"
        if (proc.returncode == 0 and observed_present == expected_present)
        else "fail"
    )
    return CaseResult(
        name=name,
        env_value=env_value,
        expected_present=expected_present,
        ok=proc.returncode == 0,
        exit_code=proc.returncode,
        observed_raw=observed_raw,
        observed_present=observed_present,
        verdict=verdict,
    )


def _to_dict(case: CaseResult) -> dict[str, Any]:
    return {
        "name": case.name,
        "env_value": case.env_value,
        "expected_present": case.expected_present,
        "ok": case.ok,
        "exit_code": case.exit_code,
        "observed_raw": case.observed_raw,
        "observed_present": case.observed_present,
        "verdict": case.verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PR235 VSCODE_AGENT terminal probe")
    parser.add_argument(
        "--json-output", default="test-results/235/vscode_agent_probe.json"
    )
    parser.add_argument("--md-output", default="test-results/235/vscode_agent_probe.md")
    args = parser.parse_args()

    cases = [
        _run_case(name="unset", env_value=None, expected_present=False),
        _run_case(name="set_1", env_value="1", expected_present=True),
    ]

    report = {
        "scope": "pr235-vscode-agent-terminal-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "cases": [_to_dict(case) for case in cases],
        "summary": {
            "total": len(cases),
            "passed": sum(1 for case in cases if case.verdict == "pass"),
            "failed": sum(1 for case in cases if case.verdict == "fail"),
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
        "# PR235 VSCODE_AGENT Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        "",
        "## Summary",
        f"- total: `{report['summary']['total']}`",
        f"- passed: `{report['summary']['passed']}`",
        f"- failed: `{report['summary']['failed']}`",
        "",
    ]
    for case in report["cases"]:
        md_lines.extend(
            [
                f"## Case: {case['name']}",
                f"- env_value: `{case['env_value']}`",
                f"- expected_present: `{case['expected_present']}`",
                f"- observed_present: `{case['observed_present']}`",
                f"- exit_code: `{case['exit_code']}`",
                f"- verdict: `{case['verdict']}`",
                f"- observed_raw: `{case['observed_raw']}`",
                "",
            ]
        )

    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")

    return 0 if report["summary"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
