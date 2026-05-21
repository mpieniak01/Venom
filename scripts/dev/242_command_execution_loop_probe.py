#!/usr/bin/env python3
"""PR242 probe: validate command execution loop contract and code anchors."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_json(rel_path: str) -> dict[str, Any]:
    path = REPO_ROOT / rel_path
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def _load_text(rel_path: str) -> str:
    path = REPO_ROOT / rel_path
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _missing_required_keys(payload: dict[str, Any], required: list[str]) -> list[str]:
    return [key for key in required if key not in payload]


def main() -> int:
    parser = argparse.ArgumentParser(description="PR242 command loop probe")
    parser.add_argument(
        "--loop-contract",
        default="config/chat_operator/pr242_command_execution_loop_contract.json",
    )
    parser.add_argument(
        "--response-contract",
        default="config/chat_operator/pr242_repo_truth_response_contract.json",
    )
    parser.add_argument(
        "--json-output",
        default="test-results/242/command_execution_loop_probe.json",
    )
    parser.add_argument(
        "--md-output",
        default="test-results/242/command_execution_loop_probe.md",
    )
    args = parser.parse_args()

    issues: list[str] = []
    loop_contract = _load_json(args.loop_contract)
    response_contract = _load_json(args.response_contract)
    integrator_text = _load_text("venom_core/agents/integrator.py")
    extension_text = _load_text("tools/vscode-chat-executor/src/extension.ts")
    extension_core_text = _load_text(
        "tools/vscode-chat-executor/src/core/command-execution.ts"
    )

    for key in _missing_required_keys(
        loop_contract,
        ["scope", "loop", "required_plan_fields", "required_evidence_fields"],
    ):
        issues.append(f"loop_contract_missing_key:{key}")
    for key in _missing_required_keys(
        response_contract,
        ["scope", "required_evidence_fields", "required_output_markers"],
    ):
        issues.append(f"response_contract_missing_key:{key}")

    if "REPO_ROOT=" not in integrator_text:
        issues.append("integrator_missing_repo_root_marker")
    if (
        "venom_git_status" not in extension_text
        and "venom_git_status" not in extension_core_text
    ):
        issues.append("extension_missing_venom_git_status_tool")
    if (
        "LanguageModelToolResultPart" not in extension_text
        and "LanguageModelToolResultPart" not in extension_core_text
    ):
        issues.append("extension_missing_tool_result_mapping")
    if (
        "Nie generuj listy komend jako finalnej odpowiedzi" not in extension_text
        and "Nie generuj listy komend jako finalnej odpowiedzi"
        not in extension_core_text
    ):
        issues.append("extension_missing_no_command_list_contract")

    verdict = "pass" if not issues else "fail"
    result = {
        "scope": "pr242-command-execution-loop-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": verdict,
        "issues": issues,
        "observed": {
            "loop_contract_scope": loop_contract.get("scope"),
            "response_contract_scope": response_contract.get("scope"),
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
        "# PR242 Command Execution Loop Probe",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{verdict}`",
        "",
        "## Observed",
        f"- loop_contract_scope: `{result['observed']['loop_contract_scope']}`",
        f"- response_contract_scope: `{result['observed']['response_contract_scope']}`",
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
