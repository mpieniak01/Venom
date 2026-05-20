#!/usr/bin/env python3
"""PR233B phase 2 probe for prompt/tool-call flakiness.

This runner uses Codex CLI as a locally available proxy for prompt/tool
stability. It is intentionally small and repeatable:
- same prompt repeated multiple times
- prompt variants that emulate the 233B phase-2 matrix
- optional rule suppression to isolate repo guidance

The output is a JSON report plus a markdown summary.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class RunResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def _run_cmd(cmd: list[str], *, timeout: float = 120.0) -> RunResult:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return RunResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=(proc.stdout or "").strip(),
            stderr=(proc.stderr or "").strip(),
        )
    except subprocess.TimeoutExpired as exc:
        return RunResult(
            ok=False,
            exit_code=124,
            stdout=(exc.stdout or "").strip() if exc.stdout else "",
            stderr=f"timeout after {timeout}s",
        )


def _extract_agent_message(stdout: str) -> str:
    for line in stdout.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "item.completed":
            item = payload.get("item") or {}
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text") or ""
                if isinstance(text, str):
                    return text.strip()
    return ""


def _classify_message(text: str) -> dict[str, bool]:
    lowered = text.lower()
    return {
        "tool_request": "send_input" in lowered,
        "mentions_git_status": "git status" in lowered,
        "mentions_git_diff": "git diff --shortstat" in lowered,
        "mentions_codebase": "#codebase" in lowered,
        "text_only": not any(
            token in lowered
            for token in ["send_input", "git status", "git diff --shortstat"]
        ),
    }


def _build_cases(base_prompt: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "baseline_strict",
            "description": "baseline prompt with repo rules enabled",
            "prompt": base_prompt,
            "extra_flags": [],
        },
        {
            "id": "baseline_ignore_rules",
            "description": "baseline prompt with repo rules suppressed",
            "prompt": base_prompt,
            "extra_flags": ["--ignore-rules"],
        },
        {
            "id": "codebase_mention",
            "description": "baseline prompt with explicit #codebase mention",
            "prompt": f"{base_prompt}\n#codebase",
            "extra_flags": [],
        },
        {
            "id": "plain_prompt",
            "description": "plain repo status prompt with minimal instruction",
            "prompt": "Sprawdz status repo i ryzyka zmian.",
            "extra_flags": [],
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="PR233B phase-2 tool flake probe")
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--json-output", default="test-results/233b/tool_flake_probe.json"
    )
    parser.add_argument("--md-output", default="test-results/233b/tool_flake_probe.md")
    args = parser.parse_args()

    base_prompt = (
        "Sprawdz status repo i ryzyka zmian. Uzyj narzedzi, nie zgaduj. "
        "Najpierw git status i git diff --shortstat, potem wnioski."
    )
    cases = _build_cases(base_prompt)
    report: dict[str, Any] = {
        "scope": "pr233b-phase2-tool-flake-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "model": args.model,
        "runs_per_case": args.runs,
        "cases": [],
    }

    for case in cases:
        per_run: list[dict[str, Any]] = []
        for idx in range(args.runs):
            cmd = [
                "codex",
                "exec",
                "--json",
                "--oss",
                "--local-provider",
                "ollama",
                "-m",
                args.model,
                "--cd",
                str(REPO_ROOT),
                "--sandbox",
                "workspace-write",
            ]
            cmd.extend(case["extra_flags"])
            cmd.append(case["prompt"])

            result = _run_cmd(cmd, timeout=120.0)
            agent_message = _extract_agent_message(result.stdout)
            classification = _classify_message(agent_message)
            per_run.append(
                {
                    "run": idx + 1,
                    "ok": result.ok,
                    "exit_code": result.exit_code,
                    "agent_message": agent_message,
                    "stderr_excerpt": result.stderr[-240:],
                    **classification,
                }
            )

        summary = {
            "tool_request_runs": sum(1 for item in per_run if item["tool_request"]),
            "text_only_runs": sum(1 for item in per_run if item["text_only"]),
            "git_status_mentions": sum(
                1 for item in per_run if item["mentions_git_status"]
            ),
            "git_diff_mentions": sum(
                1 for item in per_run if item["mentions_git_diff"]
            ),
            "codebase_mentions": sum(
                1 for item in per_run if item["mentions_codebase"]
            ),
            "ok_runs": sum(1 for item in per_run if item["ok"]),
        }
        report["cases"].append(
            {
                "id": case["id"],
                "description": case["description"],
                "extra_flags": case["extra_flags"],
                "prompt": case["prompt"],
                "runs": per_run,
                "summary": summary,
            }
        )

    json_path = REPO_ROOT / args.json_output
    md_path = REPO_ROOT / args.md_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# PR233B Phase 2 Tool Flake Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Model: `{args.model}`",
        f"Runs per case: `{args.runs}`",
        "",
    ]
    for case in report["cases"]:
        summary = case["summary"]
        md_lines.extend(
            [
                f"## {case['id']}",
                f"- description: {case['description']}",
                f"- flags: `{case['extra_flags']}`",
                f"- tool_request_runs: `{summary['tool_request_runs']}`",
                f"- text_only_runs: `{summary['text_only_runs']}`",
                f"- git_status_mentions: `{summary['git_status_mentions']}`",
                f"- git_diff_mentions: `{summary['git_diff_mentions']}`",
                f"- codebase_mentions: `{summary['codebase_mentions']}`",
                f"- ok_runs: `{summary['ok_runs']}`",
                "",
            ]
        )
    md_lines.append(f"JSON: `{json_path}`")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
