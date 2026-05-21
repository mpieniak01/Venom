#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = REPO_ROOT / "test-results/239/selftest_report.json"
OUT_MD = REPO_ROOT / "test-results/239/selftest_report.md"


def run_cmd(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    proc = subprocess.run(
        cmd, cwd=str(cwd or REPO_ROOT), text=True, capture_output=True
    )
    return {
        "cmd": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ok": proc.returncode == 0,
    }


def check_extension_contract() -> dict[str, Any]:
    pkg_path = REPO_ROOT / "tools/vscode-chat-executor/package.json"
    src_path = REPO_ROOT / "tools/vscode-chat-executor/src/extension.ts"
    issues: list[str] = []
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "issues": [f"package_json_error:{exc}"]}

    tools = pkg.get("contributes", {}).get("languageModelTools", [])
    names = {t.get("name") for t in tools if isinstance(t, dict)}
    if "run_git_status" not in names:
        issues.append("missing_languageModelTool:run_git_status")

    participants = pkg.get("contributes", {}).get("chatParticipants", [])
    pnames = {p.get("name") for p in participants if isinstance(p, dict)}
    for required in ("venom-exec", "venom-agent"):
        if required not in pnames:
            issues.append(f"missing_chatParticipant:{required}")

    src = src_path.read_text(encoding="utf-8")
    if "TOOL_NAME = 'run_git_status'" not in src:
        issues.append("tool_name_constant_mismatch")
    if "vscode.lm.invokeTool(" not in src:
        issues.append("missing_lm_invokeTool_call")
    if "REPO_ROOT=" not in src:
        issues.append("missing_repo_root_evidence_in_output")

    return {"ok": not issues, "issues": issues}


def main() -> int:
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "name": "runtime_status",
            "result": run_cmd(["make", "-C", str(REPO_ROOT), "local-first-status"]),
        }
    )
    checks.append(
        {
            "name": "session_probe",
            "result": run_cmd(
                [
                    "make",
                    "-C",
                    str(REPO_ROOT),
                    "local-first-copilot-agent-session-probe",
                ]
            ),
        }
    )
    checks.append(
        {
            "name": "terminal_tool_loop_probe",
            "result": run_cmd(
                [
                    "make",
                    "-C",
                    str(REPO_ROOT),
                    "local-first-vscode-terminal-tool-loop-probe",
                ]
            ),
        }
    )
    checks.append(
        {
            "name": "model_tool_call_probe",
            "result": run_cmd(
                [
                    "make",
                    "-C",
                    str(REPO_ROOT),
                    "local-first-local-model-tool-call-probe",
                    "MODEL=qwen3.5:9b",
                ]
            ),
        }
    )
    checks.append(
        {
            "name": "execution_lane_git_status",
            "result": run_cmd(["make", "-C", str(REPO_ROOT), "local-first-git-status"]),
        }
    )
    checks.append(
        {
            "name": "repo_truth_reply",
            "result": run_cmd(
                ["make", "-C", str(REPO_ROOT), "local-first-repo-truth-reply"]
            ),
        }
    )
    checks.append(
        {
            "name": "extension_build",
            "result": run_cmd(
                ["npm", "run", "build"], cwd=REPO_ROOT / "tools/vscode-chat-executor"
            ),
        }
    )

    ext = check_extension_contract()
    checks.append(
        {
            "name": "extension_contract",
            "result": {
                "cmd": "static contract check",
                "exit_code": 0 if ext["ok"] else 2,
                "stdout": json.dumps(ext, ensure_ascii=False),
                "stderr": "",
                "ok": ext["ok"],
            },
        }
    )

    failed = [c for c in checks if not c["result"]["ok"]]
    verdict = "pass" if not failed else "fail"

    report = {
        "scope": "pr239-selftest",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "checks": checks,
        "failed_checks": [c["name"] for c in failed],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# PR239 Selftest Report",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "## Checks",
    ]
    for c in checks:
        lines.append(f"- `{c['name']}`: `{'PASS' if c['result']['ok'] else 'FAIL'}`")
    if failed:
        lines += ["", "## Failed", *[f"- `{c['name']}`" for c in failed]]

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {"verdict": verdict, "failed_checks": report["failed_checks"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"Saved JSON: {OUT_JSON}")
    print(f"Saved MD:   {OUT_MD}")
    return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
