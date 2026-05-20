#!/usr/bin/env python3
"""PR236A probe: enforce repo-truth preflight before agent analysis.

This probe is intentionally deterministic:
1. Collect repository truth using real git commands.
2. Pass the captured truth to the agent as explicit input context.
3. Validate that the answer reflects that exact truth.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class CmdResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def _run_cmd(cmd: list[str], *, timeout: float = 120.0) -> CmdResult:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CmdResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=(proc.stdout or "").strip(),
            stderr=(proc.stderr or "").strip(),
        )
    except subprocess.TimeoutExpired:
        return CmdResult(
            ok=False, exit_code=124, stdout="", stderr=f"timeout after {timeout}s"
        )


def _agent_exec(model: str, prompt: str, *, timeout: float = 180.0) -> CmdResult:
    codex = shutil.which("codex")
    if not codex:
        return CmdResult(ok=False, exit_code=127, stdout="", stderr="codex not found")
    cmd = [
        codex,
        "exec",
        "--json",
        "--oss",
        "--local-provider",
        "ollama",
        "-m",
        model,
        "--cd",
        str(REPO_ROOT),
        "--sandbox",
        "workspace-write",
        prompt,
    ]
    return _run_cmd(cmd, timeout=timeout)


def _extract_agent_message(stdout: str) -> str:
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


def _repo_truth() -> dict[str, str]:
    branch = _run_cmd(["git", "branch", "--show-current"])
    status = _run_cmd(["git", "status", "--short", "--branch"])
    diff = _run_cmd(["git", "diff", "--shortstat"])
    head = _run_cmd(["git", "rev-parse", "--short", "HEAD"])
    return {
        "branch": branch.stdout,
        "status_short_branch": status.stdout,
        "diff_shortstat": diff.stdout,
        "head": head.stdout,
    }


def _pick_changed_paths(status_short_branch: str) -> list[str]:
    lines = [line.rstrip() for line in status_short_branch.splitlines() if line.strip()]
    paths: list[str] = []
    for line in lines:
        if line.startswith("## "):
            continue
        if len(line) < 4:
            continue
        maybe_path = line[3:].strip()
        if maybe_path:
            paths.append(maybe_path)
    return paths[:5]


def _build_prompt(truth: dict[str, str]) -> str:
    return (
        "Masz ponizej surowe wyniki narzedziowe z terminala (zrodlo prawdy repo). "
        "Nie zgaduj, uzyj tylko tych danych.\n\n"
        "[BEGIN git-branch]\n"
        f"{truth['branch']}\n"
        "[END git-branch]\n\n"
        "[BEGIN git-status-short-branch]\n"
        f"{truth['status_short_branch']}\n"
        "[END git-status-short-branch]\n\n"
        "[BEGIN git-diff-shortstat]\n"
        f"{truth['diff_shortstat']}\n"
        "[END git-diff-shortstat]\n\n"
        "Zwróć TYLKO JSON z polami: branch, diff_shortstat, changed_paths, summary.\n"
        "changed_paths: lista maksymalnie 5 sciezek ze statusu.\n"
        "summary: 1 zdanie operacyjne po polsku."
    )


def _validate(
    message: str, truth: dict[str, str]
) -> tuple[str, list[str], dict[str, Any]]:
    issues: list[str] = []
    payload: dict[str, Any] = {}
    normalized = message.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if (
            len(lines) >= 3
            and lines[0].startswith("```")
            and lines[-1].strip() == "```"
        ):
            normalized = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(normalized)
        if not isinstance(payload, dict):
            issues.append("agent_output_not_object")
            payload = {}
    except json.JSONDecodeError:
        issues.append("agent_output_not_json")

    branch = str(payload.get("branch") or "").strip()
    diff_raw = payload.get("diff_shortstat")
    if isinstance(diff_raw, dict):
        files = diff_raw.get("files_changed")
        ins = diff_raw.get("insertions")
        dels = diff_raw.get("deletions")
        if files is not None and ins is not None and dels is not None:
            diff = f"{files} files changed, {ins} insertions(+), {dels} deletions(-)"
        else:
            diff = ""
    else:
        diff = str(diff_raw or "").strip()
    changed_paths = payload.get("changed_paths")

    expected_paths = _pick_changed_paths(truth["status_short_branch"])
    if branch != truth["branch"]:
        issues.append("branch_mismatch")
    if diff != truth["diff_shortstat"]:
        issues.append("diff_shortstat_mismatch")
    if not isinstance(changed_paths, list):
        issues.append("changed_paths_not_list")
        changed_paths = []
    normalized_changed = [
        str(item).strip() for item in changed_paths if str(item).strip()
    ]
    if expected_paths:
        missing = [p for p in expected_paths[:3] if p not in normalized_changed]
        if missing:
            issues.append("changed_paths_missing_expected_entries")

    verdict = "pass" if not issues else "fail"
    details = {
        "expected_paths_sample": expected_paths,
        "agent_paths": normalized_changed,
    }
    return verdict, issues, details


def main() -> int:
    parser = argparse.ArgumentParser(description="PR236A repo-truth preflight probe")
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument(
        "--json-output", default="test-results/236/repo_truth_preflight_probe.json"
    )
    parser.add_argument(
        "--md-output", default="test-results/236/repo_truth_preflight_probe.md"
    )
    args = parser.parse_args()

    truth = _repo_truth()
    preflight_ok = all(
        bool(truth[key]) for key in ["branch", "status_short_branch", "head"]
    )
    issues: list[str] = []
    if not preflight_ok:
        issues.append("repo_truth_preflight_incomplete")

    prompt = _build_prompt(truth)
    run = _agent_exec(args.model, prompt)
    message = _extract_agent_message(run.stdout)

    verdict = "fail"
    validation_details: dict[str, Any] = {}
    if run.ok and message:
        verdict, validation_issues, validation_details = _validate(message, truth)
        issues.extend(validation_issues)
    else:
        if not run.ok:
            issues.append("agent_exec_failed")
        if not message:
            issues.append("agent_message_missing")

    if issues:
        verdict = "fail"

    report = {
        "scope": "pr236a-repo-truth-preflight-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "issues": issues,
        "model": args.model,
        "preflight_truth": truth,
        "agent_exec": {
            "ok": run.ok,
            "exit_code": run.exit_code,
            "stderr": run.stderr,
            "agent_message": message,
        },
        "validation_details": validation_details,
    }

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR236A Repo Truth Preflight Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "## Preflight Truth",
        f"- branch: `{truth['branch']}`",
        f"- head: `{truth['head']}`",
        f"- diff_shortstat: `{truth['diff_shortstat'] or '<empty>'}`",
        "",
        "## Issues",
    ]
    if issues:
        for issue in issues:
            md_lines.append(f"- `{issue}`")
    else:
        md_lines.append("- `<none>`")
    md_lines.extend(["", f"JSON: `{json_path}`"])
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
