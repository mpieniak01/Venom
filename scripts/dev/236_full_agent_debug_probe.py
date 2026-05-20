#!/usr/bin/env python3
"""PR236 probe for the Venom full-agent debug loop contract."""

from __future__ import annotations

import argparse
import json
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


def main() -> int:
    parser = argparse.ArgumentParser(description="PR236 full-agent debug probe")
    parser.add_argument(
        "--contract",
        default="config/chat_operator/venom_full_agent_debug_contract.json",
    )
    parser.add_argument(
        "--settings-file",
        default=".vscode/settings.json",
    )
    parser.add_argument(
        "--agent-file",
        default=".github/agents/venom-full-agent.agent.md",
    )
    parser.add_argument(
        "--json-output", default="test-results/236/full_agent_debug.json"
    )
    parser.add_argument("--md-output", default="test-results/236/full_agent_debug.md")
    args = parser.parse_args()

    contract = _read_json(REPO_ROOT / args.contract) or {}
    settings = _read_json(REPO_ROOT / args.settings_file) or {}
    agent_text = _read_text(REPO_ROOT / args.agent_file)
    docs_en = _read_text(REPO_ROOT / "docs/CHAT_OPERATOR.md")
    docs_pl = _read_text(REPO_ROOT / "docs/PL/CHAT_OPERATOR.md")

    issues: list[str] = []
    advisories: list[str] = []

    if not contract:
        issues.append("missing_or_invalid_contract")

    debug_views = (
        contract.get("debug_views")
        if isinstance(contract.get("debug_views"), list)
        else []
    )
    debug_commands = (
        contract.get("debug_commands")
        if isinstance(contract.get("debug_commands"), list)
        else []
    )
    debug_settings = (
        contract.get("debug_settings")
        if isinstance(contract.get("debug_settings"), list)
        else []
    )
    required_refs = (
        contract.get("required_refs")
        if isinstance(contract.get("required_refs"), list)
        else []
    )

    if contract.get("debug_policy") != "audit-every-session":
        issues.append("debug_policy_mismatch")

    for item in debug_views:
        if item not in agent_text + "\n" + docs_en + "\n" + docs_pl:
            issues.append(f"missing_debug_view_ref:{item}")

    for item in debug_commands:
        if item not in docs_en + "\n" + docs_pl:
            issues.append(f"missing_debug_command_ref:{item}")

    for ref in required_refs:
        if ref not in docs_en + "\n" + docs_pl + "\n" + agent_text:
            issues.append(f"missing_required_ref:{ref}")

    for key in debug_settings:
        value = settings.get(key)
        if value is True:
            continue
        if value is None:
            advisories.append(f"missing_recommended_setting:{key}")
        else:
            issues.append(f"debug_setting_not_enabled:{key}:{value!r}")

    if "Agent Debug Log" not in agent_text or "Chat Debug View" not in agent_text:
        issues.append("agent_file_missing_debug_loop_language")

    result = {
        "scope": "pr236-full-agent-debug-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "verdict": "pass" if not issues else "fail",
        "issues": issues,
        "advisories": advisories,
        "contract": contract,
        "inputs": {
            "contract": str((REPO_ROOT / args.contract).resolve()),
            "settings_file": str((REPO_ROOT / args.settings_file).resolve()),
            "agent_file": str((REPO_ROOT / args.agent_file).resolve()),
            "docs_en": str((REPO_ROOT / "docs/CHAT_OPERATOR.md").resolve()),
            "docs_pl": str((REPO_ROOT / "docs/PL/CHAT_OPERATOR.md").resolve()),
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
        "# PR236 Full Agent Debug Probe",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Verdict: `{result['verdict']}`",
        "",
        "## Issues",
    ]
    md_lines.extend(f"- `{issue}`" for issue in issues) if issues else md_lines.append(
        "- `<none>`"
    )
    md_lines.extend(["", "## Advisories"])
    md_lines.extend(
        f"- `{adv}`" for adv in advisories
    ) if advisories else md_lines.append("- `<none>`")

    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
