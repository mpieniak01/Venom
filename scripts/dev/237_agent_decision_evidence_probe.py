#!/usr/bin/env python3
"""PR237 probe: validate decision evidence schema from repo-truth-first agent run."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], timeout: float = 180.0) -> tuple[bool, int, str, str]:
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
        return False, 124, "", "timeout"
    return proc.returncode == 0, proc.returncode, proc.stdout or "", proc.stderr or ""


def _extract_agent_text(stdout: str) -> str:
    for line in stdout.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "item.completed":
            continue
        item = payload.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str):
                return text.strip()
    return ""


def _coerce_json(text: str) -> dict[str, Any] | None:
    normalized = text.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            normalized = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _repo_truth() -> dict[str, str]:
    def run_local(cmd: list[str]) -> str:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
        )
        return (proc.stdout or "").strip()

    return {
        "branch": run_local(["git", "branch", "--show-current"]),
        "status_short_branch": run_local(["git", "status", "--short", "--branch"]),
        "diff_shortstat": run_local(["git", "diff", "--shortstat"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PR237 agent decision evidence probe")
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument(
        "--contract",
        default="config/chat_operator/venom_agent_decision_contract.json",
    )
    parser.add_argument(
        "--json-output",
        default="test-results/237/agent_decision_evidence_probe.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/237/agent_decision_evidence_probe.md",
    )
    args = parser.parse_args()

    truth = _repo_truth()
    prompt = (
        "Na podstawie preflightu repo zwroc tylko JSON.\n"
        "Wymagane pola: repo_truth, tools_used, decision, next_step.\n"
        "repo_truth ma zawierac branch i diff_shortstat jako string lub obiekt z tymi polami.\n"
        "tools_used ma byc lista nazw narzedzi wykorzystanych lub dostarczonych danych preflight.\n"
        "decision i next_step maja byc krotkie, operacyjne i po polsku.\n"
        "Nie dodawaj markdown ani dodatkowego tekstu."
    )

    cmd = [
        "bash",
        "scripts/dev/236b_repo_truth_agent_run.sh",
    ]
    env_cmd = ["env", f"MODEL={args.model}", f"PROMPT={prompt}"] + cmd
    ok, exit_code, stdout, stderr = _run(env_cmd, timeout=240.0)

    issues: list[str] = []
    advisories: list[str] = []

    if not ok:
        issues.append("agent_run_failed")

    agent_text = _extract_agent_text(stdout)
    if not agent_text:
        issues.append("agent_message_missing")

    payload = _coerce_json(agent_text) if agent_text else None
    if payload is None:
        issues.append("agent_message_not_json_object")
        payload = {}

    required_fields = ["repo_truth", "tools_used", "decision", "next_step"]
    for field in required_fields:
        if field not in payload:
            issues.append(f"missing_field:{field}")

    repo_truth_value = payload.get("repo_truth")
    branch = ""
    diff = ""
    if isinstance(repo_truth_value, dict):
        branch = str(repo_truth_value.get("branch") or "").strip()
        diff = str(repo_truth_value.get("diff_shortstat") or "").strip()
    elif isinstance(repo_truth_value, str):
        lines = [line.strip() for line in repo_truth_value.splitlines() if line.strip()]
        for line in lines:
            lower = line.lower()
            if lower.startswith("branch:"):
                branch = line.split(":", 1)[1].strip()
            if lower.startswith("diff_shortstat:"):
                diff = line.split(":", 1)[1].strip()
    else:
        issues.append("repo_truth_invalid_type")
    if not branch:
        issues.append("repo_truth_branch_missing")
    elif branch != truth["branch"]:
        issues.append("repo_truth_branch_mismatch")
    if not diff:
        issues.append("repo_truth_diff_shortstat_missing")
    elif diff != truth["diff_shortstat"]:
        issues.append("repo_truth_diff_shortstat_mismatch")

    tools_used = payload.get("tools_used")
    if not isinstance(tools_used, list):
        issues.append("tools_used_not_list")
        tools_used = []
    normalized_tools = [str(item).strip() for item in tools_used if str(item).strip()]
    if not normalized_tools:
        issues.append("tools_used_empty")
    elif not any(
        "git" in item.lower() or "terminal" in item.lower() for item in normalized_tools
    ):
        advisories.append("tools_used_without_terminal_or_git_marker")

    decision = str(payload.get("decision") or "").strip()
    next_step = str(payload.get("next_step") or "").strip()
    if not decision:
        issues.append("decision_empty")
    if not next_step:
        issues.append("next_step_empty")

    verdict = "pass" if not issues else "fail"
    report = {
        "scope": "pr237-agent-decision-evidence-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "model": args.model,
        "verdict": verdict,
        "issues": issues,
        "advisories": advisories,
        "expected_repo_truth": truth,
        "agent_run": {
            "model": args.model,
            "ok": ok,
            "exit_code": exit_code,
            "stderr_excerpt": (stderr or "")[:600],
            "agent_message": agent_text,
        },
        "parsed_payload": payload,
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR237 Agent Decision Evidence Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Model: `{args.model}`",
        f"Verdict: `{verdict}`",
        "",
        "## Expected Repo Truth",
        f"- branch: `{truth['branch']}`",
        f"- diff_shortstat: `{truth['diff_shortstat']}`",
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
