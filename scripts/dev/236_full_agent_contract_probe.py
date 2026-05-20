#!/usr/bin/env python3
"""PR236 probe for the Venom full-agent contract.

The probe checks that the custom agent, routing contract and operator docs
agree on the same full-agent lane, model and debug surfaces.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _contains_all(text: str, needles: list[str]) -> list[str]:
    missing = [needle for needle in needles if needle not in text]
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description="PR236 full-agent contract probe")
    parser.add_argument(
        "--contract",
        default="config/chat_operator/venom_full_agent_contract.json",
    )
    parser.add_argument(
        "--agent-file",
        default=".github/agents/venom-full-agent.agent.md",
    )
    parser.add_argument(
        "--json-output", default="test-results/236/full_agent_contract.json"
    )
    parser.add_argument(
        "--md-output", default="test-results/236/full_agent_contract.md"
    )
    args = parser.parse_args()

    contract = _read_json(REPO_ROOT / args.contract)
    agent_text = _read_text(REPO_ROOT / args.agent_file)
    chat_operator = _read_text(REPO_ROOT / "docs/CHAT_OPERATOR.md")
    chat_operator_pl = _read_text(REPO_ROOT / "docs/PL/CHAT_OPERATOR.md")

    issues: list[str] = []

    if contract is None:
        issues.append("missing_or_invalid_contract_json")
        contract = {}
    if agent_text is None:
        issues.append("missing_agent_file")
        agent_text = ""
    if chat_operator is None:
        issues.append("missing_chat_operator_doc")
        chat_operator = ""
    if chat_operator_pl is None:
        issues.append("missing_chat_operator_pl_doc")
        chat_operator_pl = ""

    required_tools = (
        contract.get("tools") if isinstance(contract.get("tools"), list) else []
    )
    required_handoffs = (
        contract.get("handoffs") if isinstance(contract.get("handoffs"), list) else []
    )
    required_docs = (
        contract.get("required_docs")
        if isinstance(contract.get("required_docs"), list)
        else []
    )
    debug_surfaces = (
        contract.get("debug_surfaces")
        if isinstance(contract.get("debug_surfaces"), list)
        else []
    )

    contract_model = contract.get("model")
    contract_agent_name = contract.get("agent_name")
    contract_primary_surface = contract.get("primary_surface")
    contract_agents_window_policy = contract.get("agents_window_policy")
    contract_background_handoff = contract.get("background_handoff")
    contract_tool_loop_policy = contract.get("tool_loop_policy")

    if contract_agent_name != "Venom Full Agent":
        issues.append("contract.agent_name_mismatch")
    if contract_model != "qwen2.5-coder:7b":
        issues.append("contract.model_mismatch")
    if contract_primary_surface != "main-vscode-window":
        issues.append("contract.primary_surface_mismatch")
    if contract_agents_window_policy != "review-only":
        issues.append("contract.agents_window_policy_mismatch")
    if contract_background_handoff != "copilot-cli-worktree":
        issues.append("contract.background_handoff_mismatch")
    if contract_tool_loop_policy != "tool-first-required":
        issues.append("contract.tool_loop_policy_mismatch")

    missing_agent_bits = _contains_all(
        agent_text,
        [
            "name: Venom Full Agent",
            "model: qwen2.5-coder:7b",
            "search/codebase",
            "search/usages",
            "runSubagent",
            "Venom Release Guard",
            "Venom Hard Gate Engineer",
            "Agent Debug Log",
            "Chat Debug View",
        ],
    )
    if missing_agent_bits:
        issues.append(
            "agent_file_missing_expected_content:" + ",".join(missing_agent_bits)
        )

    missing_tools = [tool for tool in required_tools if tool not in agent_text]
    if missing_tools:
        issues.append("contract_tools_missing_from_agent:" + ",".join(missing_tools))

    missing_handoffs = [
        handoff for handoff in required_handoffs if handoff not in agent_text
    ]
    if missing_handoffs:
        issues.append(
            "contract_handoffs_missing_from_agent:" + ",".join(missing_handoffs)
        )

    missing_docs = [
        doc
        for doc in required_docs
        if doc not in chat_operator + "\n" + chat_operator_pl
    ]
    if missing_docs:
        issues.append("contract_docs_missing_references:" + ",".join(missing_docs))

    if debug_surfaces and any(surface not in agent_text for surface in debug_surfaces):
        issues.append("debug_surfaces_missing_from_agent")

    result = {
        "scope": "pr236-full-agent-contract-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": "pass" if not issues else "fail",
        "issues": issues,
        "contract": contract,
        "inputs": {
            "contract": str((REPO_ROOT / args.contract).resolve()),
            "agent_file": str((REPO_ROOT / args.agent_file).resolve()),
            "chat_operator": str((REPO_ROOT / "docs/CHAT_OPERATOR.md").resolve()),
            "chat_operator_pl": str((REPO_ROOT / "docs/PL/CHAT_OPERATOR.md").resolve()),
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
        "# PR236 Full Agent Contract Probe",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{result['verdict']}`",
        "",
        "## Contract",
        f"- agent_name: `{contract_agent_name}`",
        f"- model: `{contract_model}`",
        f"- primary_surface: `{contract_primary_surface}`",
        f"- agents_window_policy: `{contract_agents_window_policy}`",
        f"- background_handoff: `{contract_background_handoff}`",
        f"- tool_loop_policy: `{contract_tool_loop_policy}`",
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
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
