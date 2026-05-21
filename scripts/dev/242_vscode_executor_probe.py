#!/usr/bin/env python3
"""PR242 probe: VS Code executor testability without IDE."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_json(rel_path: str) -> dict[str, Any]:
    path = REPO_ROOT / rel_path
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(rel_path: str) -> str:
    path = REPO_ROOT / rel_path
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="PR242 VS Code executor probe")
    parser.add_argument(
        "--json-output",
        default="test-results/242/vscode_executor_probe.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/242/vscode_executor_probe.md",
    )
    args = parser.parse_args()

    issues: list[str] = []
    package = _read_json("tools/vscode-chat-executor/package.json")
    extension = _read_text("tools/vscode-chat-executor/src/extension.ts")
    extension_core = _read_text(
        "tools/vscode-chat-executor/src/core/command-execution.ts"
    )

    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        scripts = {}
    if "test" not in scripts:
        issues.append("package_missing_test_script")
    if "test:contract" not in scripts:
        issues.append("package_missing_test_contract_script")

    contributes = package.get("contributes")
    tools: list[str] = []
    participants: list[str] = []
    if isinstance(contributes, dict):
        raw_tools = contributes.get("languageModelTools")
        if isinstance(raw_tools, list):
            for item in raw_tools:
                if isinstance(item, dict):
                    tools.append(str(item.get("name", "")).strip())
        raw_parts = contributes.get("chatParticipants")
        if isinstance(raw_parts, list):
            for item in raw_parts:
                if isinstance(item, dict):
                    participants.append(str(item.get("id", "")).strip())

    for required_tool in [
        "venom_git_status",
        "venom_search_code",
        "venom_read_file",
        "venom_exec_safe",
    ]:
        if required_tool not in tools:
            issues.append(f"missing_language_model_tool:{required_tool}")
    if "venom.agent" not in participants:
        issues.append("missing_chat_participant:venom.agent")

    if (
        "LanguageModelToolResultPart" not in extension
        and "LanguageModelToolResultPart" not in extension_core
    ):
        issues.append("extension_missing_tool_result_roundtrip")
    if (
        "request.model.sendRequest" not in extension
        and "request.model.sendRequest" not in extension_core
    ):
        issues.append("extension_missing_send_request_call")
    if (
        '"tool": "runSubagent"' in extension
        or '"tool": "runSubagent"' in extension_core
    ):
        issues.append("extension_contains_raw_runSubagent_payload_literal")

    verdict = "pass" if not issues else "fail"
    result = {
        "scope": "pr242-vscode-executor-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "issues": issues,
        "observed": {
            "scripts": sorted(scripts.keys()),
            "tools": tools,
            "participants": participants,
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
        "# PR242 VS Code Executor Probe",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "## Observed",
        f"- scripts: `{', '.join(result['observed']['scripts'])}`",
        f"- tools: `{', '.join(tools) if tools else '<none>'}`",
        f"- participants: `{', '.join(participants) if participants else '<none>'}`",
        "",
        "## Issues",
    ]
    if issues:
        md_lines.extend(f"- `{issue}`" for issue in issues)
    else:
        md_lines.append("- `<none>`")
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
