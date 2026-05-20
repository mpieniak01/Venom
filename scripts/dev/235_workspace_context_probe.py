#!/usr/bin/env python3
"""PR235 probe for workspace context contract.

Validates AGENTS.md context wiring and local-index-first metadata contract
for VS Code local agent workflows.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class ProbeResult:
    verdict: str
    issues: list[str]
    settings_path: str
    chat_use_agents_md_file: bool | None
    chat_use_nested_agents_md_files: bool | None
    workspace_index_mode: str | None
    workspace_context_default: str | None
    agents_files_present: dict[str, bool]


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "settings_file_missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"settings_json_invalid:{exc.msg}"
    if not isinstance(payload, dict):
        return None, "settings_root_not_object"
    return payload, None


def _probe(settings: dict[str, Any], settings_path: Path) -> ProbeResult:
    issues: list[str] = []

    use_agents = settings.get("chat.useAgentsMdFile")
    use_nested = settings.get("chat.useNestedAgentsMdFiles")
    index_mode = settings.get("venom.workspaceIndexMode")
    context_default = settings.get("venom.workspaceContextDefault")

    if not isinstance(use_agents, bool):
        issues.append("chat.useAgentsMdFile_missing_or_not_bool")
    elif use_agents is not True:
        issues.append("chat.useAgentsMdFile_disabled")

    if not isinstance(use_nested, bool):
        issues.append("chat.useNestedAgentsMdFiles_missing_or_not_bool")

    if not isinstance(index_mode, str) or not index_mode.strip():
        issues.append("venom.workspaceIndexMode_missing_or_empty")
    elif index_mode.strip() != "local-first":
        issues.append("venom.workspaceIndexMode_not_local-first")

    if not isinstance(context_default, str) or not context_default.strip():
        issues.append("venom.workspaceContextDefault_missing_or_empty")
    elif context_default.strip() != "#codebase":
        issues.append("venom.workspaceContextDefault_not_#codebase")

    agents_required = {
        "AGENTS.md": (REPO_ROOT / "AGENTS.md").exists(),
        "docs/AGENTS.md": (REPO_ROOT / "docs" / "AGENTS.md").exists(),
        "docs/PL/AGENTS.md": (REPO_ROOT / "docs" / "PL" / "AGENTS.md").exists(),
    }
    for rel_path, present in agents_required.items():
        if not present:
            issues.append(f"missing_required_agents_file:{rel_path}")

    verdict = "pass" if not issues else "fail"

    return ProbeResult(
        verdict=verdict,
        issues=issues,
        settings_path=str(settings_path),
        chat_use_agents_md_file=use_agents if isinstance(use_agents, bool) else None,
        chat_use_nested_agents_md_files=use_nested
        if isinstance(use_nested, bool)
        else None,
        workspace_index_mode=index_mode.strip()
        if isinstance(index_mode, str)
        else None,
        workspace_context_default=context_default.strip()
        if isinstance(context_default, str)
        else None,
        agents_files_present=agents_required,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PR235 workspace context settings probe"
    )
    parser.add_argument(
        "--settings-file",
        default="config/chat_operator/vscode_workspace_context_contract.json",
    )
    parser.add_argument(
        "--json-output", default="test-results/235/workspace_context_probe.json"
    )
    parser.add_argument(
        "--md-output", default="test-results/235/workspace_context_probe.md"
    )
    args = parser.parse_args()

    settings_path = (REPO_ROOT / args.settings_file).resolve()
    settings, load_error = _load_json(settings_path)

    if load_error:
        result = ProbeResult(
            verdict="fail",
            issues=[load_error],
            settings_path=str(settings_path),
            chat_use_agents_md_file=None,
            chat_use_nested_agents_md_files=None,
            workspace_index_mode=None,
            workspace_context_default=None,
            agents_files_present={
                "AGENTS.md": (REPO_ROOT / "AGENTS.md").exists(),
                "docs/AGENTS.md": (REPO_ROOT / "docs" / "AGENTS.md").exists(),
                "docs/PL/AGENTS.md": (REPO_ROOT / "docs" / "PL" / "AGENTS.md").exists(),
            },
        )
    else:
        assert settings is not None
        result = _probe(settings, settings_path)

    report = {
        "scope": "pr235-workspace-context-probe",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(REPO_ROOT),
        "result": {
            "verdict": result.verdict,
            "issues": result.issues,
            "settings_path": result.settings_path,
            "chat.useAgentsMdFile": result.chat_use_agents_md_file,
            "chat.useNestedAgentsMdFiles": result.chat_use_nested_agents_md_files,
            "venom.workspaceIndexMode": result.workspace_index_mode,
            "venom.workspaceContextDefault": result.workspace_context_default,
            "agents_files_present": result.agents_files_present,
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
        "# PR235 Workspace Context Probe",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Settings file: `{result.settings_path}`",
        "",
        "## Verdict",
        f"- verdict: `{result.verdict}`",
        f"- chat.useAgentsMdFile: `{result.chat_use_agents_md_file}`",
        f"- chat.useNestedAgentsMdFiles: `{result.chat_use_nested_agents_md_files}`",
        f"- venom.workspaceIndexMode: `{result.workspace_index_mode}`",
        f"- venom.workspaceContextDefault: `{result.workspace_context_default}`",
        "",
        "## AGENTS Files",
    ]
    for rel, present in result.agents_files_present.items():
        md_lines.append(f"- `{rel}`: `{present}`")

    md_lines.extend(["", "## Issues"])
    if result.issues:
        for issue in result.issues:
            md_lines.append(f"- `{issue}`")
    else:
        md_lines.append("- `<none>`")

    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")

    return 0 if result.verdict == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
