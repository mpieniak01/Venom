#!/usr/bin/env python3
"""PR237 probe: environment and repo-index readiness for decision engine."""

from __future__ import annotations

import argparse
import json
import shutil
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


def main() -> int:
    parser = argparse.ArgumentParser(description="PR237 env/index readiness probe")
    parser.add_argument(
        "--contract",
        default="config/chat_operator/venom_agent_decision_contract.json",
    )
    parser.add_argument(
        "--json-output",
        default="test-results/237/env_index_readiness_probe.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/237/env_index_readiness_probe.md",
    )
    args = parser.parse_args()

    contract = _read_json(REPO_ROOT / args.contract) or {}
    issues: list[str] = []
    advisories: list[str] = []

    required_commands = contract.get("required_env_commands", [])
    required_refs = contract.get("required_repo_refs", [])
    required_markers = contract.get("required_index_markers", [])

    command_status: dict[str, dict[str, Any]] = {}
    for cmd in required_commands if isinstance(required_commands, list) else []:
        present = bool(shutil.which(str(cmd)))
        command_status[str(cmd)] = {"present": present}
        if not present:
            issues.append(f"missing_command:{cmd}")

    git_ok, git_branch = _run(["git", "branch", "--show-current"])
    git_status_ok, git_status = _run(["git", "status", "--short", "--branch"])
    rg_ok, rg_result = _run(["rg", "--files"], timeout=60.0)
    rg_file_count = (
        len([line for line in rg_result.splitlines() if line.strip()]) if rg_ok else 0
    )

    if not git_ok:
        issues.append("git_branch_failed")
    if not git_status_ok:
        issues.append("git_status_failed")
    if not rg_ok:
        issues.append("rg_files_failed")
    elif rg_file_count == 0:
        issues.append("rg_files_empty")

    missing_refs: list[str] = []
    for ref in required_refs if isinstance(required_refs, list) else []:
        if not (REPO_ROOT / str(ref)).exists():
            missing_refs.append(str(ref))
    if missing_refs:
        issues.append("missing_repo_refs:" + ",".join(missing_refs))

    combined_docs = "\n".join(
        [
            _read_text(REPO_ROOT / ".github/agents/venom-full-agent.agent.md"),
            _read_text(REPO_ROOT / "docs/CHAT_OPERATOR.md"),
            _read_text(REPO_ROOT / "docs/PL/CHAT_OPERATOR.md"),
        ]
    )
    for marker in required_markers if isinstance(required_markers, list) else []:
        if str(marker) not in combined_docs:
            issues.append(f"missing_index_marker:{marker}")

    if "local-first-repo-truth-agent" not in _read_text(REPO_ROOT / "make/runtime.mk"):
        advisories.append("missing_repo_truth_agent_make_target")

    verdict = "pass" if not issues else "fail"
    report = {
        "scope": "pr237-env-index-readiness-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "issues": issues,
        "advisories": advisories,
        "contract": contract,
        "checks": {
            "commands": command_status,
            "git_branch": {"ok": git_ok, "value": git_branch},
            "git_status": {"ok": git_status_ok, "value": git_status},
            "rg_files": {"ok": rg_ok, "count": rg_file_count},
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
        "# PR237 Env Index Readiness Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "## Core Checks",
        f"- git_branch_ok: `{git_ok}`",
        f"- git_status_ok: `{git_status_ok}`",
        f"- rg_files_ok: `{rg_ok}`",
        f"- rg_file_count: `{rg_file_count}`",
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
